"""Real HTTPS browser + synthetic audio + actual ASR/LLM/TTS; no transcript injection."""
import argparse,asyncio,base64,json,subprocess,time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
FIXTURES=Path('/mnt/nvme/robo-speaker-studies/speaker-live-fixtures')

def samples(name):
    source=Path(name) if Path(name).is_file() else FIXTURES/(name+'.mp3')
    return subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(source),
        '-ar','16000','-ac','1','-f','f32le','pipe:1'],capture_output=True,check=True).stdout

async def main(url,name):
    result={'synthetic_microphone':True,'physical_microphone_test':False,'fixture':name,'passed':False}
    events=[];errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,
            args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
        page=await browser.new_page(viewport={'width':1280,'height':900})
        await page.add_init_script('''
          localStorage.setItem('robby.autoStartDefaultVersion','1');localStorage.setItem('robby.autoStart','false');
          localStorage.setItem('robby.cameraAutoVersion','3');localStorage.setItem('robby.cameraAuto','false');
          localStorage.setItem('robby.avatar-idle-enabled','false');
          navigator.mediaDevices.getUserMedia=async()=>{const ctx=window.robo.ctx,d=ctx.createMediaStreamDestination();
            window.testMic=d;const delay=ctx.createDelay(1),gain=ctx.createGain();
            delay.delayTime.value=.12;gain.gain.value=.05;robo.output.connect(delay);delay.connect(gain);gain.connect(d);return d.stream};
          window.testSpeak=async(encoded)=>{const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
            const x=new Float32Array(bytes.buffer),ctx=robo.ctx,b=ctx.createBuffer(1,x.length,16000);
            b.getChannelData(0).set(x);const s=ctx.createBufferSource();s.buffer=b;s.connect(testMic);
            await new Promise(resolve=>{s.onended=resolve;s.start()});s.disconnect()};''')
        def receive(raw):
            if isinstance(raw,str):
                item=json.loads(raw)
                if item.get('type') in ('reply','barge','reply_cancelled','stop_command','error','asr_preview','turn_done'):
                    events.append({'t':time.monotonic(),**item})
        page.on('websocket',lambda ws:ws.on('framereceived',receive))
        page.on('pageerror',lambda exc:errors.append(str(exc)))
        async def wait(pred,seconds):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                if pred():return
                await page.wait_for_timeout(100)
            raise TimeoutError('Timed out waiting for expected browser event')
        try:
            for _ in range(90):
                response=await page.goto(url)
                if response and response.status==200:break
                await page.wait_for_timeout(1000)
            else:raise TimeoutError('Demo did not become reachable')
            await page.wait_for_function('window.robo && !document.querySelector("#call").disabled',timeout=150000)
            await page.click('#call');await page.wait_for_function('window.testMic && robo.metrics.mic_blocks>30',timeout=30000)
            await page.fill('#message','Bitte erzähle mir eine längere freundliche Geschichte mit acht Sätzen über einen kleinen Roboter.')
            await page.locator('#form').evaluate('f=>f.requestSubmit()')
            await wait(lambda:any(x['type']=='reply' for x in events),90)
            await page.wait_for_function('robo.sources.length>0',timeout=90000)
            started=time.monotonic()
            await page.evaluate('x=>testSpeak(x)',base64.b64encode(samples(name)).decode())
            await wait(lambda:any(e['type']=='barge' and e['t']>=started for e in events),12)
            barge=next(e for e in events if e['type']=='barge' and e['t']>=started)
            await page.wait_for_timeout(500)
            matched=next((e for e in events if e['type']=='asr_preview' and e['t']>=started
                and any(w in e.get('text','').casefold() for w in ('stop','stopp','стоп','hör auf','hör bitte auf'))),None)
            result.update(passed=not errors and await page.evaluate('robo.sources.length===0'),
                command_to_barge_ms=round((barge['t']-started)*1000),
                first_stop_preview_ms=round((matched['t']-started)*1000) if matched else None,
                barge_after_stop_preview_ms=round((barge['t']-matched['t'])*1000) if matched else None,
                stop_sources=[e.get('source') for e in events if e['type']=='stop_command' and e['t']>=started],
                asr_previews=[e.get('text','') for e in events if e['type']=='asr_preview' and e['t']>=started],
                page_errors=errors)
        except Exception as exc:result.update(error=type(exc).__name__+': '+str(exc),page_errors=errors,
            asr_previews=[e.get('text','') for e in events if e['type']=='asr_preview'])
        finally:
            await page.evaluate('window.robo?.stop()');await browser.close()
    (ROOT/'logs'/('browser-instant-stop-'+Path(name).stem+'.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps(result,ensure_ascii=False),flush=True)
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='https://diane-asylum-understood-invoice.trycloudflare.com/desk-robot/')
    p.add_argument('--fixture',default='christoph-stop');a=p.parse_args();asyncio.run(main(a.url,a.fixture))
