"""Real ASR and spoken-action regressions with synthetic Idris fixtures.
Run after browser_tools_audit.py; the production demo has one live session.
"""
import asyncio,json,os
from pathlib import Path
import numpy as np,soundfile as sf
from playwright.async_api import async_playwright
import browser_mouth_to_ear as fixture
from browser_stunts_emotions_check import INIT,URL
ROOT=Path(__file__).parent
TEXTS=['Hey Robbie, schneid bitte eine Grimasse.','Hi Robby, please do a somersault.']
async def main():
 fixture.TEXTS=TEXTS;fixture.FIXTURES=ROOT/'.runtime/tools-microphone-final'
 await fixture.tts_idle();paths=fixture.fixtures();report={'passed':False,'physical_microphone':False,'turns':[]}
 async with async_playwright() as p:
  try:
   for i,path in enumerate(paths):
    if os.environ.get("ROBO_TEST_NATIVE_ONLY")=="1" and i==0:continue
    await fixture.tts_idle();wave,rate=sf.read(path,dtype='float32');mic=path.with_name('capture-'+path.name)
    sf.write(mic,np.r_[np.zeros(4*rate),wave,np.zeros(24*rate)].astype(np.float32),rate,subtype='PCM_16')
    b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str(mic),'--autoplay-policy=no-user-gesture-required'])
    page=await b.new_page();await page.add_init_script(INIT+"localStorage.setItem('robby.verification',JSON.stringify({verify_input:"+('true' if i==0 else 'false')+",verify_tts:true,serial_tts:false}));")
    try:
     await page.goto(URL+'/desk-robot/');await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled',timeout=120000)
     await page.evaluate('''()=>{window.ev=[];window.fr=[];window.chunks=0;const old=robo.on.message,play=robo.play.bind(robo);robo.on.message=m=>{if(['asr_sentence','avatar_action','reply','turn_done','error','verification_settings','ignored','warning','asr_settings'].includes(m.type))ev.push(m);old(m);};robo.play=x=>{chunks++;play(x);};setInterval(()=>{if(robotFace.actions.active){const s=robotFace.rig.snapshot();fr.push({kind:robotFace.actions.active.kind,flip:s.bodyFlip,heard:!!robo.clock?.position()&&robo.sources.length>0})}},40);}''')
     await page.click('#call');await page.wait_for_function('ev.some(e=>["turn_done","error"].includes(e.type)||e.type==="ignored")',timeout=120000)
     await page.wait_for_function('robotFace.actions.queue.length===0&&!robotFace.actions.pendingRequest',timeout=20000)
     row=await page.evaluate('({events:ev,frames:fr,audio_chunks:chunks})');row['request']=TEXTS[i];report['turns'].append(row)
     rejected=[e for e in row['events'] if e['type'] in ('error','ignored')]
     assert not rejected,[(e.get('source'),e.get('reason') or e.get('error')) for e in rejected]
     action=next(e for e in row['events'] if e['type']=='avatar_action')['steps'][0]
     assert action['kind']==('grimace' if i==0 else 'somersault'),action
     asr=next(e for e in row['events'] if e['type']=='asr_sentence')['asr'];row['asr_model']=asr['model']
     assert asr['model']==('parakeet_ultra' if i==0 else 'nemotron'),asr
     assert row['audio_chunks']>0
     if i==1:assert max(f['flip'] for f in row['frames'])>345
     row['passed']=True;print(TEXTS[i],'PASS',asr['model'],flush=True)
    finally:
     try:await page.evaluate('robo.stop()')
     except Exception:pass
     await b.close()
   report['passed']=True
  except Exception as e:report['error']=str(e)[:2200]
 (ROOT/'logs/tools-microphone-20261114.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print({'passed':report['passed'],'error':report.get('error')},flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
