"""Publish only authored test summaries, never visitor logs or microphone data."""
import html,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 rows=json.loads((ROOT/'logs/candidate-search/summary.json').read_text())
 browser=json.loads((ROOT/'logs/candidate-search-browser.json').read_text())
 cancel=json.loads((ROOT/'logs/candidate-search-cancellation.json').read_text())
 table=[]
 for mode in ['single','search_asr']:
  for prompt in ['de','en','negation','long']:
   group=[r for r in rows if r['label']=='graph-warm' and r['mode']==mode and r['prompt']==prompt]
   if not group:continue
   def med(k):
    values=[r[k] for r in group if r.get(k) is not None]
    return statistics.median(values) if values else None
   fmt=lambda x:'not measured' if x is None else f'{x:.3f}'
   table.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [mode,prompt,
    str(sum(bool(r['passed']) for r in group))+'/'+str(len(group)),
    fmt(med('first_pcm_ms')/1000 if med('first_pcm_ms') else None),fmt(med('rtf')),
    fmt(med('wer')),fmt(med('asr_seconds')),fmt(med('zero_reserve_underrun_ms'))])+'</tr>')
 cold=[r for r in rows if r['label'] in ('cold','graph-cold','final-cold')]
 browser_summary={'passed':browser['passed'],'physical_microphone':False,'turns':[
  {'search':r['search'],'audio_chunks':r['audio_chunks'],
   'metrics':{k:v for k,v in next((e['metrics'] for e in r['events'] if e['type']=='pipeline_metrics'),{}).items()
    if k in ('tts_generation_mode','llm_first_sentence_ms','tts_first_audio_ms','first_audio_ms','llm_rate_limit_retries','tts_retries')}} for r in browser['turns']],
  'page_errors':browser['page_errors'],'error':browser.get('error')}
 receipt={'hardware':'2 × RTX 3090 24 GiB; TTS GPU 0, resident Photon ASR GPU 1',
  'model':'laion/Humaneness-Voice-Small-1.1-Alpha-RL-r128-v1','temperature':.8,'cfg':2,
  'reference':'Mira / emolia_c1699, existing fixed reference','summary':rows,
  'browser':browser_summary,'cancellation':cancel,
  'codec_equivalence':json.loads((ROOT/'logs/candidate-search-codec.json').read_text()) if (ROOT/'logs/candidate-search-codec.json').exists() else {'status':'not run'}}
 (ROOT/'static/candidate-search-results.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False))
 doc='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Robby · causal candidate streaming</title><style>body{font:16px/1.6 system-ui;max-width:1150px;margin:32px auto;padding:0 20px;color:#e7eef7;background:#111b28}a{color:#91c6ff}table{border-collapse:collapse;width:100%}td,th{padding:9px;text-align:left;border-bottom:1px solid #3a4859}pre{white-space:pre-wrap;background:#1c2c40;padding:16px}section{overflow:auto}h2{margin-top:36px}</style><h1>Causal Best-of-3 streaming</h1><p>14 November 2026 · RTX 3090 · Small 1.1 Alpha RL · CFG 2 · temperature 0.8 · fixed Mira reference.</p><p>Enable <b>Speed &amp; verification → Best-of-3 streaming</b> in <a href="/desk-robot/">Robby</a>. The existing single-stream mode remains the default. Three continuations are generated in one batch. Every 12 semantic frames (960 ms of audio), actual ASR word accuracy and progress select a winner. Its complete semantic and codec state are copied into the next three lanes. Already emitted audio is never revised. Optional edge fades reuse these timestamps; there is no extra output ASR pass.</p><h2>Measured warm comparison</h2><p>Three seeds per condition. Entries are medians; success counts include failures. First PCM is local HTTP request to received samples, not audible browser onset. RTF is total wall time divided by emitted audio duration, including selection. ASR runs on GPU 1; this is not a one-GPU-only throughput claim. The single stream uses the previous parallel word checker and 1.6-s maximum chunks with its initial ramp. Search uses fixed 960-ms selection chunks.</p><section><table><tr><th>Mode</th><th>Authored prompt</th><th>Completed</th><th>First PCM (s)</th><th>Wall RTF</th><th>ASR WER</th><th>Selection ASR (s)</th><th>Zero-reserve gaps (ms)</th></tr>'''+''.join(table)+'''</table></section><p>de/en: friendly two-sentence reply; negation: German “do not open the door”; long: English explanation of rainbows. WER is a final Parakeet Ultra transcript check using the same ASR family as selection. It is not independent perceptual evidence or a large quality study. Zero-reserve gaps assume playback immediately on the first received sample; the browser normally buffers additional audio.</p><h2>Cold start and limitations</h2><p>A newly encountered batch shape compiles and autotunes before producing audio. This can take minutes and must not be presented as normal warm latency. The service also warms its existing single/continuous-stream paths at startup.</p><pre>'''+html.escape(json.dumps(cold,indent=2,ensure_ascii=False))+'''</pre><p>Search can select incorrect or faster-but-less-natural speech. It does not optimize speaker similarity or enjoyment. ASR uses approximately 12-second rolling windows; later decoding can revise earlier recognized words. Missing openings are bounded to 3.84 seconds of generated audio. Natural endings are checked using selection timestamps, without a second full-text gate. Large, quick reactions and optional idle speech retain their existing paths.</p><h2>Recovery and browser checks</h2><p>Transient candidate ASR errors get one retry. Before any published sentence audio, missing openings/empty audio get up to three attempts; a first search OOM falls back to a single stream. Audio that has already played is not replayed. Cancellation remains cooperative at frame/ASR boundaries.</p><pre>'''+html.escape(json.dumps({'browser':browser_summary,'cancellation':cancel},indent=2))+'''</pre><p>The browser test uses real HTTPS, LLM, TTS and playback scheduling, plus toggle persistence. It is not a physical microphone or listening-quality test. Fault recovery is covered by injected transport unit tests; no intentional production OOM was induced.</p><p><a href="/static/candidate-search-results.json">Complete measured summaries</a> · <a href="https://github.com/christophschuhmann/cartoon-face-generator/blob/main/robby/voice-assistant/ASR_CANDIDATE_STREAMING.md">Algorithm, test commands and source guide</a> · <a href="/desk-robot/">Back to Robby</a></p></html>'''
 (ROOT/'static/candidate-search.html').write_text(doc)
if __name__=='__main__':main()
