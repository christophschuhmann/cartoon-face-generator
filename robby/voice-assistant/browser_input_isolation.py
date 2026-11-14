"""Public HTTPS, real CUDA workers, fake microphone through Chrome AudioWorklet.

The authored synthetic voice is the only recording. No real user data is saved.
Run with uv run --no-project --with playwright --python /path/to/venv/python.
"""
import asyncio,json,os,tempfile,time
from pathlib import Path
import numpy as np,soundfile as sf
from playwright.async_api import async_playwright
from benchmark_input_isolation import audio

ROOT=Path(__file__).resolve().parent
URL=os.environ.get('ROBBY_TEST_URL','https://diane-asylum-understood-invoice.trycloudflare.com')
INIT="""
localStorage.setItem('robby.autoStart','false');localStorage.setItem('robby.autoStartDefaultVersion','1');
localStorage.setItem('robby.cameraAuto','false');localStorage.setItem('robby.cameraAutoVersion','3');
localStorage.setItem('robby.avatar-idle-enabled','false');localStorage.setItem('robby.avatar-pet-invites-enabled','false');
localStorage.setItem('robby.memorySettings',JSON.stringify({enabled:false}));localStorage.setItem('robby.memoryDefaultVersion','1');
window.filterEvents=[];const OldSocket=window.WebSocket;
window.WebSocket=class extends OldSocket {constructor(...args){super(...args);this.addEventListener('message',e=>{
 if(typeof e.data==='string'){const m=JSON.parse(e.data);if(['ready','input_isolation','endpoint','asr_sentence','reply','turn_done','barge','error'].includes(m.type))filterEvents.push({...m,at:performance.now()});}
});}};
"""

async def main():
 report={'url':URL+'/desk-robot/','synthetic_microphone':True,'physical_room_test':False,'rows':[],'passed':False};errors=[]
 # Chrome loops this file; intro permits automatic wake, reference and reply tests.
 wave=np.r_[audio('christoph-intro'),np.zeros(12*16000),audio('christoph-followup'),np.zeros(12*16000)].astype(np.float32)
 with tempfile.TemporaryDirectory(prefix='robby-filter-browser-') as tmp:
  wav=Path(tmp)/'synthetic.wav';sf.write(wav,wave,16000)
  async with async_playwright() as p:
   browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str(wav),'--autoplay-policy=no-user-gesture-required'])
   page=await browser.new_page(viewport={'width':1280,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
   await page.add_init_script(INIT)
   try:
    await page.goto(report['url']);await page.wait_for_function('window.robotFace?.inputIsolationControls && !document.querySelector("#call").disabled',timeout=180000)
    assert await page.locator('#input-isolation-model').input_value()=='off'
    await page.evaluate("document.querySelector('#model-settings').open=true")
    await page.select_option('#input-isolation-model','voxlock')
    await page.wait_for_function('robotFace.inputIsolationControls.last?.phase==="waiting_reference"',timeout=100000)
    await page.click('#input-isolation-learn')
    await page.wait_for_function('robotFace.inputIsolationControls.last?.active && robotFace.inputIsolationControls.last.chunks>40',timeout=60000)
    await page.wait_for_function('filterEvents.some(m=>m.type==="reply") && robo.metrics.chunks>0',timeout=90000)
    for model in ('voxlock','scicom'):
     if model=='scicom':
      await page.select_option('#input-isolation-model','scicom')
      await page.wait_for_function('robotFace.inputIsolationControls.last?.selected==="scicom" && robotFace.inputIsolationControls.last.active',timeout=100000)
     previous=await page.evaluate('robotFace.inputIsolationControls.last.chunks')
     await page.wait_for_function('(previous)=>robotFace.inputIsolationControls.last.chunks>previous+30',arg=previous,timeout=15000)
     row=await page.evaluate('({state:robotFace.inputIsolationControls.last,microphone_packets:robo.metrics.mic_blocks,tts_chunks:robo.metrics.chunks,asr:filterEvents.filter(m=>m.type==="asr_sentence").map(m=>m.text),replies:filterEvents.filter(m=>m.type==="reply").map(m=>m.text)})')
     report['rows'].append(row);print(json.dumps(row),flush=True)
    await page.click('#input-isolation-clear')
    await page.wait_for_function('robotFace.inputIsolationControls.last?.phase==="waiting_reference" && robotFace.inputIsolationControls.last.reference_s===0',timeout=10000)
    report['clear_returns_to_raw']=True
    await page.select_option('#input-isolation-model','off')
    await page.wait_for_function('robotFace.inputIsolationControls.last?.phase==="off"',timeout=10000)
    assert await page.evaluate('localStorage.getItem("robby.inputIsolation")')=='off'
    report['off_persisted']=True
    report['errors']=await page.evaluate('filterEvents.filter(m=>m.type==="error")')
    report['browser_errors']=errors
    assert not report['errors'] and not errors,report
    await page.screenshot(path=str(ROOT/'logs/input-isolation-controls.png'),full_page=False)
    report['passed']=True
   except Exception as e:
    report['error']=str(e)
    report['recent_events']=await page.evaluate('filterEvents.slice(-20)')
    raise
   finally:
    try:await page.evaluate('robo.stop()')
    except Exception:pass
    await browser.close()
    (ROOT/'logs/input-isolation-ui-browser.json').write_text(json.dumps(report,indent=2))

if __name__=='__main__':asyncio.run(main())
