"""Actual HTTPS page → configured LLM/tools → verified TTS → rendered avatar.
Uses authored requests; it never records a person. SVG diagrams checked at mobile.
"""
import asyncio,json,time
from pathlib import Path
from playwright.async_api import async_playwright
from browser_stunts_emotions_check import INIT,URL
ROOT=Path(__file__).parent
async def main():
 report={'date':'2026-11-14','url':URL+'/desk-robot/','turns':[],'passed':False};errors=[]
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required'])
  page=await b.new_page(viewport={'width':1280,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
  await page.add_init_script(INIT+"localStorage.setItem('robby.verification',JSON.stringify({verify_input:true,verify_tts:true,serial_tts:false}));")
  try:
   response=await page.goto(URL+'/desk-robot/');assert response.status==200
   await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled&&document.querySelector("#system-guide")',timeout=150000)
   await page.evaluate('''()=>{window.auditEvents=[];window.auditFrames=[];window.auditAudio=0;
    const old=robo.on.message,play=robo.play.bind(robo);
    robo.on.message=m=>{if(['reply','avatar_action','turn_done','error','barge','busy','pipeline_metrics','verification_settings'].includes(m.type))auditEvents.push(m);old(m);};
    robo.play=b=>{auditAudio++;play(b);};
    setInterval(()=>{const a=robotFace.actions,r=robotFace.rig.snapshot();if(a.active)auditFrames.push({kind:a.active.kind,pose:r.pose.slug,spin:r.bodySpin,flip:r.bodyFlip,audio:!!robo.clock?.position()&&robo.sources.length>0});},50);
   }''')
   cases=[('Hey Robbie, schneid eine Grimasse.','grimace',None),('Mach ein ernstes Gesicht.','emotion','concentration'),
     ('Mach einen Salto rückwärts.','somersault',None),('Mach einen Hundeblick.','puppy',None),
     ('Kannst du kurz mit einem Auge blinzeln?','wink',None),('Schüttle den Kopf.','shake',None),
     ('Puste deine Backen auf und schiele lustig.','grimace',None),('Mach so 😡','emotion','anger'),
     ('Schau bei Wikipedia nach Pinguinen und nenne einen kurzen Fakt.','lookup','search_wikipedia'),
     ('Kannst du die offizielle Website des Viktor Frankl Instituts nachgucken? Antworte in einem Satz.','lookup','search_web')]
   for text,kind,extra in cases:
    await page.wait_for_function('robo.sources.length===0',timeout=45000)
    await page.evaluate('auditEvents=[];auditFrames=[];auditAudio=0');start=time.perf_counter()
    await page.fill('#message',text);await page.locator('#form').evaluate('f=>f.requestSubmit()')
    await page.wait_for_function('auditEvents.some(e=>e.type==="turn_done"||e.type==="error")',timeout=140000)
    await page.wait_for_function('robotFace.actions.queue.length===0&&!robotFace.actions.pendingRequest',timeout=20000)
    data=await page.evaluate('({events:auditEvents,frames:auditFrames,audio:auditAudio})');row={'request':text,'elapsed_ms':round((time.perf_counter()-start)*1000),**data};report['turns'].append(row)
    assert not [e for e in data['events'] if e['type'] in ('error','barge','busy')],str(data['events'])[:1500]
    assert data['audio']>0,'No actual TTS PCM'
    if kind=='lookup':
     replies=[e for e in data['events'] if e['type']=='reply'];assert any(e.get('sources') for e in replies),'No sources';assert any(x['tool']==extra and not x.get('error') for e in replies for x in e.get('lookups',[])),replies
    else:
     assert any(f['kind']==kind for f in data['frames']),'No actual animation'
     if extra:assert any(f['pose']==extra for f in data['frames']),'Wrong pose'
     if kind=='somersault':assert max(abs(f['flip']) for f in data['frames'])>345,'Incomplete flip'
    row['passed']=True;print(text,'PASS',data['audio'],'PCM chunks',flush=True)
    (ROOT/'logs/tools-browser-20261114.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
   # Verify every authored emotion and grimace really renders, not only metadata.
   report['catalogue']=await page.evaluate('''async()=>{const {profiles,pose}=await import('/static/emotions.js');const {sampleAction,GRIMACES,validateSteps}=await import('/static/avatar-actions.js');const rig=robotFace.rig;const poses=[],faces=[];
    for(const p of profiles){const a=sampleAction({kind:'emotion',emotion:p.slug},.55);rig.update({pose:a.pose,actionMotion:a.motion,actionEyes:a.eyes,freezeExpression:true},1000,0);const s=rig.snapshot();if(s.pose.slug!==p.slug)throw Error(p.slug);poses.push({slug:p.slug,controls:s.displayPose.actions});}
    for(const variant of GRIMACES){const a=sampleAction({kind:'grimace',variant},.55);rig.update({pose:a.pose,actionMotion:a.motion,actionEyes:a.eyes,freezeExpression:true},1000,0);faces.push(variant);}
    return {poses,faces,uniquePoses:new Set(poses.map(p=>JSON.stringify(p.controls))).size};}''')
   assert len(report['catalogue']['poses'])==40 and report['catalogue']['uniquePoses']==40
   # Toggle through actual DOM -> WebSocket -> backend -> TTS request/receipt.
   report['checks']=[]
   for checked,serial in ((False,False),(True,False),(True,True)):
    await page.wait_for_function('robo.sources.length===0',timeout=45000)
    await page.locator('#verification-controls').evaluate('e=>e.open=true')
    await page.locator('#verify-tts').set_checked(checked);await page.locator('#verify-input').set_checked(checked)
    if checked:await page.locator('#verify-serial').set_checked(serial)
    await page.wait_for_function('document.querySelector("#verification-status").textContent.includes("confirmed")')
    await page.evaluate('auditEvents=[];auditAudio=0');await page.fill('#message','Sag genau: Hallo zusammen, schön euch zu sehen.');await page.locator('#form').evaluate('f=>f.requestSubmit()')
    await page.wait_for_function('auditEvents.some(e=>e.type==="turn_done"||e.type==="error")',timeout=90000)
    d=await page.evaluate('({events:auditEvents,audio:auditAudio})');assert not any(e['type']=='error' for e in d['events']);assert d['audio']>0
    metrics=[e['metrics'] for e in d['events'] if e['type']=='pipeline_metrics'][-1];assert metrics['verification']['align'] is checked
    assert metrics['verification']['speech_verification']==('serial' if serial else 'parallel')
    report['checks'].append({'enabled':checked,'serial':serial,'metrics':metrics,'pcm_chunks':d['audio']});print('Verification',checked,'PASS',flush=True)
   await page.wait_for_function('robo.sources.length===0',timeout=45000)
   await page.locator('#verify-serial').uncheck()
   await page.wait_for_function('document.querySelector("#verification-status").textContent.includes("confirmed")')
   await page.evaluate('robo.stop()')
   await page.reload();await page.wait_for_selector('#system-guide');assert await page.locator('#verify-tts').is_checked()
   await page.set_viewport_size({'width':390,'height':844});await page.locator('#system-guide').scroll_into_view_if_needed();await page.screenshot(path=str(ROOT/'logs/tools-guide-mobile-20261114.png'))
   report['guide']=await page.evaluate('''()=>({diagrams:[...document.querySelectorAll('#system-guide img')].map(x=>({src:x.getAttribute('src'),loaded:x.complete&&x.naturalWidth>0})),belowSettings:document.querySelector('#system-guide').getBoundingClientRect().top>document.querySelector('aside').getBoundingClientRect().bottom-1,bodyOverflow:document.documentElement.scrollWidth>innerWidth+2})''')
   assert all(x['loaded'] for x in report['guide']['diagrams']);assert report['guide']['belowSettings'];assert not report['guide']['bodyOverflow']
   report['passed']=not errors
  except Exception as e:report.update(error=str(e)[:2200],error_type=type(e).__name__);print('FAIL',report.get('error'),flush=True)
  finally:
   report['page_errors']=errors
   try:await page.evaluate('robo.stop()')
   except Exception:pass
   await b.close()
 (ROOT/'logs/tools-browser-20261114.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('PASSED',report['passed'],flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
