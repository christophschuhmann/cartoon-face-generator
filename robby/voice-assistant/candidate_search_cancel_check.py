"""Cancel a warmed real candidate search after first PCM, then check admission."""
import json,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parent
def main():
 body={'model':'small_rl','input_mode':'manual','format':'structured','message':
  'GENERAL: Natural and gentle conversation.\nSCRIPT:\n(natural) A rainbow appears when sunlight enters tiny drops of water. The light bends and separates into colors. Each observer sees a slightly different rainbow.',
  'language':'en','generation':'search_asr','search_n':3,'search_chunk_frames':12,
  'search_seconds':30,'streaming':True,'stream_transport':'pcm_f32','live_only':True,
  'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699',
  'align':True,'cancel_on_disconnect':True,'seed':780}
 report={'passed':False};started=time.perf_counter()
 with httpx.Client(base_url='http://127.0.0.1:8792',timeout=120,trust_env=False) as c:
  assert not c.get('/api/state').json()['busy']
  with c.stream('POST','/api/turn',json=body) as r:
   r.raise_for_status()
   for line in r.iter_lines():
    if not line.startswith('data: '):continue
    e=json.loads(line[6:])
    if e.get('event')=='error':raise RuntimeError(e.get('code'))
    if e.get('pcm_f32'):report['first_pcm_ms']=(time.perf_counter()-started)*1000;break
  assert 'first_pcm_ms' in report,'No audio was received; cancellation not tested'
  stopped=time.perf_counter()
  while time.perf_counter()-stopped<8:
   if not c.get('/api/state').json()['busy']:
    report['idle_after_disconnect_ms']=(time.perf_counter()-stopped)*1000;report['passed']=True;break
   time.sleep(.05)
 (ROOT/'logs/candidate-search-cancellation.json').write_text(json.dumps(report,indent=2));print(report)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
