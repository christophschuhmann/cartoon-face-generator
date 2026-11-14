"""Real HTTPS LLM/TTS/stunt overlap plus isolated browser recovery contracts.

Contract events are explicitly synthetic and run without GPU inference; real
turns below use actual production services. No visitor audio is recorded.
"""
import asyncio,json,time
from pathlib import Path
from playwright.async_api import async_playwright
from browser_stunts_emotions_check import INIT,URL
ROOT=Path(__file__).resolve().parent

async def main():
 report={'passed':False,'physical_microphone':False,'turns':[]};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu','--autoplay-policy=no-user-gesture-required'])
  page=await browser.new_page(viewport={'width':1240,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
  await page.add_init_script(INIT+"localStorage.setItem('robby.verification',JSON.stringify({candidate_search:false,verify_tts:true,verify_input:true,serial_tts:false}));")
  try:
   r=await page.goto(URL+'/desk-robot/');assert r.status==200
   await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled',timeout=180000)
   report['contracts']=await page.evaluate('''async()=>{
    const {AvatarActions}=await import('/static/avatar-actions.js');const {pose}=await import('/static/emotions.js');
    const assert=(v,m)=>{if(!v)throw Error(m)},a=new AvatarActions(),base=pose();a.idleEnabled=false;
    const step={kind:'spin',scope:'body',direction:'clockwise',duration_s:3};
    a.request('late',[step],0,{waitForAudio:true});a.bindRequested(91,'late');
    a.frame(12000,base,{busy:true});assert(!a.queue.length&&a.pendingRequest,'must wait through 12 second TTS retry');
    a.frame(12001,base,{position:{id:90,sample:0},busy:true});assert(!a.queue.length,'wrong reply must not start action');
    a.frame(12002,base,{position:{id:91,sample:0},busy:true});assert(a.active?.kind==='spin','start at actual playback');
    a.frame(13502,base,{position:{id:91,sample:36000},busy:true});assert(a.active?.kind==='spin','motion overlaps speech');
    assert(!a.request('late',[step]),'no duplicate action');a.clear();
    a.request('stop',[step],0,{waitForAudio:true});a.clear();a.frame(14000,base);assert(!a.queue.length,'cancel waits');
    a.request('silent',[step],15000);assert(a.queue.length===1,'explicit silent action immediate');
    a.clear();a.request('failed',[step],0,{waitForAudio:true});a.finishSpeech(100);assert(a.queue.length===1,'terminal no-audio visual fallback');
    robo.on.message({type:'reply',reply_id:500,text:'This complete answer must remain visible.',sentence_index:0});
    robo.on.message({type:'pipeline_metrics',reply_id:500,metrics:{speech_complete:false}});
    robo.on.message({type:'speech_recovery',available:true,may_repeat_sentence:false,sentence_count:2});
    robo.on.message({type:'turn_done'});
    assert(document.querySelector('#recent-robby').textContent.includes('complete answer'),'text retained');
    assert(!document.querySelector('#retry-speech').hidden,'retry available');
    assert(document.querySelector('#latency-status').textContent.includes('incomplete'),'not false success');
    robo.on.message({type:'error',stage:'planning',http_status:429,error:'Language model unavailable.'});
    assert(document.querySelector('#recent-playback-status').textContent.includes('429'),'correct failure stage');
    robo.on.message({type:'speech_recovery',available:false});robotFace.actions.clear();
    return {waits_for_delayed_playback:true,cancellation:true,silent_actions:true,no_duplicate:true,text_retained:true,retry_control:true,stage_specific_error:true};
   }''')
   await page.evaluate('''()=>{window.recoveryEvents=[];window.recoveryFrames=[];
    const old=robo.on.message;robo.on.message=m=>{if(['reply','avatar_action','turn_done','pipeline_metrics','error','busy','speech_recovery','service_status'].includes(m.type))recoveryEvents.push({...m,at:performance.now()});old(m)};
    setInterval(()=>{const s=robotFace.rig.snapshot(),a=robotFace.actions.active,p=robo.clock?.position();
      if(a||p)recoveryFrames.push({at:performance.now(),kind:a?.kind,source:a?.source,audio:!!p,bodySpin:s.bodySpin,bodyFlip:s.bodyFlip});},30);
   }''')
   for text,kind in [('Mach eine Drehung und sprich dabei einen fröhlichen Satz.','spin'),('Mach einen Salto und rede dabei weiter.','somersault'),('Antworte bitte mit vier vollständigen Sätzen über Regenbogen.','long')]:
    await page.evaluate('recoveryEvents=[];recoveryFrames=[]');await page.fill('#message',text);await page.locator('#form').evaluate('f=>f.requestSubmit()')
    await page.wait_for_function('recoveryEvents.some(e=>e.type==="turn_done"||e.type==="error"||e.type==="busy")',timeout=210000)
    await page.wait_for_function('robo.sources.length===0&&robotFace.actions.queue.length===0',timeout=40000)
    data=await page.evaluate('({events:recoveryEvents,frames:recoveryFrames})');report['turns'].append({'request':text,**data})
    assert not [e for e in data['events'] if e['type'] in ('error','busy')],data['events']
    metrics=[e['metrics'] for e in data['events'] if e['type']=='pipeline_metrics'][-1]
    assert metrics['speech_complete'],metrics
    assert any(f['audio'] for f in data['frames'])
    if kind!='long':
     both=[f for f in data['frames'] if f['kind']==kind and f['audio']]
     assert len(both)>=10,(kind,len(both))
     motion='bodySpin' if kind=='spin' else 'bodyFlip'
     assert max(abs(f.get(motion) or 0) for f in data['frames'])>330,(kind,data['frames'])
     row=report['turns'][-1];row['audio_motion_overlap_ms']=round(both[-1]['at']-both[0]['at'])
    else:assert metrics['sentences']>=4,metrics
    print(json.dumps({'kind':kind,'complete':True,'sentences':metrics['sentences'],'first_pcm_ms':metrics.get('first_audio_ms'),'overlap_ms':report['turns'][-1].get('audio_motion_overlap_ms')}),flush=True)
   await page.locator('#system-guide').scroll_into_view_if_needed();await page.screenshot(path=str(ROOT/'logs/recovery-diagrams-desktop.png'),full_page=False)
   report['diagrams']=await page.locator('#system-guide img').evaluate_all('(imgs)=>imgs.map(i=>({src:i.getAttribute("src"),loaded:i.complete&&i.naturalWidth>0}))')
   assert len(report['diagrams'])==4 and all(d['loaded'] for d in report['diagrams'])
   await page.set_viewport_size({'width':390,'height':844});await page.wait_for_timeout(500)
   report['mobile_overflow']=await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
   assert not report['mobile_overflow'];report['passed']=not errors
  except Exception as e:report['error']=repr(e)
  finally:
   report['page_errors']=errors
   try:await page.evaluate('robo.stop()')
   except Exception:pass
   await browser.close()
 (ROOT/'logs/speech-recovery-browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
 print(json.dumps({'passed':report['passed'],'error':report.get('error'),'turns':len(report['turns'])}),flush=True)
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
