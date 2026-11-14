"""Real HTTPS/CUDA/ASR/TTS spoken Stop, synthetic MediaStream + 120-ms bot echo."""
import asyncio,base64,json,time,os
from pathlib import Path
from playwright.async_api import async_playwright
from browser_input_isolation import INIT,URL
from benchmark_input_isolation import audio

MIC="""
navigator.mediaDevices.getUserMedia=async()=>{
 const ctx=window.robo.ctx,d=ctx.createMediaStreamDestination();window.testMic=d;
 const delay=ctx.createDelay(1),gain=ctx.createGain();delay.delayTime.value=.12;gain.gain.value=.05;
 robo.output.connect(delay);delay.connect(gain);gain.connect(d);return d.stream;
};
window.testSpeak=async(encoded)=>{
 const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)),x=new Float32Array(bytes.buffer),ctx=robo.ctx;
 const b=ctx.createBuffer(1,x.length,16000);b.getChannelData(0).set(x);
 const s=ctx.createBufferSource();s.buffer=b;s.connect(testMic);
 await new Promise(resolve=>{s.onended=resolve;s.start();});s.disconnect();
};
"""

async def main():
 models=os.environ.get('ROBBY_STOP_MODELS','voxlock,scicom').split(',')
 report={'passed':False,'synthetic_only':True,'physical_microphone':False,'echo_delay_ms':120,'echo_gain':.05,'rows':[]}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required'])
  page=await browser.new_page();await page.add_init_script(INIT+MIC)
  async def speak(name):await page.evaluate('x=>testSpeak(x)',base64.b64encode(audio(name).astype('<f4').tobytes()).decode())
  try:
   await page.goto(URL+'/desk-robot/');await page.wait_for_function('window.robotFace?.inputIsolationControls && !document.querySelector("#call").disabled',timeout=60000)
   await page.evaluate("document.querySelector('#model-settings').open=true")
   await page.select_option('#input-isolation-model',models[0])
   if models[0]!='off':await page.wait_for_function('robotFace.inputIsolationControls.last?.phase==="waiting_reference"',timeout=100000)
   await page.click('#input-isolation-learn');await page.wait_for_function('window.testMic');await speak('christoph-intro')
   await page.wait_for_function('(robotFace.inputIsolationControls.last?.active || robotFace.inputIsolationControls.last?.selected==="off") && filterEvents.some(m=>m.type==="turn_done") && robo.sources.length===0',timeout=90000)
   for model in models:
    if model!=models[0]:
     await page.select_option('#input-isolation-model',model)
     await page.wait_for_function('(model)=>robotFace.inputIsolationControls.last?.selected===model && robotFace.inputIsolationControls.last.active',arg=model,timeout=100000)
    await page.evaluate("robo.send('text:Erzähle mir bitte eine lustige Geschichte über einen Roboter im Weltraum. Antworte mit acht vollständigen Sätzen.')")
    await page.wait_for_function('robo.sources.some(s=>s.roboId>0)',timeout=60000);await page.wait_for_timeout(1000)
    ids=await page.evaluate('robo.sources.map(s=>s.roboId)');t=await page.evaluate('performance.now()')
    await speak('christoph-stop')
    row={'model':model,'stop_detected':False}
    try:
     await page.wait_for_function('(t)=>filterEvents.some(m=>m.type==="barge" && m.at>t)',arg=t,timeout=12000)
     row=await page.evaluate('({t,ids})=>({model:robotFace.inputIsolationControls.last.selected,stop_detected:true,command_start_to_barge_ms:filterEvents.find(m=>m.type==="barge"&&m.at>t).at-t,old_audio_cancelled:!robo.sources.some(s=>ids.includes(s.roboId)),filter_active:robotFace.inputIsolationControls.last.active,microphone_live:robo.stream.getAudioTracks()[0].readyState==="live"})',{'t':t,'ids':ids})
     assert row['old_audio_cancelled'] and (row['filter_active'] or model=='off') and row['microphone_live'],row
    except Exception as e:
     row['error']=str(e);row['events']=await page.evaluate('filterEvents.filter(m=>m.type!=="input_isolation").slice(-15)')
     await page.evaluate("robo.stopAudio();robo.send('interrupt')")
    report['rows'].append(row);print(json.dumps(row),flush=True);await page.wait_for_timeout(1000)
   report['passed']=all(r['stop_detected'] for r in report['rows'])
  except Exception as e:report['error']=str(e)
  finally:
   try:await page.evaluate('robo.stop()')
   except Exception:pass
   await browser.close();Path('logs/input-isolation-stop-'+ '-'.join(models) +'.json').write_text(json.dumps(report,indent=2))
 if not report['passed']:raise SystemExit('Filtered spoken Stop test failed; see receipt')

if __name__=='__main__':asyncio.run(main())
