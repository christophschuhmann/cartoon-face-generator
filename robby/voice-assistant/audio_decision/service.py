"""Bounded upload jobs and latest-window live scheduling; loopback ASGI service."""
import asyncio,contextlib,hashlib,json,math,os,secrets,time
from pathlib import Path
from collections import deque
from contextlib import asynccontextmanager
import httpx,numpy as np,soundfile as sf
from fastapi import FastAPI,HTTPException,Request,WebSocket,WebSocketDisconnect
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from optional_lab_gpu import Lease,OptionalLabBusy
from .core import Settings,TAXONOMY,intervals,process_rows,csv_export
from .engine import Engine,MODEL,REVISION,PROMPT_VERSION
from . import storage

ROOT=Path(__file__).parent;engine=Engine();jobs={};active=None;starts={};UPLOAD_LIMIT=32*1024**2;MAX_SAMPLES=120*16000
COOKIE='robby_audio_decision';cookie_path='/audio-decision'

@asynccontextmanager
async def lifespan(app):
    storage.expire()
    async def janitor():
        while True:
            await asyncio.sleep(60)
            storage.expire(protected())
            for identifier,job in list(jobs.items()):
                if identifier!=active and not (storage.ROOT/job['owner']/identifier).exists():jobs.pop(identifier,None)
    cleanup=asyncio.create_task(janitor())
    yield
    for job in jobs.values():job['cancel']=True
    cleanup.cancel();await asyncio.gather(cleanup,return_exceptions=True)

app=FastAPI(title='Context-aware AudioSet decision lab',lifespan=lifespan)
uploads_in_progress=0

def protected():
    return [active,jobs[active]['asset_id']] if active in jobs else []

def owner(request):
    token=request.cookies.get(COOKIE,'')
    if len(token)!=64 or any(c not in '0123456789abcdef' for c in token):raise HTTPException(401,'Open the lab page to create a private session first.')
    return storage.owner_key(token)

@app.middleware('http')
async def privacy(request,call_next):
    global uploads_in_progress
    origin=request.headers.get('origin')
    if origin and origin.split('://',1)[-1]!=request.headers.get('host'):
        return JSONResponse({'detail':'Cross-origin requests are not accepted'},status_code=403)
    if request.method in ('POST','DELETE') and not request.url.path.startswith('/internal/') and request.headers.get('x-audio-decision')!='1':
        return JSONResponse({'detail':'Missing same-origin request header'},status_code=403)
    is_upload=request.url.path=='/api/upload' and request.method=='POST'
    if is_upload and uploads_in_progress>=2:return JSONResponse({'detail':'Two uploads are already being decoded; try again shortly.'},status_code=429)
    if is_upload:uploads_in_progress+=1
    try:response=await call_next(request)
    finally:
        if is_upload:uploads_in_progress-=1
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
    return response

@app.post('/api/session')
async def session(request:Request):
    token=request.cookies.get(COOKIE,'')
    if len(token)!=64 or any(c not in '0123456789abcdef' for c in token):token=secrets.token_hex(32)
    response=JSONResponse({'ok':True,'retention_seconds':storage.TTL})
    response.set_cookie(COOKIE,token,max_age=86400,httponly=True,secure=request.headers.get('x-forwarded-proto')=='https',samesite='strict',path=cookie_path)
    return response

@app.get('/api/status')
async def status():
    return {'model':MODEL,'revision':REVISION,'device':engine.device,'loaded':engine.model is not None,'load_ms':engine.load_ms,'busy':active is not None,
        'precision':'BF16','compiled':engine.compiled,'group_default':16,'taxonomy_counts':{'strong':456,'classic':527},
        'score_label':'Official d1 model scores; release calibration is included, but no AudioSet/short-interval calibration has been evaluated.',
        'max_duration_s':120,'max_upload_mb':32,'retention_s':storage.TTL,'real_time_guaranteed':False}

@app.get('/api/taxonomy')
async def taxonomy():return TAXONOMY

async def command(*args):
    p=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:out,err=await asyncio.wait_for(p.communicate(),40)
    except asyncio.TimeoutError:p.kill();await p.wait();raise ValueError('Audio decoding timed out')
    if p.returncode:raise ValueError('Audio cannot be decoded; try WAV, MP3, M4A, OGG, FLAC or WebM')
    return out

def audio_metadata(wave,filename,source=None):
    peaks=[float(np.max(np.abs(x))) for x in np.array_split(wave,min(1800,len(wave))) if len(x)]
    return {'filename':filename[:180],'duration_s':len(wave)/16000,'model_sample_rate':16000,'model_channels':1,
        'source':source or {'sample_rate':16000,'channels':1,'codec_name':'pcm_s16le'},'waveform_peaks':peaks,
        'sha256':hashlib.sha256(wave.astype('<f4').tobytes()).hexdigest(),'created':time.time()}

@app.post('/api/upload')
async def upload(request:Request):
    own=owner(request);storage.expire(protected())
    if len(list((storage.ROOT/own).glob('*/audio.json')))>=12:raise HTTPException(429,'Delete an older recording before uploading another.')
    identifier,folder=storage.create(own);source=folder/'input';size=0
    try:
        with source.open('wb') as f:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>UPLOAD_LIMIT:raise ValueError('Maximum upload is 32 MB')
                f.write(chunk)
        if not size:raise ValueError('Empty upload')
        formats='wav,mp3,mov,ogg,matroska,webm,flac,aac'
        raw=await command('ffprobe','-v','error','-protocol_whitelist','file,pipe','-format_whitelist',formats,'-show_entries','stream=codec_type,sample_rate,channels,codec_name','-of','json',str(source))
        streams=json.loads(raw)['streams'];meta=next((s for s in streams if s.get('codec_type')=='audio'),None)
        if not meta:raise ValueError('No audio track')
        decoded=await command('ffmpeg','-v','error','-nostdin','-protocol_whitelist','file,pipe','-format_whitelist',formats,'-i',str(source),'-t','120.1','-vn','-ac','1','-ar','16000','-f','f32le','pipe:1')
        wave=np.frombuffer(decoded,dtype='<f4').copy()
        if not 0<len(wave)<=MAX_SAMPLES or not np.isfinite(wave).all():raise ValueError('Use finite audio between 0 and 120 seconds')
        from urllib.parse import unquote
        metadata=audio_metadata(wave,Path(unquote(request.headers.get('x-filename','recording'))).name,meta)
        sf.write(folder/'audio.wav',wave,16000,subtype='PCM_16');os.chmod(folder/'audio.wav',0o600)
        # Analyze the exact stored PCM, making cache identity and later playback agree.
        stored=sf.read(folder/'audio.wav',dtype='float32')[0];metadata['sha256']=hashlib.sha256(stored.astype('<f4').tobytes()).hexdigest()
        storage.write(folder/'audio.json',metadata)
        return {'asset_id':identifier,**metadata}
    except ValueError as exc:
        import shutil;shutil.rmtree(folder,ignore_errors=True);raise HTTPException(422,str(exc))
    finally:source.unlink(missing_ok=True)

def asset(own,identifier):
    try:
        p=storage.directory(own,identifier)
        os.utime(p,None)
        return p,json.loads((p/'audio.json').read_text())
    except (FileNotFoundError,ValueError):raise HTTPException(404,'Private recording expired or not found')

@app.get('/api/audio/{identifier}')
async def audio(identifier:str,request:Request):
    folder,_=asset(owner(request),identifier);return FileResponse(folder/'audio.wav',media_type='audio/wav',headers={'Cache-Control':'no-store'})

@app.get('/api/library')
async def library(request:Request):
    own=owner(request);storage.expire(protected());assets=[];results=[]
    for f in (storage.ROOT/own).glob('*/audio.json'):assets.append({'asset_id':f.parent.name,**json.loads(f.read_text())})
    for f in (storage.ROOT/own).glob('*/result.json'):
        r=json.loads(f.read_text());results.append({'job_id':f.parent.name,'asset_id':r['asset_id'],'settings':r['settings'],'state':r['state'],'created':r['created']})
    return {'assets':assets,'results':results}

@app.delete('/api/library')
async def erase(request:Request):
    own=owner(request)
    if any(j['owner']==own and j['state']=='running' for j in jobs.values()):raise HTTPException(409,'Stop the active analysis first')
    import shutil;shutil.rmtree(storage.ROOT/own,ignore_errors=True)
    for k,j in list(jobs.items()):
        if j['owner']==own:jobs.pop(k)
    return {'deleted':True}

async def gpu():
    try:lease=Lease().acquire()
    except OptionalLabBusy as exc:raise HTTPException(409,str(exc))
    try:
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                r=await client.post('http://127.0.0.1:8810/internal/offload');r.raise_for_status()
        except httpx.ConnectError:pass  # Optional AV lab may be stopped entirely.
        await asyncio.to_thread(engine.load)
        return lease
    except Exception:
        lease.release();raise

@app.post('/internal/offload')
async def offload():
    if active is not None:raise HTTPException(409,'Decision lab is active')
    await asyncio.to_thread(engine.unload);return {'offloaded':True}

def blank(start,end,count,status='not_evaluated'):
    return {'start_s':start,'end_s':end,'raw':[None]*count,'status':status,'inference_ms':None,'failures':[]}

def snapshot(job):
    rows=job['rows'];smooth,events=process_rows(rows,job['classes'],job['settings'])
    return {k:v for k,v in job.items() if k not in ('owner','task','cancel','lease')}|{'smoothed_scores':smooth,'raw_scores':[r['raw'] for r in rows],'events':events,
        'model':MODEL,'model_revision':REVISION,'prompt_version':PROMPT_VERSION,'calibration':'Official release calibration only; not empirically calibrated for this taxonomy and short target windows.',
        'smoothing_note':'Causal EMA/hysteresis, never acoustic evidence. Missing intervals remain null and reset state.',
        'completed_at':time.time()}

def save(job):
    storage.write(storage.directory(job['owner'],job['job_id'])/'result.json',snapshot(job))
    with contextlib.suppress(FileNotFoundError):os.utime(storage.directory(job['owner'],job['asset_id']),None)

def feedback(job):
    for row in reversed(job['rows']):
        scored=[(x,c['name']) for x,c in zip(row['raw'],job['classes']) if x is not None and x>=.6]
        if scored:return {'interval':[row['start_s'],row['end_s']],'top_events':[name for _,name in sorted(scored,reverse=True)[:3]],'unverified_model_estimates':True}
    return None

async def evaluate(wave,target,job):
    out=await asyncio.to_thread(engine.analyze,wave,target,job['classes'],job['settings'],feedback(job))
    return {'raw':[out['scores'][c['id']] for c in job['classes']],'inference_ms':out['inference_ms'],'status':'partial' if out['failures'] else 'evaluated',
        'failures':out['failures'],'performance':{k:out[k] for k in ('reuse','input_tokens','allocated_mb','reserved_mb','groups')}}

def admit(own):
    global active
    if active is not None:raise HTTPException(409,'One GPU analysis is already running. Stop it or wait.')
    times=[x for x in starts.get(own,[]) if time.time()-x<3600]
    if len(times)>=12:raise HTTPException(429,'Hourly analysis limit reached')
    starts[own]=times+[time.time()]
    identifier,_=storage.create(own);active=identifier;return identifier

def new_job(own,identifier,asset_id,metadata,settings,mode):
    return {'owner':own,'job_id':identifier,'asset_id':asset_id,'audio':metadata,'settings':settings.model_dump(),'classes':settings.classes(),
        'state':'running','mode':mode,'rows':[],'created':time.time(),'cancel':False,'error':None,'metrics':{'dropped_intervals':0,'evaluated_intervals':0}}

class Analyze(BaseModel):
    asset_id:str
    settings:Settings

@app.post('/api/analyze')
async def analyze(body:Analyze,request:Request):
    own=owner(request);folder,metadata=asset(own,body.asset_id);cachekey=storage.key(metadata['sha256'],body.settings.model_dump())
    for f in (storage.ROOT/own).glob('*/result.json'):
        old=json.loads(f.read_text())
        if old.get('cache_key')==cachekey and old['state']=='done':
            return {'job_id':f.parent.name,'cached':True,'state':'done'}
    identifier=admit(own);job=new_job(own,identifier,body.asset_id,metadata,body.settings,'file');job['cache_key']=cachekey;jobs[identifier]=job
    job['task']=asyncio.create_task(run_file(job,folder/'audio.wav'))
    return JSONResponse({'job_id':identifier,'cached':False,'state':'running'},status_code=202)

async def run_file(job,path):
    global active
    lease=None;started=time.perf_counter();last_save=0
    try:
        lease=await gpu();job['model_load_ms']=engine.load_ms;wave=await asyncio.to_thread(lambda:sf.read(path,dtype='float32')[0]);s=job['settings']
        for i,a,b in intervals(len(wave),s['hop_ms']):
            row=blank(a/16000,b/16000,len(job['classes']))
            if job['cancel'] or time.perf_counter()-started>7200:
                row['status']='cancelled';job['rows'].append(row);continue
            lo=max(0,b-round(s['window_s']*16000));row.update(await evaluate(wave[lo:b],b-a,job));row['history_start_s']=lo/16000
            job['rows'].append(row);job['metrics']['evaluated_intervals']+=1
            if time.monotonic()-last_save>10:save(job);last_save=time.monotonic()
        job['state']='cancelled' if job['cancel'] or any(r['status']=='cancelled' for r in job['rows']) else 'done'
        failures=sum(len(r.get('failures',[])) for r in job['rows'])
        if failures and job['state']=='done':job['state']='partial';job['error']=f'{failures} question groups failed. Missing scores are null; retry to evaluate them.'
    except Exception as exc:
        job['state']='failed';job['error']=str(exc.detail) if isinstance(exc,HTTPException) else type(exc).__name__+': '+str(exc)[:180]
    finally:
        job['metrics']['wall_ms']=(time.perf_counter()-started)*1000;save(job)
        if lease:lease.release()
        active=None;job.pop('task',None)

def get_job(own,identifier):
    if identifier in jobs and jobs[identifier]['owner']==own:
        with contextlib.suppress(FileNotFoundError):os.utime(storage.directory(own,identifier),None)
        return jobs[identifier]
    try:
        result=json.loads((storage.directory(own,identifier)/'result.json').read_text())
        if result['state']=='running':result['state']='interrupted';result['error']='Server restarted; partial results are retained.'
        return result
    except (FileNotFoundError,ValueError):raise HTTPException(404,'Private analysis expired or not found')

@app.get('/api/jobs/{identifier}')
async def get_result(identifier:str,request:Request,since:int=0):
    if since<0:raise HTTPException(422,'Invalid offset')
    j=get_job(owner(request),identifier)
    return {k:j[k] for k in ('job_id','asset_id','state','mode','settings','classes','audio','metrics','error')}|{'rows':j['rows'][since:],'offset':since,'row_count':len(j['rows'])}

@app.delete('/api/jobs/{identifier}')
async def cancel(identifier:str,request:Request):
    j=get_job(owner(request),identifier)
    if identifier in jobs:j['cancel']=True
    return {'stop_requested':True}

@app.get('/api/export/{identifier}')
async def export(identifier:str,request:Request,format:str='json',smooth:bool=False):
    job=get_job(owner(request),identifier);result=snapshot(job)
    if format=='json':return JSONResponse(result,headers={'Content-Disposition':'attachment; filename="audio-decision.json"'})
    if format=='csv':return Response(csv_export(result,smooth),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="audio-decision.csv"'})
    raise HTTPException(422,'Choose json or csv')

@app.websocket('/ws')
async def live(ws:WebSocket):
    global active
    if ws.headers.get('origin','').split('://',1)[-1]!=ws.headers.get('host'):
        await ws.close(code=1008);return
    try:own=owner(ws)
    except HTTPException:await ws.close(code=1008);return
    await ws.accept();identifier=None;lease=None;job=None;stopped=False;chunks=[];ring=deque();ring_samples=0;received=0;capture_ms={};changed=asyncio.Event();receiver=None;live_started=time.monotonic()
    try:
        message=await asyncio.wait_for(ws.receive_json(),15);settings=Settings.model_validate(message['settings']);identifier=admit(own)
        asset_id,folder=storage.create(own);metadata=audio_metadata(np.zeros(1,np.float32),'Live microphone.wav')
        job=new_job(own,identifier,asset_id,metadata,settings,'live');jobs[identifier]=job
        await ws.send_json({'type':'started','job_id':identifier,'classes':job['classes'],'settings':settings.model_dump()})
        async def receive():
            nonlocal stopped,received,ring_samples
            try:
                while not stopped and time.monotonic()-live_started<140:
                    try:m=await asyncio.wait_for(ws.receive(),15)
                    except asyncio.TimeoutError:break
                    if m['type']=='websocket.disconnect':break
                    if m.get('text'):
                        if json.loads(m['text']).get('type')=='stop':break
                    elif m.get('bytes') is not None:
                        b=m['bytes']
                        if len(b)<12 or (len(b)-8)%4 or len(b)>8+16000*4:raise ValueError('Invalid live packet')
                        sent=float(np.frombuffer(b[:8],'<f8')[0]);wave=np.frombuffer(b[8:],'<f4').copy()
                        if not math.isfinite(sent) or not np.isfinite(wave).all():raise ValueError('Nonfinite live packet')
                        if received+len(wave)>MAX_SAMPLES:break
                        chunks.append(wave);ring.append(wave);ring_samples+=len(wave);received+=len(wave);capture_ms[received]=sent
                        while ring and ring_samples-len(ring[0])>21*16000:ring_samples-=len(ring.popleft())
                        changed.set()
            finally:stopped=True;changed.set()
        receiver=asyncio.create_task(receive());lease=await gpu();job['model_load_ms']=engine.load_ms
        step=settings.hop_ms*16;last_index=-1;last_save=0
        while True:
            latest=received//step-1
            if latest<=last_index:
                if stopped:break
                changed.clear();await changed.wait();continue
            if job['cancel']:break
            end=(latest+1)*step;start=latest*step
            # Snapshot only past samples. Capture continues while the GPU thread runs.
            past=np.concatenate(ring);offset=received-len(past);lo=max(0,end-round(settings.window_s*16000));wave=past[lo-offset:end-offset].copy()
            near=min((n for n in capture_ms if n>=end),default=received);captured=capture_ms[near]-(near-end)/16
            for idx in range(last_index+1,latest):job['rows'].append(blank(idx*step/16000,(idx+1)*step/16000,len(job['classes']),'skipped'));job['metrics']['dropped_intervals']+=1
            row=blank(start/16000,end/16000,len(job['classes']));row.update(await evaluate(wave,step,job));row['history_start_s']=lo/16000
            job['rows'].append(row);last_index=latest;job['metrics']['evaluated_intervals']+=1
            await ws.send_json({'type':'result','row':row,'index':latest,'capture_end_client_ms':captured,'captured_until_s':received/16000,'metrics':job['metrics']})
            if time.monotonic()-last_save>10:save(job);last_save=time.monotonic()
            if stopped:break
        if receiver and not receiver.done():receiver.cancel();await asyncio.gather(receiver,return_exceptions=True)
        wave=np.concatenate(chunks) if chunks else np.zeros(0,np.float32)
        if not len(wave):
            import shutil
            shutil.rmtree(folder,ignore_errors=True)
            job['asset_id']=None;job['audio']={'filename':'No audio captured','duration_s':0,'waveform_peaks':[]}
            job['state']='cancelled';save(job)
            await ws.send_json({'type':'empty','job_id':identifier})
            return
        if len(wave):
            sf.write(folder/'audio.wav',wave,16000,subtype='PCM_16');os.chmod(folder/'audio.wav',0o600)
            metadata=audio_metadata(sf.read(folder/'audio.wav',dtype='float32')[0],'Live microphone.wav');storage.write(folder/'audio.json',metadata);job['audio']=metadata
            for idx,a,b in intervals(len(wave),settings.hop_ms):
                if idx>last_index:job['rows'].append(blank(a/16000,b/16000,len(job['classes']),'skipped'));job['metrics']['dropped_intervals']+=1
        failures=sum(len(r.get('failures',[])) for r in job['rows'])
        job['state']='partial' if failures else 'done'
        if failures:job['error']=f'{failures} question groups failed; affected scores are null.'
        save(job)
        await ws.send_json({'type':'done','job_id':identifier,'asset_id':asset_id,'audio':metadata,'metrics':job['metrics']})
    except Exception as exc:
        if job:
            job['state']='failed';job['error']=type(exc).__name__+': '+str(exc)[:180];save(job)
        with contextlib.suppress(Exception):await ws.send_json({'type':'error','message':str(exc.detail) if isinstance(exc,HTTPException) else type(exc).__name__+': '+str(exc)[:180]})
    finally:
        if receiver and not receiver.done():receiver.cancel();await asyncio.gather(receiver,return_exceptions=True)
        if lease:lease.release()
        if identifier:active=None
        with contextlib.suppress(Exception):await ws.close()

app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='ui')
