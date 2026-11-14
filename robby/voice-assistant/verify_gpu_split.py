"""Public HTTPS typed + synthetic browser microphone smoke test after deployment.

Uses a fresh isolated browser profile and an existing authored wake-phrase audio
fixture. Exercises actual WebAudio capture, ASR, hosted LLM, TTS and playback.
Does not test a physical microphone, webcam or acoustic echo in a real room.
"""
import asyncio
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
URL='https://diane-asylum-understood-invoice.trycloudflare.com/desk-robot/'
REPORT=ROOT/'logs/gpu-split-browser-verification.json'
INIT="""localStorage.setItem('robby.autoStartDefaultVersion','1');
localStorage.setItem('robby.autoStart','false');
localStorage.setItem('robby.cameraAutoVersion','3');
localStorage.setItem('robby.cameraAuto','false');
localStorage.setItem('robby.avatar-idle-enabled','false');
localStorage.setItem('robby.avatar-pet-invites-enabled','false');
localStorage.setItem('robby.memoryDefaultVersion','1');
localStorage.setItem('robby.memorySettings',JSON.stringify({enabled:false}));"""

def state(port,path):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=5) as r:
        return json.load(r)

async def wait_ready():
    previous=None
    # A new physical GPU/index can require a cold Inductor autotuning pass.
    # This limit includes compilation, not the latency of a ready speech turn.
    for _ in range(600):
        try:
            s=await asyncio.to_thread(state,8792,'/api/state')
            if s.get('error'):raise RuntimeError(s['error'])
            if s.get('ready') and not s.get('busy'):return
            phase=s.get('phase')
        except (OSError,TimeoutError):phase='waiting for TTS HTTP'
        if phase!=previous:print('TTS: '+str(phase),flush=True);previous=phase
        await asyncio.sleep(3)
    raise TimeoutError('TTS startup did not complete')

async def exercise(browser,microphone=False):
    ctx=await browser.new_context(viewport={'width':1280,'height':1000})
    page=await ctx.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    await page.add_init_script(INIT)
    result={'case':'synthetic_microphone' if microphone else 'typed_reply','url':URL,'passed':False}
    try:
        response=await page.goto(URL,timeout=60000)
        result['https_status']=response.status
        assert response.status==200
        await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled',timeout=90000)
        await page.evaluate('''()=>{
            window.splitEvents=[];window.splitAudio=[];window.splitStart=performance.now();
            const msg=robo.on.message,play=robo.play.bind(robo);
            robo.on.message=m=>{if(['ready','endpoint','reply','turn_done','error','busy','ignored','pipeline_metrics','avatar_action'].includes(m.type))splitEvents.push({...m,at:performance.now()-splitStart});msg(m)};
            robo.play=b=>{let energy=0;const pcm=new Int16Array(b,4);for(const x of pcm)energy+=(x/32768)**2;
                splitAudio.push({at:performance.now()-splitStart,samples:pcm.length,rms:Math.sqrt(energy/pcm.length)});play(b)};
        }''')
        if microphone:
            # Browser's real capture/worklet pipeline, fed an authored WAV by
            # Chromium's fake-device switch. No direct socket injection.
            await page.evaluate('robo.start(true)')
        else:
            await page.locator('#message').fill('Erkläre mir in zwei Sätzen, warum der Himmel blau ist. Schau dabei fröhlich.')
            await page.locator('#form').evaluate('f=>f.requestSubmit()')
        await page.wait_for_function('splitEvents.some(e=>e.type==="turn_done"||e.type==="error"||e.type==="busy")',timeout=150000)
        await page.wait_for_function('robo.sources.length===0',timeout=60000)
        result.update(await page.evaluate('''()=>({events:splitEvents,audio:splitAudio,
            metrics:robo.metrics,context_state:robo.ctx?.state,
            audio_clock_s:robo.ctx?.currentTime,capture_blocks:robo.captureBlocks||0,
            view:document.body.dataset.robotView,
            llm:localStorage.getItem('robby.llmSelection'),
            asr:localStorage.getItem('robby.asrModel')})'''))
        assert not errors,errors
        assert not any(e['type'] in ('error','busy') for e in result['events']),result['events']
        assert any(e['type']=='reply' for e in result['events']),'No reply'
        assert result['audio'] and max(x['rms'] for x in result['audio'])>.005,'No audible PCM'
        assert result['context_state']=='running' and result['audio_clock_s']>1,'Playback clock stalled'
        if microphone:
            assert result['capture_blocks']>100 and result['metrics']['mic_blocks']>100
            assert any(e['type']=='endpoint' and e.get('transcript') for e in result['events']),'ASR did not submit'
        else:
            assert sum(e['type']=='reply' for e in result['events'])>=2,'Two-sentence response incomplete'
        result['passed']=True
        await page.screenshot(path=str(ROOT/'logs'/('gpu-split-mic.png' if microphone else 'gpu-split-demo.png')))
    except Exception as e:
        result['error']=repr(e)
        try:result['events']=await page.evaluate('window.splitEvents||[]')
        except Exception:pass
    finally:
        result['page_errors']=errors
        try:await page.evaluate('window.robo?.stop()')
        except Exception:pass
        await ctx.close()
    print(json.dumps({k:v for k,v in result.items() if k in ('case','passed','error','https_status','capture_blocks')},ensure_ascii=False),flush=True)
    return result

async def main():
    report={'started':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'url':URL,'passed':False,'cases':[],
            'limitation':'Authored synthetic microphone, not physical microphone/webcam/room acoustics.'}
    await wait_ready()
    report['podcast_before']=state(8816,'/health')['jobs']
    with tempfile.TemporaryDirectory(prefix='robby-gpu-split-') as tmp:
        wav=Path(tmp)/'wake.wav'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(ROOT/'logs/wake-short.mp3'),
                        '-af','adelay=2000,apad=pad_dur=170','-ar','48000','-ac','1','-c:a','pcm_s16le',str(wav)],check=True)
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=[
                '--no-sandbox','--disable-gpu','--mute-audio','--autoplay-policy=no-user-gesture-required',
                '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
                '--use-file-for-fake-audio-capture='+str(wav)])
            try:
                report['cases'].append(await exercise(browser))
                REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False))
                await asyncio.sleep(2)
                report['cases'].append(await exercise(browser,microphone=True))
            finally:await browser.close()
    report['podcast_after']=state(8816,'/health')['jobs']
    report['passed']=all(c['passed'] for c in report['cases'])
    REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('Report: '+str(REPORT),flush=True)
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
