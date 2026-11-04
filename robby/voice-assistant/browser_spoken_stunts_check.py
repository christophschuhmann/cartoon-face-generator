"""Synthetic microphone through HTTPS ASR -> real LLM/TTS -> rendered actions."""
import asyncio,json
from pathlib import Path
import numpy as np,soundfile as sf
from playwright.async_api import async_playwright
import browser_mouth_to_ear as fixture
from browser_stunts_emotions_check import HOOK
ROOT=Path(__file__).resolve().parent
URL='https://diane-asylum-understood-invoice.trycloudflare.com'
TEXTS=['Hey Robby, mach eine Drehung.','Hey Robby, du sollst mal wütend sein.','Hey Robby, zeig mir Traurigkeit.']
async def main():
 fixture.TEXTS=TEXTS;fixture.FIXTURES=ROOT/'.runtime/stunts-mic';paths=fixture.fixtures()
 report={'passed':False,'scope':__doc__,'physical_microphone':False,'turns':[]}
 async with async_playwright() as p:
  try:
   for i,path in enumerate(paths):
    await fixture.tts_idle();wave,rate=sf.read(path,dtype='float32');mic=fixture.FIXTURES/('mic-'+str(i)+'.wav');sf.write(mic,np.r_[np.zeros(3*rate),wave,np.zeros(25*rate)].astype(np.float32),rate,subtype='PCM_16')
    b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str(mic),'--autoplay-policy=no-user-gesture-required']);page=await b.new_page(viewport={'width':1200,'height':1000})
    await page.add_init_script(fixture.INIT+"localStorage.setItem('robby.avatar-actions-enabled','true');")
    try:
     await page.goto(URL+'/desk-robot/');await page.wait_for_function('window.robo&&window.robotFace',timeout=60000);await page.evaluate(HOOK)
     await page.wait_for_function('actEvents.some(e=>e.type==="turn_done"||e.type==="error")',timeout=120000)
     await page.wait_for_function('robotFace.actions.queue.length===0',timeout=15000)
     data=await page.evaluate('({events:actEvents,audio:actAudio,yaw:actYaw,poses:actPoses})');assert not [e for e in data['events'] if e['type'] in ('error','barge','busy')],data['events']
     actions=[e for e in data['events'] if e['type']=='avatar_action'];assert actions and data['audio']>0,data
     if i==0:assert actions[0]['steps'][0]['kind']=='spin' and min(data['yaw'])<-340
     else:
      expected='anger' if i==1 else 'sadness';assert actions[0]['steps'][0]['emotion']==expected and expected in data['poses']
     replies=[e for e in data['events'] if e['type']=='reply'];row={'request':TEXTS[i],'steps':actions[0]['steps'],'reply':replies[-1]['text'],'audio_chunks':data['audio'],'rendered_yaw_range':[min(data['yaw']),max(data['yaw'])]};report['turns'].append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    finally:
     try:await page.evaluate('robo.stop()')
     except Exception:pass
     await b.close()
   report['passed']=True
  except Exception as e:report['error']=repr(e)
 (ROOT/'static/stunts-emotions-spoken.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print('PASSED',report['passed'],report.get('error',''),flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
