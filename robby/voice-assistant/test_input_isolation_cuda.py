"""Real, paced CUDA + controller + IPC + ASR regression on synthetic audio.

Run with the production Python. Uses GPU 1 by default; never restarts services.
This does not represent an acoustic room/microphone test.
"""
import asyncio,json,time,urllib.request
from pathlib import Path
import numpy as np
from benchmark_input_isolation import audio
from input_isolation import InputIsolation,unpack
from test_input_isolation import Conversation,packet

async def main():
    rows=[]
    for name in ('voxlock','scicom'):
        c=Conversation();f=InputIsolation(c)
        try:
            f.reference=audio('christoph-intro')[:96000];t=time.perf_counter()
            await f.configure(name)
            while f.phase not in ('active','error') and time.perf_counter()-t<100:await asyncio.sleep(.1)
            assert f.phase=='active',f.state()
            setup=(time.perf_counter()-t)*1000
            target=audio('christoph-followup');x=np.r_[np.zeros(16000,np.float32),target,np.zeros(16000,np.float32)]
            times=[];first=None;started=time.perf_counter()
            for at in range(0,len(x),320):
                await asyncio.sleep(max(0,started+(at+min(320,len(x)-at))/16000-time.perf_counter()))
                before=time.perf_counter();await f.receive(packet(np.rint(x[at:at+320]*32768)))
                times.append((time.perf_counter()-before)*1000)
                if first is None and c.packets:first=(time.perf_counter()-started)*1000
                assert f.phase=='active',f.state()
            stats=f.state();await f.configure('off')
            y=np.concatenate([unpack(p)[2] for p in c.packets]);assert len(y)==len(x)
            assert np.isfinite(y).all() and np.max(np.abs(y))>.001
            req=urllib.request.Request('http://127.0.0.1:8801/transcribe/parakeet_v3',data=y.astype('<f4').tobytes(),headers={'Content-Type':'application/octet-stream'})
            result=await asyncio.to_thread(lambda:json.load(urllib.request.urlopen(req,timeout=30)))
            rows.append({'model':name,'gpu':f.gpu,'setup_ms':round(setup,1),'first_forwarded_ms':round(first,2),
                'packet_handler_p50_ms':round(float(np.percentile(times,50)),2),'packet_handler_p95_ms':round(float(np.percentile(times,95)),2),
                'filter_last_compute_ms':stats['compute_ms'],'filtered_chunks':stats['chunks'],
                'samples_in':len(x),'samples_out_after_off':len(y),'asr':result,'raw_environment_samples':sum(len(r[0]) for r in c.raw)})
            print(json.dumps(rows[-1]),flush=True)
        finally:await f.close()
    Path('logs/input-isolation-ui-cuda.json').write_text(json.dumps({'synthetic_only':True,'rows':rows},indent=2))

if __name__=='__main__':asyncio.run(main())
