"""Authored real-model checks for the Nov 2026 pause/retry repair.

No private recordings. Run serially on this shared service. Unit SSE failures
live in test_speech_retry.py; this file only calls real TTS, ASR and Chromium.
"""
import asyncio,json,time,tempfile
from pathlib import Path
import httpx,numpy as np,soundfile as sf
from scipy.signal import resample_poly
from playwright.async_api import async_playwright
from bolt_pipeline import pipeline
from bolt_text import Sentence
from verify_gpu_split import INIT,URL,exercise

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'logs/turn-reliability';OUT.mkdir(exist_ok=True)

async def ready():
    last=None
    async with httpx.AsyncClient(timeout=10) as client:
        for _ in range(600):
            try:
                states=[(await client.get(f'http://127.0.0.1:{port}/api/state')).json() for port in (8792,8793)]
                phase=[s.get('phase') for s in states]
                if phase!=last:print('Readiness:',phase,flush=True);last=phase
                if all(s.get('ready') for s in states) and not states[0].get('busy'):return
                if any(s.get('error') for s in states):raise RuntimeError('Worker startup error; inspect private service log')
            except httpx.TransportError:pass
            await asyncio.sleep(2)
    raise TimeoutError('Services not ready')

async def speech_checks():
    rows=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8792',timeout=180) as client:
        for name,lang,texts in [
            ('de_conversation','de',["Mir geht's prima, Christoph!",'Heute können wir gemeinsam etwas Neues entdecken.']),
            ('de_numbers','de',['Zwei kleine Roboter sitzen auf einer Bank.','Sie erzählen sich ganz entspannt eine lustige Geschichte.']),
            ('en_conversation','en',["I'm happy to see you.",'Let us discover something new together today.'])]:
            row={'case':name,'sentences':texts,'passed':False};waves=[];notices=[];start=time.perf_counter()
            try:
                async for kind,value in pipeline(client,'Read these sentences.',{},[],
                        preset=[Sentence(t,'interest, gentle, natural',language=lang) for t in texts]):
                    if kind=='audio':waves.append(value.copy())
                    elif kind=='status':notices.append(value)
                    elif kind=='done':row['metrics']=value
                wave=np.concatenate(waves);sf.write(OUT/(name+'.wav'),wave,24000)
                row.update(audio_s=len(wave)/24000,rms=float(np.sqrt(np.mean(wave**2))),notices=notices)
                assert row['rms']>.002 and row['metrics']['sentences']==len(texts)
                row['passed']=True
            except Exception as exc:row['error']=str(exc)
            row['wall_s']=round(time.perf_counter()-start,3);rows.append(row)
            (OUT/'tts.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False))
            print('TTS:',name,row['passed'],row.get('error'),len(notices),'retries',flush=True)
    return rows

async def microphone_check(p,name,pause_ms,gap,gain,noise=False):
    a=np.load(ROOT/'logs/speech-pause/first.npy');b=np.load(ROOT/'logs/speech-pause/second.npy')*gain
    clip=np.r_[a,np.zeros(round(gap*16000)),b].astype(np.float32)
    if noise:clip+=np.random.default_rng(42).normal(0,.001,len(clip)).astype(np.float32)
    wave=np.r_[np.zeros(5*16000),clip,np.zeros(35*16000)].astype(np.float32)
    row={'case':name,'pause_ms':pause_ms,'internal_gap_s':gap,'second_gain':gain,'passed':False,'physical_microphone':False}
    with tempfile.TemporaryDirectory(prefix='robby-pause-check-') as tmp:
        wav=Path(tmp)/'input.wav';sf.write(wav,resample_poly(wave,3,1),48000,subtype='PCM_16')
        browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=[
            '--no-sandbox','--disable-gpu','--mute-audio','--autoplay-policy=no-user-gesture-required',
            '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str(wav)])
        page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.add_init_script(INIT+f"localStorage.setItem('robby.speechPauseMs','{pause_ms}');"+
            "localStorage.setItem('robby.wakeMode','false');localStorage.setItem('robby.conversationFocus','false');"+
            "localStorage.setItem('robby.ttsModel','small_rl');")
        try:
            r=await page.goto(URL,timeout=60000);assert r.status==200
            await page.wait_for_function('window.robo&&!document.querySelector("#call").disabled',timeout=90000)
            await page.evaluate('''()=>{window.reliabilityEvents=[];const old=robo.on.message;
                robo.on.message=m=>{if(['asr_sentence','endpoint','reply','turn_done','error','asr_settings','service_status'].includes(m.type))
                    reliabilityEvents.push({...m,wall_ms:performance.now()});old(m)};}''')
            await page.evaluate('robo.start(true)')
            await page.evaluate(f"robo.send('wake:off');robo.send('identity:focus:enabled:off');robo.send('asr:pause_ms:{pause_ms}')")
            await page.wait_for_function('reliabilityEvents.some(e=>e.type==="turn_done"||e.type==="error")',timeout=90000)
            row['events']=await page.evaluate('reliabilityEvents')
            submitted=[e for e in row['events'] if e['type']=='asr_sentence']
            assert len(submitted)==1,[(e.get('text'),e.get('observed_quiet_ms')) for e in submitted]
            assert submitted[0]['observed_quiet_ms']>=pause_ms,submitted
            text=submitted[0]['text'].casefold()
            assert 'gemeinsam machen' in text and 'spiel vor' in text,text
            assert not [e for e in row['events'] if e['type']=='error'],row['events']
            await page.wait_for_function('robo.metrics.chunks>0',timeout=15000)
            row['audio_chunks']=await page.evaluate('robo.metrics.chunks')
            assert not errors,errors
            row['passed']=True
        except Exception as exc:
            row['error']=str(exc)
            try:row['events']=await page.evaluate('window.reliabilityEvents||[]')
            except Exception:pass
        finally:
            row['page_errors']=errors
            try:await page.evaluate('window.robo?.stop()')
            except Exception:pass
            await browser.close()
    print('Browser:',name,row['passed'],row.get('error','')[:500],flush=True)
    return row

async def main():
    await ready()
    report={'tts':await speech_checks(),'browser':[],'public_url':URL}
    target=OUT/'report.json';target.write_text(json.dumps(report,indent=2,ensure_ascii=False))
    async with async_playwright() as p:
        for args in [('quieter_continuous_speech',300,.12,.2,False),('noise_and_longer_pause',1000,.5,.5,True)]:
            report['browser'].append(await microphone_check(p,*args))
            target.write_text(json.dumps(report,indent=2,ensure_ascii=False));await asyncio.sleep(2)
        browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--mute-audio','--autoplay-policy=no-user-gesture-required'])
        report['browser'].append(await exercise(browser));await browser.close()
    report['passed']=all(r['passed'] for r in report['tts']+report['browser'])
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print('PASSED',report['passed'],flush=True)
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
