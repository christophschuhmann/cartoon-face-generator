"""HTTPS: typed requests through selected hosted LLM, live TTS and avatar rendering."""
import asyncio,json,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent
URL='https://diane-asylum-understood-invoice.trycloudflare.com'
async def main():
 report={'passed':False,'scope':'Synthetic typed requests with Qwen 27B, real TTS and rendered screen avatar. No physical microphone.','turns':[]};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required'])
  page=await browser.new_page(viewport={'width':1280,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
  await page.add_init_script("localStorage.setItem('robby.llmSelection',JSON.stringify({model:'qwen',provider:'cerebras/fp16'}));localStorage.setItem('robby.autoStartDefaultVersion','1');localStorage.setItem('robby.autoStart','false');localStorage.setItem('robby.cameraAutoVersion','3');localStorage.setItem('robby.cameraAuto','false');localStorage.setItem('robby.avatar-idle-enabled','false');localStorage.setItem('robby.avatar-actions-enabled','true');localStorage.setItem('robby.memoryDefaultVersion','1');localStorage.setItem('robby.memorySettings',JSON.stringify({enabled:false}));")
  try:
   response=await page.goto(URL+'/desk-robot/');assert response.status==200
   await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled',timeout=90000)
   await page.evaluate('''()=>{window.checkEvents=[];window.checkAudio=[];window.checkFrames=[];
     const old=robo.on.message,play=robo.play.bind(robo),frame=robotFace.actions.frame.bind(robotFace.actions);
     robo.on.message=m=>{if(['reply','avatar_action','pipeline_metrics','turn_done','error','busy','barge'].includes(m.type))checkEvents.push(m);old(m)};
     robo.play=raw=>{checkAudio.push(raw.byteLength);play(raw)};
     robotFace.actions.frame=(...args)=>{const r=frame(...args),a=robotFace.actions.active;if(a)checkFrames.push({kind:a.kind,source:a.source});return r;};}''')
   cases=[('Wie geht es dir heute, kleiner Roboter?',-2,None),('Was würdest du gerne mit mir unternehmen?',-2,None),('Erkläre mir in zwei Sätzen, warum der Mond leuchtet.',2,None),('Sei mal sauer.',None,'anger')]
   for idx,(prompt,count,emotion) in enumerate(cases):
    before=await page.evaluate('checkEvents.length');before_audio=await page.evaluate('checkAudio.length');before_frames=await page.evaluate('checkFrames.length')
    await page.locator('#message').fill(prompt);await page.locator('#form').evaluate('f=>f.requestSubmit()')
    await page.wait_for_function('(n)=>checkEvents.slice(n).some(e=>e.type==="turn_done"||e.type==="error")',arg=before,timeout=150000)
    await page.wait_for_timeout(300)
    events=await page.evaluate('(n)=>checkEvents.slice(n)',before);replies=[e for e in events if e.get('type')=='reply']; bad=[e for e in events if e.get('type') in ('error','busy','barge')]
    assert not bad,bad
    assert replies,'No spoken reply'
    if count is not None:
     assert (2<=len(replies)<=4 if count==-2 else len(replies)>=3 if count==-1 else len(replies)==count),[(e.get('sentence_index'),e.get('sentence_text')) for e in replies]
     metrics=next(e['metrics'] for e in events if e.get('type')=='pipeline_metrics');assert metrics.get('response_complete') and metrics.get('sentences')==len(replies),metrics
    if emotion:
     actions=[e for e in events if e.get('type')=='avatar_action'];assert any(any(s.get('emotion')==emotion for s in a.get('steps',[])) for a in actions),actions
     frames=await page.evaluate('(n)=>checkFrames.slice(n)',before_frames);assert any(f['kind']=='emotion' for f in frames),frames
    audio=await page.evaluate('checkAudio.length')-before_audio;assert audio>0
    report['turns'].append({'request':prompt,'sentences':len(replies),'reply':replies[-1]['text'],'emotion':emotion,'audio_chunks':audio});print(json.dumps(report['turns'][-1],ensure_ascii=False),flush=True)
    await page.wait_for_timeout(500)
   report['passed']=not errors
  except Exception as e:
   report['error']=repr(e);report['recent_events']=(await page.evaluate('window.checkEvents||[]'))[-15:]
  finally:
   report['page_errors']=errors
   try:await page.evaluate('window.robo?.stop()')
   except Exception:pass
   await browser.close()
 (ROOT/'logs/rtx3090-personality-browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print('PASSED',report['passed'],report.get('error',''),flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
