"""Authored real-TTS checks plus one explicitly injected pre-audio transport fault.

No fault is installed in the running service. A test client drops only its first
unheard request; all played waveforms come from the real TTS + real ASR checker.
"""
import asyncio,json,time,base64
from pathlib import Path
from contextlib import asynccontextmanager
import httpx,numpy as np
from bolt_text import Sentence
from speech_retry import speech_events
ROOT=Path(__file__).resolve().parent

class DropFirst:
 def __init__(self,client):self.client=client;self.count=0
 async def get(self,*a,**kw):return await self.client.get(*a,**kw)
 @asynccontextmanager
 async def stream(self,*a,**kw):
  self.count+=1
  if self.count==1:raise httpx.ConnectError('TEST ONLY: failed before audio admission')
  async with self.client.stream(*a,**kw) as response:yield response

async def main():
 rows=[]
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8792',timeout=240.) as client:
  for text,language,inject in [('Hallo!','de',False),('Bitte öffne die Tür nicht. Warte hier, bis ich wieder zurück bin.','de',False),('Hello, it is lovely to see you. We can discover something new together today.','en',True),('Ich hole kurz Schwung, und dann geht es kopfüber!','de',False)]:
   spec=Sentence(text,'amusement, natural',language=language).spec()
   body={'model':'small_rl','input_mode':'manual','format':'structured','message':spec['manual_prompt'],'language':language,
    'generation':'single','n':1,'batch_size':1,'streaming':True,'stream_transport':'pcm_f32','live_only':True,'chunk_frames':20,
    'cancel_on_disconnect':True,'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699',
    'voice_conversion':False,'speaker_steering':False,'dynamic_reference':False,'align':True,'speech_verification':'parallel','seed':777}
   row={'text':text,'injected_pre_audio_fault':inject,'passed':False};started=time.perf_counter();audio=[];events=[]
   async def wait(*a):pass
   try:
    async for e in speech_events(DropFirst(client) if inject else client,body,wait,timeout=45.):
     if e.get('event')=='audio_chunk' and e.get('pcm_f32'):
      row.setdefault('first_pcm_ms',round((time.perf_counter()-started)*1000,2));audio.append(np.frombuffer(base64.b64decode(e['pcm_f32']),dtype='<f4'))
     if e.get('event') in ('result','speech_retry'):events.append(e)
    row.update(audio_s=sum(len(x) for x in audio)/48000,wall_ms=round((time.perf_counter()-started)*1000,2),events=events)
    assert audio and np.isfinite(np.concatenate(audio)).all()
    if inject:assert any(e.get('code')=='transport_before_audio' for e in events)
    row['passed']=True
   except Exception as e:row['error']=repr(e)
   rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='events'}),flush=True)
   (ROOT/'logs/speech-recovery-live.json').write_text(json.dumps({'passed':all(r['passed'] for r in rows),'rows':rows},indent=2))
 if not all(r['passed'] for r in rows):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
