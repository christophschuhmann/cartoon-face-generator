"""Authored German TTS fixtures: timing, finite PCM, final transcription and silent-tail sanity."""
import base64,json,time,re,statistics
from pathlib import Path
import httpx,numpy as np
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parent
CASES=[('contentment, soft','Heute scheint die Sonne und wir gehen gemeinsam spazieren.',.8),('amusement, playful','Mein kleiner Roboter erzählt heute einen richtig lustigen Witz.',.8),('anger, firm','Ich bin wirklich sauer, weil mein letzter Keks verschwunden ist.',.8),('interest, natural','Wir testen heute eine klare und verständliche Stimme.',0.)]
def words(s):return re.findall(r'\w+',s.casefold())
def wer(a,b):
 a=words(a);b=words(b);d=list(range(len(b)+1))
 for i,x in enumerate(a,1):
  row=[i]
  for j,y in enumerate(b,1):row.append(min(row[-1]+1,d[j]+1,d[j-1]+(x!=y)))
  d=row
 return d[-1]/max(1,len(a))
def main():
 report={'scope':__doc__,'rows':[]}
 with httpx.Client(timeout=300) as c:
  for cue,text,temp in CASES:
   body={'model':'small_rl','input_mode':'manual','format':'structured','message':'GENERAL: Preserve the reference speaker. Natural spontaneous conversational German.\nSCRIPT:\n('+cue+') '+text,'language':'de','generation':'single','n':1,'streaming':True,'stream_transport':'pcm_f32','live_only':True,'chunk_frames':20,'cancel_on_disconnect':True,'temperature':temp,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699','voice_conversion':False,'speaker_steering':False,'dynamic_reference':False,'align':True,'seed':777}
   t=time.perf_counter();chunks=[];first=None;audible=None;results={}
   with c.stream('POST','http://127.0.0.1:8792/api/turn',json=body) as r:
    r.raise_for_status()
    for line in r.iter_lines():
     if not line.startswith('data: '):continue
     e=json.loads(line[6:])
     if e.get('event')=='error':raise RuntimeError(str(e)[:300])
     if e.get('pcm_f32'):
      pcm=np.frombuffer(base64.b64decode(e['pcm_f32']),'<f4').copy();assert np.isfinite(pcm).all();chunks.append(pcm)
      first=first if first is not None else time.perf_counter()-t
      if audible is None and np.sqrt(np.mean(pcm**2))>.001:audible=time.perf_counter()-t
     if e.get('event')=='result':results=e
   total=time.perf_counter()-t;wave=np.concatenate(chunks);assert len(wave)>4800
   audio16=resample_poly(wave,1,3).astype('<f4');r=c.post('http://127.0.0.1:8798/api/bolt/asr?model=parakeet_v3',content=audio16.tobytes());r.raise_for_status();transcript=r.json()['text']
   row={'text':text,'cue':cue,'temperature':temp,'first_pcm_s':first,'first_nonquiet_chunk_s':audible,'generation_s':total,'audio_s':len(wave)/48000,'wer':wer(text,transcript),'transcript':transcript,'rms':float(np.sqrt(np.mean(wave**2))),'chunks':len(chunks)}
   report['rows'].append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
 report['passed']=all(r['wer']<=.15 and r['rms']>.001 for r in report['rows']);(ROOT/'static/rtx3090-quality.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));assert report['passed']
if __name__=='__main__':main()
