"""Request-scoped MiniCPM-o 4.5 GGUF AV inference via private loopback WS."""
import asyncio,base64,contextlib,json,os,re,socket,time
from pathlib import Path
import aiohttp
ROOT=Path(__file__).resolve().parent
BINARY='/mnt/raid/robby-models/llama-omni-build124/bin/llama-omni-server'
MODEL='/mnt/raid/robby-models/MiniCPM-o-4_5-gguf-q4/MiniCPM-o-4_5-Q4_K_M.gguf'
SYSTEM=('Analyze the original audio and video together in English. Describe foreground and background, '
 'intelligible speech, music only when audible, sounds, objects and people. Describe visible expressions, '
 'gestures, gaze, movements and changes without inventing hidden intentions, identities or inaudible words. '
 'Return one JSON object with foreground, background, observations [{category,description,relevance}], '
 'people [{id,description}], events [{start_s,end_s,person_id,kind,description,relevance}]. '
 'Relevance is 0, 1 or 2; times are approximate seconds relative to this window, or null if uncertain. '
 'Previous observations may be incorrect; use them only to maintain labels when evidence supports it. '
 'Situation context is for relevance only and is not evidence of sounds or visual events.')

async def analyze(normalized,tmp,starts,window,context,cmd):
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    tmpdir=tmp/'minicpm-runtime';tmpdir.mkdir()
    env={**os.environ,'CUDA_VISIBLE_DEVICES':os.getenv('MINICPM_GPU','1'),'TMPDIR':str(tmpdir)}
    # Setting fewer GPU layers is an explicit operator-controlled CPU offload.
    layers=os.getenv('MINICPM_N_GPU_LAYERS','99')
    p=await asyncio.create_subprocess_exec(BINARY,'--host','127.0.0.1','--port',str(port),'-m',MODEL,'-ngl',layers,'-c','4096','-t','6','--no-webui',cwd=str(tmpdir),env=env,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
    started=time.perf_counter();previous=[];results=[];load_ms=None
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=240)) as c:
            for _ in range(180):
                if p.returncode is not None:raise RuntimeError('MiniCPM server stopped during startup')
                try:
                    async with c.get(f'http://127.0.0.1:{port}/health',timeout=1) as r:
                        if r.status==200:break
                except (aiohttp.ClientError,asyncio.TimeoutError):pass
                await asyncio.sleep(.5)
            else:raise RuntimeError('MiniCPM server startup timed out')
            for i,start in enumerate(starts):
                clip=tmp/f'minicpm-{i}.mp4';fps=8/max(window,.1)
                await cmd('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(normalized),'-t',str(window),'-vf',f'fps={fps:.4f},scale=320:240:force_original_aspect_ratio=decrease','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-ar','16000','-ac','1',str(clip))
                frame_data=base64.b64encode(clip.read_bytes()).decode('ascii');one=time.perf_counter()
                async with c.ws_connect(f'http://127.0.0.1:{port}/backend',max_msg_size=16*1024*1024,timeout=180) as ws:
                    await ws.send_json({'type':'session.init','payload':{'mode':'turn_based','use_tts':False}})
                    event=await ws.receive_json(timeout=180)
                    if event.get('type')!='session.created':raise RuntimeError('MiniCPM session failed to initialize')
                    if load_ms is None:load_ms=round((time.perf_counter()-started)*1000,1)
                    prompt='Describe this audio-video window. Context: '+json.dumps(context,ensure_ascii=False)[:1000]+' Previous windows: '+json.dumps(previous[-2:],ensure_ascii=False)[:1500]
                    await ws.send_json({'type':'input.append','input':{'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':[{'type':'text','text':prompt},{'type':'video','data':frame_data,'stack_frames':8}]}],'streaming':False,'generation':{'max_new_tokens':320},'enable_thinking':False}})
                    while True:
                        event=await ws.receive_json(timeout=180)
                        if event.get('type')=='session.closed':raise RuntimeError('MiniCPM closed session: '+str(event.get('reason','unknown'))[:100])
                        if event.get('type')=='response.done':break
                raw=str(event.get('text') or '').strip();clean=re.sub(r'^```(?:json)?\s*|\s*```$','',raw).strip()
                try:parsed=json.loads(clean);assert isinstance(parsed,dict);wrapped=False
                except (ValueError,AssertionError):
                    # Preserve an unstructured response without inventing
                    # separate audio/video observations or confidence scores.
                    parsed={'observations':[{'category':'audio_visual','description':raw,'relevance':None}],
                            'format_warning':'Model returned prose; this is one unstructured observation.'} if raw else None
                    wrapped=parsed is not None
                if parsed is not None:
                    from lfm3_timeline import normalize_timeline
                    from lfm3_context import flag_context_echo
                    parsed=flag_context_echo(normalize_timeline(parsed,start,window,fps=fps),context)
                metrics=event.get('metrics',{});generation=float(metrics.get('generate_ms',0));prefill=float(metrics.get('prefill_ms',0))
                result={'model':'MiniCPM-o 4.5 Q4','annotation':parsed,'parse_ok':parsed is not None,'parse_repaired':wrapped,
                  'raw_text':raw if parsed is None or wrapped else None,'preprocess_ms':round(prefill,1),'generation_ms':round(generation,1),
                  'total_ms':round((time.perf_counter()-one)*1000,1),'output_tokens':None,'output_tokens_per_s':None,
                  'model_calls':1,'sampling_fps':round(fps,2),'reported_vision_slices':metrics.get('vision_slices'),
                  'note':'Model time estimates are approximate; token counts are not independently verified.'}
                results.append(result);previous.append({'start_s':start,'observation':parsed if parsed is not None else raw});clip.unlink(missing_ok=True)
        return {'status':'ok','load_ms':load_ms,'total_ms':round((time.perf_counter()-started)*1000,1),'windows':results}
    finally:
        if p.returncode is None:
            p.terminate()
            with contextlib.suppress(Exception):await asyncio.wait_for(p.wait(),10)
            if p.returncode is None:p.kill();await p.wait()
