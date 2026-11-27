"""HTTPS auto-start smoke test with synthetic browser microphone/permissions."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent
async def main():
 result={'synthetic_permission':True,'physical_microphone':False}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  page=await browser.new_page(viewport={'width':1100,'height':800})
  await page.add_init_script('''localStorage.setItem('robby.autoStartDefaultVersion','1');localStorage.setItem('robby.autoStart','false');localStorage.removeItem('robby.browserBuddyVersion');localStorage.setItem('robby.buddyMode','false');localStorage.setItem('robby.cameraAutoVersion','3');localStorage.setItem('robby.cameraAuto','false');localStorage.setItem('robby.avatar-idle-enabled','false');navigator.mediaDevices.getUserMedia=async()=>{let d=robo.ctx.createMediaStreamDestination();window.testMic=d;return d.stream};''')
  try:
   await page.goto(os.getenv('ROBBY_DEMO_URL','http://127.0.0.1:8793/desk-robot/'),timeout=30000)
   await page.wait_for_function("window.testMic && robo.captureBlocks>30 && document.querySelector('#buddy-status')?.dataset.state==='waiting'",timeout=140000)
   result.update(autostart=await page.evaluate("localStorage.getItem('robby.autoStart')==='true'"),buddy=await page.locator('#buddy-mode').is_checked(),standby_packets=await page.evaluate('robo.metrics.mic_blocks'),status=await page.locator('#buddy-status').text_content())
   result['passed']=result['autostart'] and result['buddy'] and result['standby_packets']==0
  except Exception as e:result['error']=str(e)
  finally:
   try:await page.evaluate('window.robo?.stop()')
   except Exception:pass
   await browser.close()
 (ROOT/'logs/browser-buddy-autostart.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
 if not result.get('passed'):raise SystemExit(1)
asyncio.run(main())
