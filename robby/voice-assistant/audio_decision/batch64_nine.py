"""Follow-up: all nine unchanged 64-class groups vs one/eight groups per batch."""
import os,json,time,statistics
from pathlib import Path
import numpy as np,torch
from optional_lab_gpu import Lease
from .engine import Engine
from .core import TAXONOMY
from .batch64_study import analyze,differences,CONTEXT
if os.getenv('AUDIO_DECISION_DEVICE')!='cuda:1':raise SystemExit('Set AUDIO_DECISION_DEVICE=cuda:1; this host study preserves production GPU 0.')
ROOT=Path(__file__).parent
OUT=ROOT/'batch64-nine-result.json'
os.environ['ROBO_OPTIONAL_GPU_LOCK']=str(Path.home()/'.cache/robby-d1-batch64-gpu1.lock')
r={'device':'cuda:1','group_size':64,'classes':527,'history_s':10,'target_ms':200,'rows':[]}
def save():OUT.write_text(json.dumps(r,indent=2))
with Lease():
 e=Engine();torch.cuda.set_device(e.device);torch.cuda.set_per_process_memory_fraction(.30,e.device);e.load();r['load_ms']=e.load_ms
 t=np.arange(160000)/16000;wave=np.zeros(160000,np.float32);wave[-3200:]=.2*np.sin(2*np.pi*880*np.arange(3200)/16000)
 reference=None
 def run(label,batch):
  global reference
  out=analyze(e,wave,TAXONOMY['classic'],batch)
  if reference is None:reference=out['scores']
  row={'label':label,'groups_per_batch':batch,'score_difference':differences(out['scores'],reference),**out};r['rows'].append(row);save()
  print(label,batch,round(out['inference_ms'],1),[x['rows'] for x in out['forward_shapes']],round(out['peak_allocated_mb']),row['score_difference'],flush=True)
 for b in [1,8,9]:run('warmup',b)
 for i in range(5):
  order=[1,8,9];order=order[i%3:]+order[:i%3]
  for b in order:run('timing',b)
 e.unload();r['completed']=True;save()
