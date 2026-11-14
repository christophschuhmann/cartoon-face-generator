"""Real resident Small RL: causal ASR best-of-3 vs existing single streaming.

Only authored test sentences are saved. Selection ASR is also used for the
transcript check: this is an engineering regression, not independent quality.
"""
import argparse,base64,json,time
from pathlib import Path
import httpx,numpy as np,soundfile as sf

ROOT=Path(__file__).resolve().parent
TEXTS={'de':('de','Hallo, schön dich zu sehen. Heute können wir gemeinsam etwas Neues entdecken.'),
       'en':('en','Hello, it is lovely to see you. We can discover something new together today.'),
       'negation':('de','Bitte öffne die Tür nicht. Warte hier, bis ich wieder zurück bin.'),
       'long':('en','A rainbow appears when sunlight enters tiny drops of water in the air. The light bends and separates into colors, reflects inside each drop, and bends again as it leaves. Every observer sees light from different drops, so each rainbow depends on where you stand.')}

def main():
 p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--modes',nargs='+',default=['single','search_asr']);p.add_argument('--prompts',nargs='+',default=['de','en']);p.add_argument('--seeds',nargs='+',type=int,default=[777,778,779]);a=p.parse_args()
 out=ROOT/'logs/candidate-search'/a.label;out.mkdir(parents=True,exist_ok=True);results=[]
 with httpx.Client(base_url='http://127.0.0.1:8792',timeout=600,trust_env=False) as c:
  deadline=time.monotonic()+1200
  while True:
   try:state=c.get('/api/state').json()
   except httpx.TransportError:
    if time.monotonic()>deadline:raise
    time.sleep(2);continue
   if state['ready'] and not state['busy']:break
   if time.monotonic()>deadline:raise RuntimeError('TTS did not become available')
   print('Waiting:',state.get('phase'),state.get('job_phase'),flush=True);time.sleep(15)
  for prompt in a.prompts:
   language,text=TEXTS[prompt]
   for mode in a.modes:
    for seed in a.seeds:
     body={'model':'small_rl','input_mode':'manual','format':'structured',
      'message':'GENERAL: Very genuine, very authentic, gentle, natural and spontaneous conversation.\nSCRIPT:\n(gentle, natural) '+text,
      'language':language,'generation':mode,'n':1,'batch_size':3 if mode=='search_asr' else 1,
      'search_n':3,'search_chunk_frames':12,'search_seconds':30.,
      'streaming':True,'stream_transport':'pcm_f32','live_only':True,'chunk_frames':20,
      'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699',
      'voice_conversion':False,'speaker_steering':False,'dynamic_reference':False,
      'align':True,'speech_verification':'parallel','seed':seed,'verification_start_seconds':1.}
     row={'prompt':prompt,'target':text,'mode':mode,'seed':seed,'chunks':[],'events':[]};waves=[];started=time.perf_counter();samples=0
     try:
      with c.stream('POST','/api/turn',json=body) as r:
       r.raise_for_status()
       for line in r.iter_lines():
        if not line.startswith('data: '):continue
        e=json.loads(line[6:]);at=(time.perf_counter()-started)*1000
        if e.get('pcm_f32'):
         wave=np.frombuffer(base64.b64decode(e.pop('pcm_f32')),dtype='<f4');waves.append(wave);samples+=len(wave)
         row['chunks'].append({'at_ms':at,'seconds':len(wave)/48000,'cumulative_s':samples/48000,'boundary':e.get('live_alignment'),'selection':e.get('search_selection')})
        elif e.get('event') in ('result','error','reference_context'):row['events'].append(e)
     except Exception as e:row['exception']=type(e).__name__+': '+str(e)
     row['wall_ms']=(time.perf_counter()-started)*1000;row['first_pcm_ms']=row['chunks'][0]['at_ms'] if waves else None
     row['audio_s']=samples/48000;row['rtf']=row['wall_ms']/1000/row['audio_s'] if samples else None
     row['passed']=bool(waves) and not row.get('exception') and not any(x['event']=='error' for x in row['events'])
     if waves:sf.write(out/f'{prompt}-{mode}-{seed}.wav',np.concatenate(waves),48000)
     results.append(row);(out/'results.json').write_text(json.dumps(results,indent=2))
     print(json.dumps({k:v for k,v in row.items() if k not in ('events','chunks','target')}),flush=True)
if __name__=='__main__':main()
