"""Real public browser timings on authored voices; no user recordings."""
import asyncio,base64,json,os
from pathlib import Path
from playwright.async_api import async_playwright
from browser_isolation_enrollment import MIC
from browser_input_isolation import INIT,URL
from benchmark_input_isolation import audio

async def main():
    label=os.environ.get('BENCH_LABEL','after');model=os.environ.get('ROBBY_FILTER_MODEL','voxlock')
    result={'label':label,'filter':model,'rows':[],'passed':False}
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required'])
        page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.add_init_script(INIT+MIC)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as ready_client:
                for _ in range(120):
                    try:
                        if (await ready_client.get('http://127.0.0.1:8793/api/state')).json().get('ready'):break
                    except Exception:pass
                    await asyncio.sleep(2)
                else:raise TimeoutError('Robby startup')
            await page.goto(URL+'/desk-robot/');await page.wait_for_function('window.robotFace?.inputIsolationControls && !document.querySelector("#call").disabled',timeout=180000)
            await page.evaluate('''async()=>{const {initialReserve,playbackStart}=await import('/static/client.js');
              if(initialReserve(1.1,.65)!==.18 || initialReserve(.16,.65)!==.35 || initialReserve(.16,.18,true)!==.22)throw Error('Reserve regression');
              if(playbackStart({sampleRate:48000,currentTime:2,baseLatency:.01},5,true,.18)!==5)throw Error('Playback clock regression');}''')
            await page.evaluate('window.playEvents=[];const old=robo.on.audio;robo.on.audio=m=>{playEvents.push({...m,at:performance.now()});old?.(m);};document.querySelector("#model-settings").open=true;')
            await page.select_option('#input-isolation-model',model)
            await page.wait_for_function('robotFace.inputIsolationControls.last?.phase==="waiting_reference"',timeout=120000)
            await page.click('#call');await page.wait_for_function('window.testMic && robo.metrics.mic_blocks>20')
            for name in ('christoph-intro','christoph-followup'):
                wave=audio(name);start=await page.evaluate('performance.now()')
                await page.evaluate('x=>testSpeak(x)',base64.b64encode(wave.astype('<f4').tobytes()).decode())
                end=await page.evaluate('performance.now()')
                await page.wait_for_function('(t)=>playEvents.some(e=>e.first && e.at>t) || filterEvents.some(e=>e.type==="error" && e.at>t)',arg=start,timeout=90000)
                failure=await page.evaluate('(t)=>filterEvents.find(e=>e.type==="error" && e.at>t)',start)
                if failure:
                    result['failure_event']=failure
                    raise RuntimeError('Real pipeline error: '+str(failure.get('error_type') or failure.get('stage') or 'unknown'))
                row=await page.evaluate('(t)=>({events:filterEvents.filter(e=>e.at>t && ["endpoint","asr_sentence","reply","turn_done","error"].includes(e.type)),pcm:playEvents.filter(e=>e.at>t),timing:Object.fromEntries([...document.querySelectorAll("[id^=latency-]")].map(x=>[x.id,x.textContent]))})',start)
                row.update(fixture=name,clip_s=len(wave)/16000,clip_end_perf_ms=end,
                           end_to_scheduled_audio_ms=row['pcm'][0]['at']+row['pcm'][0]['playback_lead_ms']-end)
                result['rows'].append(row)
                if name=='christoph-intro':
                    await page.wait_for_function('(t)=>filterEvents.some(e=>e.type==="turn_done" && e.at>t) && robo.sources.length===0',arg=start,timeout=90000)
                    await page.wait_for_function('robotFace.inputIsolationControls.last?.active',timeout=30000)
                    await page.wait_for_timeout(600)
            result['all_events']=await page.evaluate('filterEvents.filter(e=>["reply","error","asr_sentence","turn_done"].includes(e.type))')
            result['passed']=not errors and not any(e['type']=='error' for e in result['all_events'])
        except Exception as e:result['error']=str(e)
        finally:
            result['errors']=errors
            result['filter_state']=await page.evaluate('window.robotFace?.inputIsolationControls?.last')
            await page.evaluate('window.robo?.stop()');await browser.close()
            Path('logs/isolation-latency').mkdir(exist_ok=True)
            Path(f'logs/isolation-latency/browser-{label}-{model}.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'label':label,'passed':result['passed'],'error':result.get('error'),'rows':[{'fixture':r['fixture'],'end_to_audio_ms':r['end_to_scheduled_audio_ms'],'timing':r['timing']} for r in result['rows']]}),flush=True)
    if not result['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
