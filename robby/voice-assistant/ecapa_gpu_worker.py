"""Private, bounded FP32 ECAPA worker. No names/audio/embeddings are logged."""
import asyncio,time
from contextlib import asynccontextmanager
import numpy as np
from fastapi import FastAPI,HTTPException,Request
from speaker_teacher import EcapaTeacher,TEACHER_REVISION

teacher=None;ready=False;slot=asyncio.Semaphore(1)
def prepare():
    global teacher,ready
    import torch
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.06)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    teacher=EcapaTeacher(device='cuda:0')
    teacher.embed(np.sin(np.arange(48640)*.05).astype(np.float32)*.03)
    ready=True
@asynccontextmanager
async def life(app):
    await asyncio.to_thread(prepare)
    yield
app=FastAPI(lifespan=life)
@app.get('/health')
def health():return {'ready':ready,'revision':TEACHER_REVISION,'device':'cuda','precision':'fp32'}
@app.post('/embed')
async def embed(request:Request):
    if not ready:raise HTTPException(503,'Speaker worker not ready')
    data=bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data)>15*16000*4:raise HTTPException(413,'At most 15 seconds')
    if len(data)%4 or len(data)<10240*4:raise HTTPException(422,'Need >=640 ms mono float32 PCM, 16 kHz')
    try:await asyncio.wait_for(slot.acquire(),.2)
    except asyncio.TimeoutError:raise HTTPException(429,'Speaker worker busy')
    try:
        tick=time.perf_counter();v=await asyncio.to_thread(teacher.embed,np.frombuffer(data,'<f4'))
        return {'embedding':v.tolist(),'revision':TEACHER_REVISION,'compute_ms':(time.perf_counter()-tick)*1000}
    except ValueError as exc:raise HTTPException(422,str(exc))
    finally:slot.release()
