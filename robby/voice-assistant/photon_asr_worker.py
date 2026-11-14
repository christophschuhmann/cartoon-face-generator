"""Loopback-only pinned Photon ASR. Separate Torch environment; no audio logs.

Ultra stays on GPU 1; Redux is an optional CPU comparison. Native CUDA graph
decode avoids the generated decoder's CUDA >=12.8 runtime requirement.
"""
import asyncio,base64,os,time
from contextlib import asynccontextmanager
from pathlib import Path
import numpy as np
from fastapi import FastAPI,HTTPException,Request

SPECS={
 'parakeet_ultra':{'name':'ultra','label':'Parakeet Ultra · fast GPU','revision':'73175eb7aeb0d82f1e2a6b53b3aabc10a90bcd0b','device':'cuda'},
 'parakeet_redux':{'name':'redux','label':'Parakeet Redux · CPU comparison','revision':'2bf128600aac4b16946f7ed8372e56117fe5e23b','device':'cpu'},
}
MODELS={};STATE={k:{'ready':False,'phase':'loading'} for k in SPECS}
LIMIT=28*16000*4
slot=asyncio.Semaphore(1)

def prepare():
 import torch,moondream
 torch.set_num_threads(4)
 torch.cuda.set_per_process_memory_fraction(.22)
 for key,s in SPECS.items():
  try:
   root=Path.home()/f'.cache/robby-photon/models/models--moondream--parakeet-{s["name"]}/snapshots'/s['revision']
   model=moondream.photon('moondream/parakeet-'+s['name'],model_path=str(root),device=s['device'],cpu_threads=4,single_pass_batch_capacity=4,decode_path='native')
   # Real inference warmup; no synthetic scores enter production responses.
   for seconds in (.72,1.68,3.28):
    wave=(.01*np.sin(np.arange(round(seconds*16000))*2*np.pi*220/16000)).astype(np.float32)
    model.transcribe(audio=wave,sample_rate=16000,timestamps='word')
   MODELS[key]=model;STATE[key]={'ready':True,'phase':'resident_'+s['device']}
  except Exception as exc:STATE[key]={'ready':False,'phase':'failed','error':type(exc).__name__}

@asynccontextmanager
async def life(app):
 task=asyncio.create_task(asyncio.to_thread(prepare))
 yield
 await task
 for model in MODELS.values():model.close()

app=FastAPI(lifespan=life)
@app.get('/models')
def status():
 return {'models':[{'id':k,'label':s['label'],'repo':'moondream/parakeet-'+s['name'],'revision':s['revision'],**STATE[k]} for k,s in SPECS.items()]}
@app.post('/activate/{key}')
def activate(key:str):
 if key not in MODELS:raise HTTPException(503,'Recognizer is not ready')
 return {'model':key,'ready':True,'switch_ms':0.}

def decode(key,data):
 if not 6400<=len(data)<=LIMIT or len(data)%4:raise ValueError('Expected 0.1–28 s mono float32 at 16 kHz')
 wave=np.frombuffer(data,'<f4').copy()
 if not np.isfinite(wave).all() or np.max(np.abs(wave))>16:raise ValueError('Invalid PCM')
 start=time.perf_counter()
 if float(np.mean(wave.astype(np.float64)**2))<1e-8:
  return {'text':'','timestamps':[],'model':key,'transcribe_ms':0.,'silence_skipped':True}
 r=MODELS[key].transcribe(audio=wave,sample_rate=16000,timestamps='word')
 words=[w for segment in r.get('segments',[]) for w in segment.get('words',[])]
 return {'text':r['text'],'timestamps':words,'model':key,'revision':SPECS[key]['revision'],
         'transcribe_ms':round((time.perf_counter()-start)*1000,3)}

async def body(request,limit):
 data=bytearray()
 async for chunk in request.stream():
  data.extend(chunk)
  if len(data)>limit:raise HTTPException(413,'Audio request is too large')
 return bytes(data)

@app.post('/transcribe/{key}')
async def transcribe(key:str,request:Request):
 if key not in MODELS:raise HTTPException(503,'Recognizer is not ready')
 data=await body(request,LIMIT)
 try:await asyncio.wait_for(slot.acquire(),.5)
 except asyncio.TimeoutError:raise HTTPException(429,'Recognizer busy; retry')
 try:return await asyncio.to_thread(decode,key,data)
 except ValueError as exc:raise HTTPException(422,str(exc))
 finally:slot.release()

@app.post('/batch/{key}')
async def batch(key:str,request:Request):
 if key not in MODELS:raise HTTPException(503,'Recognizer is not ready')
 import json
 try:
  values=json.loads(await body(request,8*LIMIT*4//3+1024))['audio']
  if not isinstance(values,list) or not 1<=len(values)<=8:raise ValueError('Batch must contain 1–8 clips')
  data=[base64.b64decode(v,validate=True) for v in values]
 except (ValueError,KeyError,TypeError):raise HTTPException(422,'Invalid base64 PCM batch')
 try:await asyncio.wait_for(slot.acquire(),.5)
 except asyncio.TimeoutError:raise HTTPException(429,'Recognizer busy; retry')
 try:
  # Concurrent requests share Photon encoder batching; bound to four lanes.
  rows=[]
  for at in range(0,len(data),4):rows.extend(await asyncio.gather(*(asyncio.to_thread(decode,key,x) for x in data[at:at+4])))
  return {'results':rows}
 except ValueError as exc:raise HTTPException(422,str(exc))
 finally:slot.release()
