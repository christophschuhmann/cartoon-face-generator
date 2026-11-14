"""Abort one owned real verified-TTS stream, then check model ownership release."""
import asyncio,json,time
from pathlib import Path
import httpx
async def main():
 report={'passed':False,'synthetic_only':True}
 text='A rainbow appears when sunlight enters tiny drops of water in the air. The light bends and separates into colors, reflects inside each drop, and bends again as it leaves. Every observer sees light from different drops, so each rainbow depends on where you stand.'
 body={'model':'small_rl','message':'GENERAL: Gentle and natural conversation.\nSCRIPT:\n(gentle, natural) '+text,'input_mode':'manual','format':'structured','language':'en','generation':'single','n':1,'streaming':True,'chunk_frames':20,'stream_transport':'pcm_f32','live_only':True,'cancel_on_disconnect':True,'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699','voice_conversion':False,'align':True}
 try:
  async with httpx.AsyncClient(base_url='http://127.0.0.1:8792',timeout=90,trust_env=False) as c:
   state=(await c.get('/api/state')).json();assert state['ready'] and not state['busy']
   async with c.stream('POST','/api/turn',json=body) as r:
    r.raise_for_status()
    async for line in r.aiter_lines():
     if not line.startswith('data: '):continue
     e=json.loads(line[6:]);assert e.get('event')!='error'
     if e.get('pcm_f32'):
      report['boundary']=e.get('live_alignment');break
    else:raise AssertionError('No real verified audio')
    assert report['boundary']['verification_mode']=='parallel'
    assert (await c.get('/api/state')).json()['busy'],'Already complete: invalid cancellation probe'
    start=time.perf_counter()
   for _ in range(100):
    if not (await c.get('/api/state')).json()['busy']:break
    await asyncio.sleep(.05)
   else:raise AssertionError('Worker failed to release model within 5 seconds')
   report.update(passed=True,disconnect_to_idle_ms=(time.perf_counter()-start)*1000)
 except Exception as e:report['error']=repr(e)
 Path('logs/isolation-latency/parallel-cancellation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));assert report['passed']
if __name__=='__main__':asyncio.run(main())
