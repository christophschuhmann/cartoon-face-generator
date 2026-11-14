"""Optional official compile ablation; never needed by the live service."""
import json,time,os
from pathlib import Path
import numpy as np,requests
from optional_lab_gpu import Lease
from .engine import Engine
from .core import TAXONOMY,Settings
path=Path(__file__).parent/'compile-result.json';out={'rows':[]}
def save():path.write_text(json.dumps(out,indent=2))
with Lease():
 requests.post('http://127.0.0.1:8810/internal/offload',timeout=35).raise_for_status()
 e=Engine();e.load();wave=np.zeros(160000,np.float32);wave[-3200:]=.2*np.sin(np.arange(3200)*2*np.pi*880/16000)
 config=Settings(method='multilabel',group_size=64).model_dump()
 for mode in ['eager','compile']:
  try:
   if mode=='compile':
    start=time.perf_counter();e.compile();out['compile_setup_ms']=(time.perf_counter()-start)*1000
   for i in range(4):
    r=e.analyze(wave,3200,TAXONOMY['classic'],config);out['rows'].append({'mode':mode,'iteration':i,**r});save();print(mode,i,round(r['inference_ms']),r['failures'][:1],flush=True)
    if r['failures']:break
  except Exception as exc:out['error']=type(exc).__name__+': '+str(exc)[:1000];save();break
 e.unload();out['completed']=True;save()
