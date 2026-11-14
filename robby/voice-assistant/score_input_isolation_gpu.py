"""Transcribe actual saved filter outputs using the existing Parakeet v3 worker.

Full-scene WER penalizes background words; cropped WER measures target retention.
ASR runs after filtering, outside filter latency measurements. A continuous-TV
tail is also transcribed to detect leaked words during the target user's pause.
"""
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import numpy as np
import soundfile as sf
from benchmark_input_isolation import wer, SR

OUT = Path(__file__).resolve().parent / 'logs/input-isolation-gpu'
cache_path = OUT / 'asr-cache.json'
cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
TEXT = {'christoph': 'Kannst du mir eine kleine Geschichte erzählen?',
        'selma': 'Was können wir heute zusammen machen?'}


def transcribe(x):
    payload = np.ascontiguousarray(x, dtype='<f4').tobytes()
    key = hashlib.sha256(payload).hexdigest()
    if key not in cache:
        req = urllib.request.Request('http://127.0.0.1:8801/transcribe/parakeet_v3',
            data=payload, headers={'Content-Type': 'application/octet-stream'}, method='POST')
        t = time.perf_counter()
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.load(response)
        if 'text' not in result:
            raise RuntimeError(str(result)[:300])
        cache[key] = {'text': result['text'], 'latency_ms': (time.perf_counter()-t)*1000}
        cache_path.write_text(json.dumps(cache, indent=2))
    return cache[key]['text']


for path in sorted(OUT.glob('*.json')):
    report = json.loads(path.read_text())
    if report.get('status') != 'completed' or not report.get('arguments',{}).get('quality'):
        continue
    for row in report['rows']:
        if 'asr' in row:
            continue
        y, sr = sf.read(OUT / row['audio'], dtype='float32')
        assert sr == SR
        start, end = int(row['target_start_s']*SR), int(row['target_end_s']*SR)
        full = transcribe(y)
        crop = transcribe(y[max(0,start-1600):min(len(y),end+1600)])
        tail = transcribe(y[end+SR:]) if row['background_gain'] else ''
        text = TEXT[row['speaker']]
        row['asr'] = {'whole_scene_text': full, 'target_interval_text': crop,
                      'background_only_text': tail, 'target_reference': text,
                      'whole_scene_target_wer': wer(text, full), 'target_interval_wer': wer(text,crop)}
        path.write_text(json.dumps(report, indent=2))
        print(json.dumps({'label':report['label'], 'case':row['case'], **row['asr']}), flush=True)
