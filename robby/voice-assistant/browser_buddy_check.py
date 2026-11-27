"""Smoke test the public browser path with generated audio, not a real microphone."""
import asyncio,base64,json,time,sys,os
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent
FIX=Path(os.environ.get('BUDDY_FIXTURES','/mnt/nvme/moss-15-v2/buddy-test'))

def audio(name):
 import subprocess
 voice=os.environ.get('BUDDY_TEST_VOICE','')
 path=FIX/'variants'/(voice+'_'+name+'.wav') if voice and name in ('hey','go','stop') else FIX/(name+'.wav')
 return base64.b64encode(subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-ar','16000','-ac','1','-f','f32le','pipe:1'],capture_output=True,check=True).stdout).decode()

async def main():
 events=[]; errors=[];out={'physical_microphone_test':False,'synthetic_fixture':True,'fixture_voice':os.environ.get('BUDDY_TEST_VOICE','default'),'mobile_emulation':os.environ.get('BUDDY_TEST_MOBILE')=='1'}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  page=await browser.new_page(**(p.devices['Pixel 5'] if out['mobile_emulation'] else {'viewport':{'width':1280,'height':900}}))
  await page.add_init_script('''localStorage.setItem('robby.autoStartDefaultVersion','1');localStorage.setItem('robby.autoStart','false');localStorage.setItem('robby.browserBuddyVersion','1');localStorage.setItem('robby.cameraAutoVersion','3');localStorage.setItem('robby.cameraAuto','false');localStorage.setItem('robby.buddyMode','true');localStorage.setItem('robby.asrModel','parakeet_ultra');localStorage.setItem('robby.avatar-idle-enabled','false');
    navigator.mediaDevices.getUserMedia=async()=>{let d=robo.ctx.createMediaStreamDestination();window.testMic=d;return d.stream};
    window.testSpeak=async(encoded)=>{const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)),x=new Float32Array(bytes.buffer),ctx=robo.ctx,b=ctx.createBuffer(1,x.length+16000,16000);b.getChannelData(0).set(x);const s=ctx.createBufferSource();s.buffer=b;s.connect(testMic);await new Promise(resolve=>{s.onended=resolve;s.start()});s.disconnect()};''')
  isolation=os.getenv('BUDDY_TEST_ISOLATION','off')
  if isolation not in ('off','voxlock','scicom'):raise ValueError('Invalid normal-mode filter')
  await page.add_init_script("localStorage.setItem('robby.inputIsolation',"+json.dumps(isolation)+");")
  out['saved_normal_filter']=isolation
  def receive(raw):
   if isinstance(raw,str):
    try:
     e=json.loads(raw)
     if e.get('type') in ('ready','buddy_wake','asr_settings','asr_sentence','asr_preview','error','reply','turn_done','input_isolation','endpoint','ignored'):events.append({'t':time.monotonic(),**e})
    except ValueError:pass
  page.on('websocket',lambda ws:ws.on('framereceived',receive));page.on('pageerror',lambda e:errors.append(str(e)))
  async def wait(pred,seconds):
   deadline=time.monotonic()+seconds
   while time.monotonic()<deadline:
    if pred():return
    await page.wait_for_timeout(100)
   raise TimeoutError('expected event did not arrive')
  try:
   for _ in range(90):
    try:
     r=await page.goto(os.getenv('ROBBY_DEMO_URL','http://127.0.0.1:8793/desk-robot/'),timeout=30000)
     if r and r.status==200:break
    except Exception:pass
    await page.wait_for_timeout(1000)
   else:raise TimeoutError('Robby page unavailable')
   out['http_status']=r.status
   await page.wait_for_function('window.robo && !document.querySelector("#call").disabled',timeout=150000)
   guide=page.locator('#buddy-guide')
   assert await guide.is_visible()
   assert await guide.locator('dt').all_text_contents()==['“Hey Buddy”','“Go Buddy”','“Stop Buddy”']
   out['buddy_default_checked']=await page.locator('#buddy-mode').is_checked()
   await page.click('#call');await page.wait_for_function('window.testMic && robo.captureBlocks>30',timeout=30000)
   await wait(lambda:any(e['type']=='asr_settings' and e.get('selected_model')=='parakeet_ultra' for e in events),30)
   await page.wait_for_function("document.querySelector('#buddy-status')?.dataset.state==='waiting'",timeout=120000)
   await wait(lambda:any(e['type']=='input_isolation' and e.get('paused_for_buddy') and e.get('selected')=='off' and e.get('preferred')==isolation for e in events),12)
   assert await page.locator('#input-isolation-model').is_disabled()
   assert await page.locator('#input-isolation-model').input_value()=='off'
   assert await page.locator('#wake-mode').is_disabled()
   assert await page.evaluate("localStorage.getItem('robby.inputIsolation')") == isolation
   out['buddy_isolation_off']=True
   await page.wait_for_timeout(1100);out['asr_in_standby']=any(e['type']=='asr_preview' for e in events)
   out['standby_packets_sent']=await page.evaluate('robo.metrics.mic_blocks')
   await page.evaluate('x=>testSpeak(x)',audio('hey'));await page.wait_for_function("document.querySelector('#buddy-status')?.dataset.state==='recording'",timeout=20000)
   await page.evaluate('x=>testSpeak(x)',audio('request'));await page.evaluate('x=>testSpeak(x)',audio('stop'))
   await page.wait_for_function("document.querySelector('#buddy-status')?.textContent.includes('Stopped.')",timeout=25000)
   out['stop_discarded']=not any(e['type']=='asr_sentence' for e in events)
   if '--controls-only' not in sys.argv:
    await page.evaluate('x=>testSpeak(x)',audio('hey'));await page.wait_for_function("document.querySelector('#buddy-status')?.dataset.state==='recording'",timeout=20000)
    await page.evaluate('x=>testSpeak(x)',audio('request'));await page.evaluate('x=>testSpeak(x)',audio('go'))
    await wait(lambda:any(e['type']=='asr_sentence' and e.get('reason')=='Go Buddy' for e in events),20)
    out['go_submitted']=True
    await wait(lambda:any(e['type'] in ('reply','error') for e in events),90)
    out['response_received']=any(e['type']=='reply' for e in events)
    await page.wait_for_function('robo.sources.length>0',timeout=120000)
    assert any(e['type']=='endpoint' and e.get('asr',{}).get('buddy_control') for e in events)
    assert not any(e['type']=='ignored' and e.get('source')=='input_isolation' for e in events)
    out['spoken_audio_scheduled']=True
    await page.locator('#buddy-mode').uncheck()
    await page.wait_for_function('robo.metrics.mic_blocks>0',timeout=10000)
    await wait(lambda:any(e['type']=='input_isolation' and not e.get('paused_for_buddy') and e.get('selected')==isolation for e in events),12)
    assert not await guide.is_visible()
    assert await page.locator('#input-isolation-model').is_enabled()
    assert await page.locator('#input-isolation-model').input_value()==isolation
    out['normal_mode_restored']=True
   out['passed']=out['http_status']==200 and out['buddy_default_checked'] and not out['asr_in_standby'] and out['standby_packets_sent']==0 and out['stop_discarded'] and ('--controls-only' in sys.argv or out.get('go_submitted') and out.get('response_received') and out.get('spoken_audio_scheduled') and out.get('normal_mode_restored')) and not errors
  except Exception as e:out['error']=type(e).__name__+': '+str(e)
  finally:
   out['page_errors']=errors;out['buddy_status']=await page.locator('#buddy-status').text_content() if await page.locator('#buddy-status').count() else None;out['scores']=await page.evaluate('window.buddyWakeDiagnostics?.()||[]');out['events']=[{k:v for k,v in e.items() if k in ('type','state','reason','command_hint')} for e in events]
   try:await page.evaluate('window.robo?.stop()')
   except Exception:pass
   await browser.close()
 (ROOT/'logs'/('browser-buddy-smoke-'+out['fixture_voice']+('-'+isolation if isolation!='off' else '')+('-mobile' if out['mobile_emulation'] else '')+'.json')).write_text(json.dumps(out,indent=2));print(json.dumps(out),flush=True)
 if not out.get('passed'):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
