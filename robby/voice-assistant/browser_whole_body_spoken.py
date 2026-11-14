"""Authored TTS microphone fixtures -> live ASR -> whole-body tools + spoken reply."""
import asyncio,json
from pathlib import Path
import numpy as np,soundfile as sf
from playwright.async_api import async_playwright
import browser_mouth_to_ear as fixture
from browser_stunts_emotions_check import INIT,URL
ROOT=Path(__file__).resolve().parent
TEXTS=['Hey Robby, dreh dich bitte im Kreis.','Hey Robby, mach bitte einen Salto.']
async def main():
 fixture.TEXTS=TEXTS;fixture.FIXTURES=ROOT/'.runtime/body-stunts-mic'
 await fixture.tts_idle();paths=fixture.fixtures()
 report={'passed':False,'physical_microphone':False,'scope':__doc__,'turns':[]}
 async with async_playwright() as p:
  try:
   for i,path in enumerate(paths):
    await fixture.tts_idle();wave,rate=sf.read(path,dtype='float32');mic=path.with_name('capture-'+path.name)
    sf.write(mic,np.r_[np.zeros(3*rate),wave,np.zeros(24*rate)].astype(np.float32),rate,subtype='PCM_16')
    b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str(mic),'--autoplay-policy=no-user-gesture-required'])
    page=await b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));await page.add_init_script(INIT)
    try:
     await page.goto(URL+'/desk-robot/');await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled',timeout=60000)
     await page.evaluate('''()=>{window.ev=[];window.fr=[];window.chunks=0;const old=robo.on.message,play=robo.play.bind(robo);robo.on.message=m=>{if(['asr_sentence','avatar_action','reply','turn_done','error'].includes(m.type))ev.push(m);old(m);};robo.play=x=>{chunks++;play(x);};setInterval(()=>{if(robotFace.actions.active){const s=robotFace.rig.snapshot();fr.push({spin:s.bodySpin,flip:s.bodyFlip,heard:!!robo.clock?.position()&&robo.sources.length>0})}},30);}''')
     await page.click('#call')
     await page.wait_for_function('ev.some(e=>["turn_done","error"].includes(e.type))',timeout=120000)
     await page.wait_for_function('robotFace.actions.queue.length===0',timeout=20000)
     row=await page.evaluate('({events:ev,frames:fr,audio_chunks:chunks})');row['request']=TEXTS[i];row['page_errors']=errors;report['turns'].append(row)
     assert not errors and not any(e['type']=='error' for e in row['events']),row['events']
     action=next(e for e in row['events'] if e['type']=='avatar_action')['steps'][0]
     assert action['kind']==('spin' if i==0 else 'somersault'),action
     assert row['audio_chunks']>0 and any(f['heard'] for f in row['frames'])
     assert max((-f['spin'] if i==0 else f['flip']) for f in row['frames'])>345
     row['passed']=True;print(TEXTS[i],'PASS',flush=True)
    finally:
     try:await page.evaluate('robo.stop()')
     except Exception:pass
     await b.close()
   report['passed']=True
  except Exception as e:report['error']=repr(e)
 (ROOT/'logs/stunts-body-spoken-20261113.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print({'passed':report['passed'],'error':report.get('error')},flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
