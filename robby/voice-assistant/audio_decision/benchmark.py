"""Reproducible GPU timing and temporal-focus probes, using actual d1 outputs."""
import json,time,os
from pathlib import Path
import numpy as np,requests
from .core import TAXONOMY,Settings
from .engine import Engine,MODEL,REVISION
from optional_lab_gpu import Lease

def main():
    path=Path(__file__).parent/'benchmark-result.json';results=[]
    report={'model':MODEL,'revision':REVISION,'hardware':'RTX 3090 24 GB, shared workloads','rows':results}
    def store():path.write_text(json.dumps(report,indent=2))
    with Lease():
        requests.post('http://127.0.0.1:8810/internal/offload',timeout=35).raise_for_status()
        e=Engine();e.load();report['load_ms']=e.load_ms
        def run(label,seconds,count=16,hop=200,group=16,method='binary',repeat=False,reuse=True,kind='late',context=''):
            wave=np.zeros(round(seconds*16000),np.float32);n=hop*16
            tone=(.2*np.sin(np.arange(n)*2*np.pi*880/16000)).astype(np.float32)
            if kind=='late':wave[-n:]=tone
            elif kind=='early':wave[:n]=tone
            classes=TAXONOMY['classic'][:count]
            if label.startswith('focus'):classes=[c for c in TAXONOMY['classic'] if c['name'] in ('Speech','Music','Beep, bleep','Silence','Dog')]
            settings=Settings(taxonomy='classic',hop_ms=hop,group_size=group,method=method,repeat_target=repeat,context=context).model_dump()
            out=e.analyze(wave,n,classes,settings,reuse=reuse)
            row={'label':label,'audio_s':seconds,'classes':len(classes),'hop_ms':hop,'group_size':group,'method':method,'repeat_target':repeat,'reuse_enabled':reuse,'signal':kind,**out}
            results.append(row);store();print(label,seconds,count,hop,group,method,round(out['inference_ms'],1),len(out['failures']),flush=True)
            return out
        run('warmup',2)
        for method in ('binary','multilabel'):
            for group in (16,32,64):
                run('group_comparison',5,100,group=group,method=method)
        # Baseline matrix always includes the documented group size of sixteen.
        for seconds in (2,5,10):
            for count in (16,100,527):run('baseline',seconds,count)
        best=min((r for r in results if r['label']=='group_comparison' and not r['failures']),key=lambda r:r['inference_ms'])
        report['fastest_tested']={k:best[k] for k in ('method','group_size')}
        for hop in (100,200,300):
            for repeat in (False,True):
                for n in range(3):run('optimized_hops',10,527,hop=hop,group=best['group_size'],method=best['method'],repeat=repeat)
        a=run('reuse_equivalence',5,100,reuse=False)
        b=run('reuse_equivalence',5,100,reuse=True)
        report['reuse_max_abs_score_difference']=max(abs(a['scores'][k]-b['scores'][k]) for k in a['scores'] if a['scores'][k] is not None and b['scores'][k] is not None)
        for kind in ('late','early','silent'):
            for repeat in (False,True):run('focus_probe',2,hop=200,repeat=repeat,kind=kind,context='A swimming pool with people, dogs and music. This is a hypothesis, not ground truth.')
        report['completed']=True;store();e.unload()

if __name__=='__main__':main()
