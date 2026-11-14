"""Public HTTPS, real LLM/TTS and browser playback; no microphone simulation."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
from browser_stunts_emotions_check import INIT,URL
ROOT=Path(__file__).resolve().parent

async def main():
 report={'passed':False,'physical_microphone':False,'turns':[]};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required'])
  page=await browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  await page.add_init_script(INIT+"localStorage.setItem('robby.verification',JSON.stringify({candidate_search:true,verify_tts:true,verify_input:true,serial_tts:false}));")
  try:
   response=await page.goto(URL+'/desk-robot/');assert response.status==200
   await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled',timeout=90000)
   assert await page.locator('#candidate-search').is_checked()
   await page.locator('#verification-controls').evaluate('e=>e.open=true')
   await page.evaluate("""()=>{window.testEvents=[];window.testAudio=0;const old=robo.on.message,play=robo.play.bind(robo);robo.on.message=m=>{if(['reply','turn_done','pipeline_metrics','error','busy','verification_settings','avatar_action'].includes(m.type))testEvents.push(m);old(m)};robo.play=raw=>{testAudio++;play(raw)}}""")
   for search,text in [(True,'Sag bitte genau: Hallo, schön dich zu sehen.'),(False,'Mach eine Grimasse und sag kurz Hallo.')]:
    await page.locator('#candidate-search').set_checked(search)
    await page.evaluate('testEvents=[];testAudio=0')
    await page.fill('#message',text);await page.locator('#form').evaluate('f=>f.requestSubmit()')
    await page.wait_for_function('testEvents.some(e=>e.type==="turn_done"||e.type==="error"||e.type==="busy")',timeout=150000)
    data=await page.evaluate('({events:testEvents,audio_chunks:testAudio})')
    report['turns'].append({'search':search,**data})
    assert not [e for e in data['events'] if e['type'] in ('error','busy')],data
    assert data['audio_chunks']>0,data
    assert any(e['type']=='turn_done' for e in data['events']),data
    serialized=json.dumps(data)
    assert ('search_asr' in serialized) if search else ('"tts_generation_mode": "single"' in serialized),serialized
    await page.wait_for_function('robo.sources.length===0',timeout=30000)
   await page.locator('#candidate-search').check();await page.reload()
   await page.wait_for_selector('#candidate-search',state='attached');assert await page.locator('#candidate-search').is_checked()
   report['persistence']=True;report['passed']=not errors
  except Exception as e:report['error']=repr(e)
  finally:
   report['page_errors']=errors
   try:await page.evaluate('robo.stop()')
   except Exception:pass
   await browser.close()
 (ROOT/'logs/candidate-search-browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print(json.dumps({'passed':report['passed'],'error':report.get('error'),'turns':len(report['turns'])}),flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
