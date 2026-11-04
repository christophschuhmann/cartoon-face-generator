"""HTTPS typed commands: real LLM/TTS, 3D yaw rotation, and all 40 authored poses."""
import asyncio,json,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent
URL='https://diane-asylum-understood-invoice.trycloudflare.com'
INIT="""localStorage.setItem('robby.llmSelection',JSON.stringify({model:'qwen',provider:'cerebras/fp16'}));localStorage.setItem('robby.autoStartDefaultVersion','1');localStorage.setItem('robby.autoStart','false');localStorage.setItem('robby.cameraAutoVersion','3');localStorage.setItem('robby.cameraAuto','false');localStorage.setItem('robby.avatar-idle-enabled','false');localStorage.setItem('robby.avatar-actions-enabled','true');localStorage.setItem('robby.memoryDefaultVersion','1');localStorage.setItem('robby.memorySettings',JSON.stringify({enabled:false}));"""
HOOK="""()=>{window.actEvents=[];window.actAudio=0;window.actYaw=[];window.actPoses=[];
 const old=robo.on.message,play=robo.play.bind(robo);
 robo.on.message=m=>{if(['reply','avatar_action','turn_done','pipeline_metrics','error','barge','busy'].includes(m.type))actEvents.push(m);old(m)};
 robo.play=raw=>{actAudio++;play(raw)};
 setInterval(()=>{const r=robotFace.rig.snapshot();if(robotFace.actions.active){actYaw.push(r.visualPan);actPoses.push(r.pose.slug)}},35);
}"""
async def main():
 report={'passed':False,'scope':__doc__,'physical_microphone':False,'turns':[],'poses':[]};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required']);page=await browser.new_page(viewport={'width':1200,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
  await page.add_init_script(INIT)
  try:
   r=await page.goto(URL+'/desk-robot/');assert r.status==200
   await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled',timeout=90000);await page.evaluate(HOOK)
   cases=[('Mach eine Drehung.','spin','clockwise'),('Kannst du eine Drehung gegen den Uhrzeigersinn machen?','spin','counterclockwise'),('Du sollst mal wütend sein.','emotion','anger'),('Stell bitte Enttäuschung dar.','emotion','disappointment'),('Zeig mir Ehrfurcht.','emotion','awe'),('Sei überrascht.','emotion','surprise'),('Mach eine Grimasse.','grimace',None)]
   for text,kind,value in cases:
    await page.evaluate('actEvents=[];actAudio=0;actYaw=[];actPoses=[]');await page.fill('#message',text);await page.locator('#form').evaluate('f=>f.requestSubmit()')
    await page.wait_for_function('actEvents.some(e=>e.type==="turn_done"||e.type==="error")',timeout=150000)
    await page.wait_for_function('robotFace.actions.queue.length===0',timeout=20000)
    data=await page.evaluate('({events:actEvents,audio:actAudio,yaw:actYaw,poses:actPoses})');bad=[e for e in data['events'] if e['type'] in ('error','barge','busy')];assert not bad,bad
    actions=[e for e in data['events'] if e['type']=='avatar_action'];assert actions and actions[0]['steps'][0]['kind']==kind,actions
    assert data['audio']>0
    replies=[e for e in data['events'] if e['type']=='reply'];assert replies
    if kind=='spin':
     assert actions[0]['steps'][0]['direction']==value
     assert (min(data['yaw'])<-340 if value=='clockwise' else max(data['yaw'])>340),data['yaw']
    if kind=='emotion':
     assert actions[0]['steps'][0]['emotion']==value
     assert value in data['poses'],data['poses']
     assert all(e['performance']['sentences'][-1]['emotion']==value for e in replies),replies
    row={'request':text,'steps':actions[0]['steps'],'reply':replies[-1]['text'],'audio_chunks':data['audio'],'rendered_yaw_min':min(data['yaw']),'rendered_yaw_max':max(data['yaw']),'rendered_pose_labels':sorted(set(data['poses']))}
    report['turns'].append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
   # Separate rendering coverage: exercise every catalog pose through the same action controller.
   slugs=await page.evaluate('robotFace.profiles.map(p=>p.slug)');assert len(slugs)==40
   for i,slug in enumerate(slugs):
    await page.evaluate('(s)=>{robotFace.actions.request("catalogue-"+s,[{kind:"emotion",emotion:s,duration_s:3}],performance.now()-1500)}',slug)
    await page.wait_for_timeout(280)
    snap=await page.evaluate('({slug:robotFace.rig.snapshot().pose.slug,actions:robotFace.rig.snapshot().displayPose.actions})');assert snap['slug']==slug,snap;report['poses'].append(snap)
   assert len({json.dumps(x['actions'],sort_keys=True) for x in report['poses']})==40
   await page.evaluate('robotFace.actions.clear()');report['passed']=not errors
  except Exception as e:
   report['error']=repr(e)
  finally:
   report['page_errors']=errors
   try:await page.evaluate('robo.stop()')
   except Exception:pass
   await browser.close()
 (ROOT/'static/stunts-emotions-browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print('PASSED',report['passed'],report.get('error',''),flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
