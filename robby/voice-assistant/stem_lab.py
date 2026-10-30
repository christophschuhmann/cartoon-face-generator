"""Optional, isolated stem branch for the audio/video lab."""
import asyncio,base64,contextlib,json,os,time,sys
from pathlib import Path
import numpy as np
import soundfile as sf
import httpx
from scipy.signal import resample_poly

ROOT=Path(__file__).resolve().parent
# Absolute RMS in normalized PCM (-40 dBFS); keep this separate from the
# much lower sound-caption threshold. It does not establish speech presence.
ASR_MIN_RMS=0.01

async def transcribe_speech(client,sound):
    wave=np.asarray(sound,dtype=np.float32)
    rms=float(np.sqrt(np.mean(wave.astype(np.float64)**2))) if wave.size else 0.
    if not np.isfinite(rms) or rms<ASR_MIN_RMS:
        return {'status':'skipped','reason':'Too quiet for Parakeet (RMS below -40 dBFS).','rms':round(rms,6) if np.isfinite(rms) else None,'minimum_rms':ASR_MIN_RMS}
    begin=time.perf_counter()
    try:
        state=(await client.get('http://127.0.0.1:8801/models')).json()
        if state.get('active_gpu_model')!='parakeet_v3':raise ValueError('Parakeet is not already active; skipped to avoid changing the conversation recognizer.')
        response=await client.post('http://127.0.0.1:8801/transcribe/parakeet_v3',content=resample_poly(wave,1,3).astype('<f4').tobytes());response.raise_for_status()
        result=response.json();result['request_ms']=round((time.perf_counter()-begin)*1000,1);return result
    except (httpx.HTTPError,ValueError) as e:return {'status':'unavailable','reason':str(e)[:120]}

async def analyze(normalized,tmp,starts,window,model,two_speakers,cmd):
    env={**os.environ,'PYTHONPATH':':'.join((str(ROOT/'vendor/tuss'),'/mnt/nvme/moss-15-v2/tuss-env',str(ROOT/'vendor/bandit-infer/src'))),'PYTHONUNBUFFERED':'1'}
    worker=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'stem_separation_worker.py'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=None,env=env,limit=1024*1024)
    started=time.perf_counter();results=[]
    try:
        ready=json.loads(await asyncio.wait_for(worker.stdout.readline(),30))
        if not ready.get('ready'):raise RuntimeError('Separator worker is not ready')
        async with httpx.AsyncClient(timeout=45) as client:
            for index,start in enumerate(starts):
                folder=tmp/('stems-'+str(index));folder.mkdir();wav=folder/'mixture.wav'
                await cmd('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(normalized),'-t',str(window),'-vn','-ac','1','-ar','48000',str(wav))
                worker.stdin.write((json.dumps({'model':model,'path':str(wav),'outdir':str(folder),'two_speakers':two_speakers})+'\n').encode());await worker.stdin.drain()
                try:line=await asyncio.wait_for(worker.stdout.readline(),180)
                except asyncio.TimeoutError:raise RuntimeError('Separator exceeded 180 seconds per window')
                if not line:raise RuntimeError('Separator worker stopped')
                item=json.loads(line)
                if not item.get('ok'):raise RuntimeError(item.get('error','Separator failed'))
                item=item['result'];tracks=[]
                for label,path in item.pop('paths').items():
                    sound,_=sf.read(path,dtype='float32');level=item['rms'].get(label,0.)
                    mp3=folder/(label+'.mp3');await cmd('ffmpeg','-hide_banner','-loglevel','error','-y','-i',path,'-ac','1','-ar','16000','-b:a','64k',str(mp3))
                    row={'kind':label,'rms':round(level,6),'audio_mpeg_base64':base64.b64encode(mp3.read_bytes()).decode('ascii')}
                    if label in ('speech','music','effects','speaker_1','speaker_2'):
                        if level<0.001:row['caption']={'status':'skipped','reason':'Very quiet estimated stem; not proof that this source is absent.'}
                        else:
                            pcm=resample_poly(sound,1,3).astype('<f4');begin=time.perf_counter()
                            try:
                                response=await client.post('http://127.0.0.1:8803/caption',content=pcm.tobytes());response.raise_for_status();row['caption']=response.json()
                                row['caption']['request_ms']=round((time.perf_counter()-begin)*1000,1)
                            except (httpx.HTTPError,ValueError):row['caption']={'status':'unavailable','reason':'Shared captioner busy or unavailable.'}
                    if label in ('speech','speaker_1','speaker_2') and level>=0.001:
                        begin=time.perf_counter()
                        try:
                            response=await client.post('http://127.0.0.1:8802/caption?impression=1',content=resample_poly(sound,1,3).astype('<f4').tobytes());response.raise_for_status()
                            row['voice']=response.json();row['voice']['request_ms']=round((time.perf_counter()-begin)*1000,1)
                        except (httpx.HTTPError,ValueError):row['voice']={'status':'unavailable','reason':'Shared Humaneness Ears worker busy or unavailable.'}
                    if label in ('speech','speaker_1','speaker_2'):
                        row['asr']=await transcribe_speech(client,sound)
                    tracks.append(row)
                item['tracks']=tracks;item['start_s']=start;item['end_s']=round(start+item['input_s'],3)
                item['notes']=['Estimated categories can contain leakage or artifacts.', 'Speaker tracks, if requested, are tentative and not linked across windows.', 'Parakeet text has no verified word timings in this integration.']
                results.append(item)
    finally:
        if worker.returncode is None:
            worker.terminate()
            with contextlib.suppress(Exception):await asyncio.wait_for(worker.wait(),5)
            if worker.returncode is None:worker.kill();await worker.wait()
    return {'status':'ok','total_ms':round((time.perf_counter()-started)*1000,1),'windows':results}
