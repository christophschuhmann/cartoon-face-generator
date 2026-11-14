"""Summarize authored benchmark audio using real private ASR, not invented WER."""
import argparse,base64,json,sys
from pathlib import Path
import httpx,numpy as np,soundfile as sf
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parent
TTS=ROOT.parent/'humaneness-small'
if not TTS.is_dir():TTS=ROOT/'tts-runtime/humaneness-small'
sys.path.insert(0,str(TTS))
from asr_chunk_search import align_prefix
from streaming_boundaries import boundary_tokens

def main():
 p=argparse.ArgumentParser();p.add_argument('labels',nargs='+');a=p.parse_args();summary=[]
 with httpx.Client(base_url='http://127.0.0.1:8822',timeout=30,trust_env=False) as c:
  for label in a.labels:
   folder=ROOT/'logs/candidate-search'/label
   for row in json.loads((folder/'results.json').read_text()):
    item={k:row[k] for k in ('prompt','mode','seed','first_pcm_ms','wall_ms','audio_s','rtf','passed')};item['label']=label
    result=next((e for e in row['events'] if e['event']=='result'),{})
    perf=result.get('performance',{});timeline=perf.get('timeline',[])
    item.update(asr_seconds=perf.get('scoring_seconds'),tts_codec_seconds=perf.get('tts_codec_seconds'),
      selection_steps=len(timeline),winner_rows=[x['retained_rows'][0] for x in timeline],
      asr_backends=sorted(set(s.get('asr_backend','unknown') or 'unknown' for x in timeline for s in x['scores'])),
      emitted_end_verified=result.get('live_stream',{}).get('end_verified'),
      graph_capture_seconds=perf.get('graph_capture_seconds'))
    if row['chunks']:
     chunks=row['chunks'];clock=chunks[0]['at_ms']/1000;underrun=0.
     for ch in chunks:
      at=ch['at_ms']/1000
      if at>clock:underrun+=at-clock;clock=at
      clock+=ch['seconds']
     item['zero_reserve_underrun_ms']=underrun*1000
     wav,rate=sf.read(folder/f"{row['prompt']}-{row['mode']}-{row['seed']}.wav",dtype='float32')
     audio=resample_poly(wav,1,3).astype('<f4');assert rate==48000
     r=c.post('/batch/parakeet_ultra',json={'audio':[base64.b64encode(audio.tobytes()).decode()]});r.raise_for_status();asr=r.json()['results'][0]
     hypothesis=' '.join(x['word'] for x in asr['timestamps'])
     alignment=align_prefix(boundary_tokens(row['target']),boundary_tokens(hypothesis),True)
     item.update(target=row['target'],asr_hypothesis=hypothesis,wer=alignment['prefix_wer'])
    summary.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
 (ROOT/'logs/candidate-search/summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
