"""Authored, fixed-seed real-server comparison; no private audio or fake scores."""
import argparse,base64,json,sys,time
from pathlib import Path
import httpx,numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'humaneness-small'))
from live_latency_benchmark import PROMPT as ORIGINAL_PROMPT,gaps

PROMPTS={'long':'GENERAL: Gentle and natural conversation.\nSCRIPT:\n(gentle, natural) A rainbow appears when sunlight enters tiny drops of water in the air. The light bends and separates into colors, reflects inside each drop, and bends again as it leaves. Every observer sees light from different drops, so each rainbow depends on where you stand.',
 'original':ORIGINAL_PROMPT,
 'current':'GENERAL: Very genuine, very authentic, gentle, natural and spontaneous conversation.\nSCRIPT:\n(gentle, natural) Hallo, schön dich zu sehen. Heute können wir gemeinsam etwas Neues entdecken.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--label',required=True)
 p.add_argument('--prompts',nargs='+',default=['current','original'],choices=list(PROMPTS))
 p.add_argument('--modes',nargs='+',default=['off','serial','parallel'],choices=['off','serial','parallel'])
 p.add_argument('--seeds',nargs='+',type=int,default=[777,778,779])
 p.add_argument('--first-scan',type=float,default=1.);a=p.parse_args()
 out=ROOT/'logs/isolation-latency';out.mkdir(exist_ok=True);rows=[]
 with httpx.Client(base_url='http://127.0.0.1:8792',timeout=180,trust_env=False) as c:
  for prompt in a.prompts:
   for mode in a.modes:
    for seed in a.seeds:
     body={'model':'small_rl','input_mode':'manual','format':'structured','message':PROMPTS[prompt],
      'language':'en' if prompt=='long' else 'de','generation':'single','n':1,'batch_size':1,'streaming':True,'stream_transport':'pcm_f32',
      'live_only':True,'chunk_frames':20,'temperature':.8,'guidance':2.,'voice_mode':'profile',
      'voice_profile':'emolia_c1699','voice_conversion':False,'speaker_steering':False,'dynamic_reference':False,
      'align':mode!='off','speech_verification':'parallel' if mode=='parallel' else 'serial','seed':seed,
      'verification_start_seconds':a.first_scan}
     row={'prompt':prompt,'mode':mode,'seed':seed,'chunks':[],'events':[]};started=time.perf_counter();samples=0
     with c.stream('POST','/api/turn',json=body) as r:
      r.raise_for_status()
      for line in r.iter_lines():
       if not line.startswith('data: '):continue
       e=json.loads(line[6:]);at=(time.perf_counter()-started)*1000
       if e.get('pcm_f32'):
        n=len(base64.b64decode(e.pop('pcm_f32')))//4;samples+=n
        row['chunks'].append({'at_ms':at,'seconds':n/48000,'cumulative_s':samples/48000,'boundary':e.get('live_alignment')})
       elif e.get('event') in ('result','error','reference_context'):row['events'].append(e)
     row['wall_ms']=(time.perf_counter()-started)*1000
     row['first_pcm_ms']=row['chunks'][0]['at_ms'] if row['chunks'] else None
     row['audio_s']=samples/48000
     row['gaps_ms']=gaps([(x['at_ms']/1000,x['cumulative_s']) for x in row['chunks']])*1000 if row['chunks'] else None
     row['passed']=bool(row['chunks']) and not any(x['event']=='error' for x in row['events'])
     if mode=='parallel' and row['chunks']:
      row['passed'] &= row['chunks'][0]['boundary'].get('verification_mode')=='parallel'
      result=next((e for e in row['events'] if e['event']=='result'),{})
      row['complete_target_verified']=result.get('live_stream',{}).get('end_verified',False)
      row['passed'] &= row['complete_target_verified']
     rows.append(row);(out/('parallel-'+a.label+'.json')).write_text(json.dumps(rows,indent=2))
     print(json.dumps({k:v for k,v in row.items() if k not in ('chunks','events')}),flush=True)
 if not all(x['passed'] for x in rows):raise SystemExit(1)
if __name__=='__main__':main()
