"""Replay the authored English seed that previously emitted only a prefix.

Uses real TTS and verifier results throughout; no injected alignment evidence.
"""
import asyncio,json,base64,time
from pathlib import Path
import httpx,numpy as np
from speech_retry import speech_events
ROOT=Path(__file__).resolve().parent
async def main():
 text='Hello, it is lovely to see you. We can discover something new together today.'
 body={'model':'small_rl','input_mode':'manual','format':'structured',
  'message':'GENERAL: Very genuine, very authentic, gentle, natural and spontaneous conversation.\nSCRIPT:\n(gentle, natural) '+text,
  'language':'en','generation':'single','n':1,'batch_size':1,'streaming':True,'stream_transport':'pcm_f32','live_only':True,'chunk_frames':20,
  'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699','voice_conversion':False,'speaker_steering':False,
  'dynamic_reference':False,'align':True,'speech_verification':'parallel','seed':778,'verification_start_seconds':1.,'cancel_on_disconnect':True}
 report={'passed':False,'target':text,'seed':778,'synthetic_evidence':False,'events':[]};waves=[]
 async def wait(*a):pass
 started=time.perf_counter()
 try:
  async with httpx.AsyncClient(base_url='http://127.0.0.1:8792',timeout=240.) as client:
   async for e in speech_events(client,body,wait,timeout=45.):
    if e.get('pcm_f32'):
     waves.append(np.frombuffer(base64.b64decode(e['pcm_f32']),dtype='<f4'));report.setdefault('first_pcm_ms',round((time.perf_counter()-started)*1000,2))
    if e.get('event') in ('result','speech_retry'):report['events'].append(e)
   report['audio_s']=sum(len(w) for w in waves)/48000
   report['suffix_recovery_observed']=any(e.get('strategy')=='verified_suffix' for e in report['events'])
   # Independent request, same ASR family: a regression check, not unbiased WER.
   from scipy.signal import resample_poly
   audio=resample_poly(np.concatenate(waves),1,3).astype('<f4')
   r=await client.post('http://127.0.0.1:8822/batch/parakeet_ultra',json={'audio':[base64.b64encode(audio.tobytes()).decode()]});r.raise_for_status()
   out=r.json()['results'][0]
   report['recognized_words']=[w['word'] for w in out['timestamps']]
   report['passed']=bool(waves) and any('today' in w.lower() for w in report['recognized_words'])
 except Exception as e:report['error']=repr(e)
 report['wall_ms']=round((time.perf_counter()-started)*1000,2)
 (ROOT/'logs/speech-recovery-suffix-live.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k!='events'}),flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
