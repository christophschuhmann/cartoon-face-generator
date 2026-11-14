"""Real public Chrome AudioWorklet: automatic Hey Robby enrollment, two people.

Synthetic MediaStream only. Real CUDA isolation, ECAPA, ASR, identity, LLM/TTS.
No learn button, injected transcript, fake model output or physical recording.
"""
import asyncio,base64,json,os,time
from pathlib import Path
from playwright.async_api import async_playwright
from browser_input_isolation import INIT,URL
from benchmark_input_isolation import audio

MIC="""
navigator.mediaDevices.getUserMedia=async()=>{window.testMic=robo.ctx.createMediaStreamDestination();return testMic.stream;};
window.testSpeak=async(encoded)=>{const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)),x=new Float32Array(bytes.buffer),ctx=robo.ctx;
 const b=ctx.createBuffer(1,x.length,16000);b.getChannelData(0).set(x);const s=ctx.createBufferSource();s.buffer=b;s.connect(testMic);
 await new Promise(resolve=>{s.onended=resolve;s.start();});s.disconnect();};
"""
async def main():
 model=os.environ.get('ROBBY_FILTER_MODEL','voxlock');report={'model':model,'synthetic_only':True,'passed':False,'checks':{}}
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required'])
  page=await b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));await page.add_init_script(INIT+MIC)
  async def speak(name):await page.evaluate('x=>testSpeak(x)',base64.b64encode(audio(name).astype('<f4').tobytes()).decode())
  async def idle():await page.wait_for_function('robo.sources.length===0 && !document.querySelector("#phase-text").textContent.includes("speaking")',timeout=90000);await page.wait_for_timeout(600)
  try:
   await page.goto(URL+'/desk-robot/');await page.wait_for_function('window.robotFace?.inputIsolationControls && !document.querySelector("#call").disabled',timeout=180000)
   await page.evaluate('document.querySelector("#model-settings").open=true');await page.select_option('#input-isolation-model',model)
   await page.wait_for_function('robotFace.inputIsolationControls.last?.phase==="waiting_reference"',timeout=120000)
   await page.click('#call');await page.wait_for_function('window.testMic && robo.metrics.mic_blocks>20')
   await speak('christoph-intro')
   await page.wait_for_function('robotFace.inputIsolationControls.last?.known_voices?.some(v=>v.ready && v.name==="Christoph") && robotFace.inputIsolationControls.last.active',timeout=60000)
   await page.wait_for_function('filterEvents.some(e=>e.type==="turn_done")',timeout=60000);await idle()
   report['checks']['first_voice_auto']=True
   t=await page.evaluate('performance.now()');await speak('selma-intro')
   await page.wait_for_function('robotFace.inputIsolationControls.last?.known_voices?.filter(v=>v.ready).length===2 && robotFace.inputIsolationControls.last.active',timeout=60000)
   await page.wait_for_function('(t)=>filterEvents.some(e=>e.type==="turn_done" && e.at>t)',arg=t,timeout=60000);await idle()
   report['checks']['second_voice_added_without_erasing_first']=True
   before=await page.evaluate('robotFace.inputIsolationControls.last.known_voices')
   t=await page.evaluate('performance.now()');await speak('christoph-followup')
   await page.wait_for_function('(t)=>filterEvents.some(e=>e.type==="endpoint" && e.at>t && e.speaker_name==="Christoph")',arg=t,timeout=60000)
   await page.wait_for_function('(t)=>filterEvents.some(e=>e.type==="turn_done" && e.at>t)',arg=t,timeout=90000);await idle()
   report['checks']['known_voice_returns_without_wake']=True
   assert await page.evaluate('robotFace.inputIsolationControls.last.known_voices.length')==2
   # Unknown non-wake TV may leak acoustically, but must not create a turn/profile.
   t=await page.evaluate('performance.now()');await speak('background');await page.wait_for_timeout(8000)
   assert not await page.evaluate('(t)=>filterEvents.some(e=>e.type==="endpoint" && e.at>t)',t)
   assert await page.evaluate('robotFace.inputIsolationControls.last.known_voices.length')==2
   report['checks']['unknown_tv_not_admitted']=True
   report['voices']=before;report['state']=await page.evaluate('robotFace.inputIsolationControls.last')
   report['events']=await page.evaluate('filterEvents.filter(e=>["endpoint","error","asr_sentence"].includes(e.type))')
   assert not errors and not any(e['type']=='error' for e in report['events']),report
   report['passed']=True
  except Exception as e:
   report['error']=str(e);report['events']=await page.evaluate('filterEvents.filter(e=>e.type!=="input_isolation").slice(-20)');report['state']=await page.evaluate('robotFace?.inputIsolationControls?.last')
  finally:
   report['browser_errors']=errors
   try:await page.evaluate('robo.stop()')
   except Exception:pass
   await b.close();suffix=os.environ.get('BENCH_LABEL','')
   Path('logs/isolation-enrollment-browser-'+model+('-'+suffix if suffix else '')+'.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k!='events'}),flush=True)
 if not report['passed']:raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
