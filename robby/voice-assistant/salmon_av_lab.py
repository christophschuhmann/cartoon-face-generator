"""Request-scoped SALMONN audio/video analysis; unloads model after request."""
import asyncio,contextlib,json,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

async def analyze(normalized,tmp,starts,window,context,cmd):
    env={**os.environ,'CUDA_VISIBLE_DEVICES':os.getenv('SALMON_GPU','1'),
      'PYTHONPATH':'/mnt/nvme/moss-15-v2/salmon-env:/mnt/raid/robby-models/video-SALMONN-2/video_SALMONN2_pro',
      'LD_PRELOAD':'/lib/x86_64-linux-gnu/libffi.so.7','HF_HUB_OFFLINE':'1','PYTHONUNBUFFERED':'1'}
    p=await asyncio.create_subprocess_exec('/mnt/nvme/venvs/dramabox-torch28/bin/python','-u',str(ROOT/'salmon_av_worker.py'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=None,env=env,limit=1024*1024)
    t=time.perf_counter();results=[];previous=[]
    try:
        raw=await asyncio.wait_for(p.stdout.readline(),120)
        if not raw:raise RuntimeError('SALMONN model failed to load; check GPU memory and dependencies')
        ready=json.loads(raw)
        if not ready.get('ready'):raise RuntimeError('SALMONN model not ready')
        for i,start in enumerate(starts):
            path=tmp/('salmon-'+str(i)+'.mp4')
            await cmd('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(normalized),'-t',str(window),'-vf','fps=5,scale=320:240:force_original_aspect_ratio=decrease','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-ar','16000','-ac','1',str(path))
            p.stdin.write((json.dumps({'path':str(path),'previous':previous,'context':context},ensure_ascii=False)+'\n').encode());await p.stdin.drain()
            raw=await asyncio.wait_for(p.stdout.readline(),180)
            if not raw:raise RuntimeError('SALMONN worker stopped')
            result=json.loads(raw)
            if not result.get('ok'):raise RuntimeError(result.get('error','SALMONN failed'))
            result=result['result']
            if result['parse_ok']:
                from lfm3_timeline import normalize_timeline
                from lfm3_context import flag_context_echo
                result['annotation']=flag_context_echo(normalize_timeline(result['annotation'],start,window,fps=5),context)
                result['annotation']['timeline_status']='Model-estimated times, not verified frame timestamps; at most 12 sampled frames per window.'
            previous.append({'start_s':start,'observation':result['annotation'] if result['parse_ok'] else result['raw_text']})
            results.append(result);path.unlink(missing_ok=True)
        return {'status':'ok','load_ms':ready['load_ms'],'total_ms':round((time.perf_counter()-t)*1000,1),'windows':results}
    finally:
        if p.returncode is None:
            p.terminate()
            with contextlib.suppress(Exception):await asyncio.wait_for(p.wait(),5)
            if p.returncode is None:p.kill();await p.wait()
