"""Real HTTPS typed requests -> Qwen -> verified streamed TTS -> CPU 3D animation.

Only authored test requests; no private recordings. Separate deterministic
renderer checks prove platform motion, reduced-motion behaviour and cancellation.
"""
import asyncio,json,base64
from pathlib import Path
from playwright.async_api import async_playwright
from browser_stunts_emotions_check import INIT,URL

ROOT=Path(__file__).resolve().parent
async def main():
 report={'passed':False,'turns':[],'scope':__doc__};errors=[]
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required'])
  page=await b.new_page(viewport={'width':1280,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
  await page.add_init_script(INIT)
  try:
   response=await page.goto(URL+'/desk-robot/');assert response.status==200
   await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled',timeout=150000)
   report['renderer']=await page.evaluate('''async()=>{
    const {sampleAction,validateSteps,AvatarActions}=await import('/static/avatar-actions.js');
    const {pose}=await import('/static/emotions.js');const rig=robotFace.rig,base=pose();
    const ok=(v,m)=>{if(!v)throw Error(m);};
    const draw=(step,t)=>{const a=sampleAction(step,t,base);rig.update({pose:a.pose,actionMotion:a.motion,actionEyes:a.eyes,freezeExpression:true},1000,0);return rig.snapshot();};
    const rest=draw({kind:'nod'},0),body=draw({kind:'spin',scope:'body',direction:'clockwise'},.5),head=draw({kind:'spin',scope:'head',direction:'clockwise'},.5);
    ok(body.baseFront[2]<-109&&head.baseFront[2]>109,'platform follows body, not head-only rotation');
    const flip={kind:'somersault',direction:'forward'},down=draw(flip,.18),air=draw(flip,.5),end=draw(flip,1);
    ok(down.bodySquash<.91&&down.baseCenter[1]<rest.baseCenter[1],'crouch');
    ok(Math.abs(air.bodyFlip-180)<.01&&air.bodyLift>139&&air.baseCenter[1]>400,'platform flips with whole body');
    ok(Math.abs(end.bodyFlip-360)<.01&&Math.abs(end.baseCenter[1]-rest.baseCenter[1])<.01,'full turn and landing');
    ok(Object.values(sampleAction(flip,.5,base,true).motion).every(x=>x===0),'reduced motion has no jump/flip');
    ok(validateSteps([{...flip,duration_s:4.8}]).length===1,'flip accepted');
    ok(!validateSteps([{...flip,direction:'clockwise',duration_s:4.8}]).length,'wrong flip axis rejected');
    const a=new AvatarActions();a.idleEnabled=false;
    a.request('timed',[{...flip,duration_s:4.8}],100,{waitForAudio:true});a.bindRequested(7,'timed');
    a.frame(500,base,{busy:true});ok(!a.queue.length,'do not finish trick during LLM prefill');
    a.frame(1000,base,{position:{id:7,sample:1}});ok(a.queue[0]?.start===1000,'actual playback starts trick');
    ok(!a.request('timed',[{...flip,duration_s:4.8}],1100),'no metadata replay');
    a.clear();a.request('fallback',[{...flip,duration_s:4.8}],2000,{waitForAudio:true});a.frame(6001,base);ok(a.queue.length===1,'silent-service bounded animation fallback');a.clear();
    robotFace.actions.request('cancel-test',[{...flip,duration_s:4.8}]);robotFace.actions.clear();
    ok(!robotFace.actions.queue.length,'cancel clears requested trick');
    robotFace.actions.request('pending-error',[{...flip,duration_s:4.8}],performance.now(),{waitForAudio:true});
    robo.on.message({type:'error',error:'Synthetic UI contract probe',stage:'planning'});
    ok(!!robotFace.actions.pendingRequest,'a planning failure must not cancel a valid requested visual');robotFace.actions.clear();
    const r={base_rest:rest.baseCenter,base_spin:body.baseFront,base_head_only:head.baseFront,base_air:air.baseCenter,base_landed:end.baseCenter};draw({kind:'nod'},0);return r;
   }''')
   await page.evaluate('''()=>{window.stuntEvents=[];window.stuntFrames=[];window.stuntAudio=0;
    const old=robo.on.message,play=robo.play.bind(robo);
    robo.on.message=m=>{if(['reply','avatar_action','turn_done','error','barge','busy'].includes(m.type))stuntEvents.push(m);old(m);};
    robo.play=b=>{stuntAudio++;play(b);};
    setInterval(()=>{const r=robotFace.rig.snapshot();if(robotFace.actions.active)stuntFrames.push({kind:robotFace.actions.active.kind,bodySpin:r.bodySpin,bodyFlip:r.bodyFlip,bodySquash:r.bodySquash,bodyLift:r.bodyLift,pose:r.pose.slug,base:r.baseCenter,render_ms:r.renderMs,audio:!!robo.clock?.position()&&robo.sources.length>0})},30);
   }''')
   cases=[('Dreh dich mal im Kreis.','spin',-1),('Dreh dich gegen den Uhrzeigersinn.','spin',1),
          ('Mach mal einen Salto.','somersault',1),('Mach einen Salto rückwärts.','somersault',-1),
          ('Sei mal wütend.','emotion',0),('Mach eine lustige Grimasse.','grimace',0)]
   for text,kind,sign in cases:
    await page.wait_for_function('robo.sources.length===0',timeout=45000)
    await page.evaluate('stuntEvents=[];stuntFrames=[];stuntAudio=0')
    await page.fill('#message',text);await page.locator('#form').evaluate('f=>f.requestSubmit()')
    await page.wait_for_function('stuntEvents.some(e=>e.type==="turn_done"||e.type==="error")',timeout=120000)
    await page.wait_for_function('robotFace.actions.queue.length===0',timeout=20000)
    data=await page.evaluate('({events:stuntEvents,frames:stuntFrames,audio:stuntAudio})')
    row={'request':text,**data};report['turns'].append(row)
    assert not [e for e in data['events'] if e['type'] in ('error','barge','busy')],data['events']
    actions=[e for e in data['events'] if e['type']=='avatar_action'];assert len(actions)==1 and actions[0]['steps'][0]['kind']==kind,actions
    assert data['audio']>0,'No real TTS audio'
    assert any(f['audio'] and f['kind']==kind for f in data['frames']),'No speech during requested animation'
    if kind in ('spin','somersault'):
     key='bodySpin' if kind=='spin' else 'bodyFlip'
     assert max(sign*f[key] for f in data['frames'])>345,'Incomplete whole-body turn'
    if kind=='somersault':assert min(f['bodySquash'] for f in data['frames'])<.92 and max(f['bodyLift'] for f in data['frames'])>135
    if kind=='emotion':assert any(f['pose']=='anger' for f in data['frames'])
    row['passed']=True;print(text,'PASS',data['audio'],'audio chunks',flush=True)
   # Disabled actions remain disabled. A repeated action ID never replays.
   report['disabled']=await page.evaluate('''()=>{const a=robotFace.actions;a.enabled=false;const x=a.request('disabled-check',[{kind:'somersault',direction:'forward',duration_s:4.8}]);const out=!x&&!a.queue.length&&!!a.warning;a.enabled=true;a.warning='';return out;}''')
   assert report['disabled'];report['passed']=not errors
   # Capture the actual software-rendered frame synchronously; Playwright's
   # scrolling/screenshot wait can otherwise miss a brief airborne pose.
   png=await page.evaluate('''async()=>{const {sampleAction}=await import('/static/avatar-actions.js');const a=sampleAction({kind:'somersault',direction:'forward'},.5);robotFace.rig.update({pose:a.pose,actionMotion:a.motion,actionEyes:true,freezeExpression:true},1000,0);return document.querySelector('#avatar canvas').toDataURL();}''')
   (ROOT/'logs/stunts-somersault-20261113.png').write_bytes(base64.b64decode(png.split(',')[1]))
  except Exception as exc:report['error']=repr(exc)
  finally:
   report['page_errors']=errors
   try:await page.evaluate('robo.stop()')
   except Exception:pass
   await b.close()
 (ROOT/'logs/stunts-body-browser-20261113.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
 print({'passed':report['passed'],'turns':len(report['turns']),'error':report.get('error')},flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
