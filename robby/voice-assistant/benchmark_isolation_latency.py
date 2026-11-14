"""Real local TTS timing; preserve boundary evidence and chunk arrival times."""
import argparse,base64,json,time
from pathlib import Path
import httpx,numpy as np

def run(label):
    rows=[]
    with httpx.Client(base_url='http://127.0.0.1:8792',timeout=180) as client:
        for align in (False,True):
            for seed in (777,778,779):
                body={'model':'small_rl','input_mode':'manual','format':'structured',
                    'message':'GENERAL: Very genuine, very authentic, gentle, natural and spontaneous conversation.\nSCRIPT:\n(gentle, natural) Hallo, schön dich zu sehen. Heute können wir gemeinsam etwas Neues entdecken.',
                    'language':'de','generation':'single','n':1,'batch_size':1,'streaming':True,
                    'stream_transport':'pcm_f32','live_only':True,'chunk_frames':20,
                    'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699',
                    'voice_conversion':False,'speaker_steering':False,'dynamic_reference':False,'align':align,'seed':seed}
                started=time.perf_counter();row={'align':align,'seed':seed,'chunks':[],'events':[]};cumulative=0
                with client.stream('POST','/api/turn',json=body) as r:
                    r.raise_for_status()
                    for line in r.iter_lines():
                        if not line.startswith('data: '):continue
                        e=json.loads(line[6:]);at=(time.perf_counter()-started)*1000
                        if e.get('pcm_f32'):
                            x=np.frombuffer(base64.b64decode(e.pop('pcm_f32')),dtype='<f4');cumulative+=len(x)/48000
                            row['chunks'].append({'at_ms':at,'seconds':len(x)/48000,'cumulative_s':cumulative,'boundary':e.get('live_alignment')})
                        elif e.get('event') in ('error','result','performance','complete'):
                            row['events'].append(e)
                row['wall_ms']=(time.perf_counter()-started)*1000
                row['first_pcm_ms']=row['chunks'][0]['at_ms'] if row['chunks'] else None
                rows.append(row);print(json.dumps({k:v for k,v in row.items() if k not in ('chunks','events')}),flush=True)
                Path('logs/isolation-latency').mkdir(exist_ok=True)
                Path('logs/isolation-latency/tts-'+label+'.json').write_text(json.dumps(rows,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);run(p.parse_args().label)
