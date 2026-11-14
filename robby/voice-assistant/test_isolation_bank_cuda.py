"""Real independent enrolled voices on GPU 1; sequential known speech + unknown TV.

No mock model outputs. Run separately from an active browser filter session.
"""
import json,time,urllib.request
from pathlib import Path
import numpy as np
from benchmark_input_isolation import audio,wer
from input_isolation_process import GPUWorker

def transcribe(y):
    r=urllib.request.Request('http://127.0.0.1:8801/transcribe/parakeet_v3',data=y.astype('<f4').tobytes(),headers={'Content-Type':'application/octet-stream'})
    return json.load(urllib.request.urlopen(r,timeout=45))['text']

def main():
    report={'synthetic_only':True,'rows':[]}
    a=audio('christoph-followup');b=audio('selma-followup-clear');tv=audio('background')
    cases=[('A',a,'Kannst du mir eine kleine Geschichte erzählen?'),('B',b,'Was können wir heute zusammen machen?'),('unknown',tv,'')]
    for name in ('voxlock','scicom'):
        w=GPUWorker();rows=[]
        try:
            w.start();t=time.perf_counter();w.request({'op':'load','model':name},120)
            refs=[audio('christoph-intro')[:64000],audio('selma-intro')[:64000]]
            w.request({'op':'enroll','references':refs},90);setup=time.perf_counter()-t
            # One continuous state sees A, B, then TV. No re-enrollment or state reset.
            pieces=[];spans=[];cursor=0
            for label,x,text in cases:
                pad=np.zeros(16000,np.float32);pieces.extend([pad,x,pad]);spans.append((label,cursor+16000,cursor+16000+len(x),text,x))
                cursor+=len(x)+32000
            x=np.concatenate(pieces);ys=[];times=[]
            for at in range(0,len(x)//640*640,640):
                t=time.perf_counter();r=w.request({'op':'push','audio':x[at:at+640]},.5)
                times.append((time.perf_counter()-t)*1000);ys.append(r['audio'])
            ys.append(w.request({'op':'flush','audio':x[len(x)//640*640:]},2)['audio']);y=np.concatenate(ys)
            assert len(x)==len(y) and np.isfinite(y).all()
            for label,start,end,text,source in spans:
                out=y[max(0,start-3200):end+3200];hyp=transcribe(out)
                rows.append({'speaker':label,'text':hyp,'wer':wer(text,hyp) if text else None,
                    'attenuation_db':round(float(20*np.log10((np.sqrt(np.mean(source**2))+1e-9)/(np.sqrt(np.mean(y[start:end]**2))+1e-9))),2)})
            row={'model':name,'known_voices':2,'setup_s':round(setup,2),'chunk_ms':40,
                 'p50_ms':round(float(np.percentile(times,50)),2),'p95_ms':round(float(np.percentile(times,95)),2),
                 'samples_in':len(x),'samples_out':len(y),'cases':rows}
            report['rows'].append(row);print(json.dumps(row),flush=True)
        finally:w.close()
    Path('logs/isolation-known-bank-cuda.json').write_text(json.dumps(report,indent=2))

if __name__=='__main__':main()
