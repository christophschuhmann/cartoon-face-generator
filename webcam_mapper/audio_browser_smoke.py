"""Real browser playback/UI checks; fixture scores test animation, not recognition."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import numpy as np
import soundfile as sf
from .paths import ROOT
from .audio_animation import PATTERNS,canonical_scores,prepare_performance

def fixture():
    names=json.loads((ROOT/'webcam_mapper/models/ears/training_normalization.json').read_text())['score_names'][:40]
    words=[];segments=[]
    for index,slug in enumerate(PATTERNS):
        raw=dict.fromkeys(names,0.)
        for name in names:
            candidate=dict(raw);candidate[name]=3.4
            if canonical_scores(candidate)[slug]>0:raw[name]=3.4;break
        start=1+index*2;end=start+1.4
        group=[{'word':slug,'start':start,'end':end}];words+=group
        segments.append(dict(start=start,end=end,words=group,text=slug,scores_raw=raw,arousal=.75,valence=0))
    return prepare_performance(dict(duration=82,words=words,segments=segments,analysis_seconds=0,
        envelope={'step':.02,'values':[.8]*4100},models={'asr':'TEST FIXTURE','emotion':'TEST FIXTURE'}))

def main():
    from playwright.sync_api import sync_playwright
    parser=argparse.ArgumentParser();parser.add_argument('--real-audio',type=Path);args=parser.parse_args()
    out=ROOT/'webcam_mapper/output/verification';out.mkdir(exist_ok=True,parents=True)
    data=fixture();wav=args.real_audio or out/'audio_browser_fixture.wav'
    if not args.real_audio:sf.write(wav,np.zeros(82*16000,dtype=np.float32),16000)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    url=f'http://127.0.0.1:{port}';errors=[]
    with (out/'audio_browser.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-m','webcam_mapper.app','--serve','--port',str(port),'--emotion-mode','motion'],cwd=ROOT,stdout=log,stderr=log)
        try:
            for _ in range(1200):
                try:urllib.request.urlopen(url+'/healthz',timeout=.5).close();break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='msedge',headless=True,args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
                    '--use-file-for-fake-video-capture='+str(out/'synthetic_fake_camera.y4m')])
                context=browser.new_context(viewport={'width':1300,'height':1000});context.grant_permissions(['camera'],origin=url)
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.add_init_script("""window.cameraTestTracks=[];const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                  navigator.mediaDevices.getUserMedia=async options=>{const stream=await original(options);window.cameraTestTracks.push(...stream.getTracks());return stream;};""")
                if not args.real_audio:page.route('**/api/audio/ready',lambda r:r.fulfill(json={'ready':True,'message':'Test fixture ready'}))
                page.goto(url);page.wait_for_selector('#avatar svg');page.locator('#start').click()
                page.wait_for_function("document.querySelector('#status').textContent.includes('Gesicht erkannt')",timeout=30000)
                page.locator('#mode-audio').click();page.wait_for_selector('#audio-panel',state='visible')
                page.wait_for_function("document.querySelector('#mode-audio').getAttribute('aria-pressed')==='true'")
                assert page.evaluate("document.querySelector('#camera').srcObject===null")
                assert page.request.post(url+'/api/frame',data=b'x').status==409
                if not args.real_audio:
                    page.route('**/api/audio/analyze*',lambda r:r.fulfill(json={'id':'fixture'},status=202))
                    page.route('**/api/audio/status/fixture',lambda r:r.fulfill(json={'state':'ready','stage':'complete','progress':1}))
                    page.route('**/api/audio/result/fixture',lambda r:r.fulfill(json=data))
                page.locator('#audio-file').set_input_files(wav)
                with page.expect_response(lambda r:'/api/audio/result/' in r.url,timeout=600000) as response:
                    page.locator('#audio-analyze').click()
                actual=response.value.json()
                page.wait_for_selector('#audio-playback',state='visible',timeout=30000)
                assert page.locator('#audio-transcript button').count()==len(actual['segments'])
                if args.real_audio:
                    assert len(actual['words'])>=3
                    assert all(len(s['scores_raw'])==40 for s in actual['segments'])
                    print(json.dumps({'real_analysis':actual['analysis_seconds'],'transcript':actual['transcript'],'stage_seconds':actual['stage_seconds']},ensure_ascii=False),flush=True)
                checks=page.evaluate('''async data=>{
                    const {AudioPerformance}=await import('/static/audio-player.mjs');
                    const holder=document.createElement('div'),clock={currentTime:0};
                    const animation=new AudioPerformance(holder,clock);animation.load(data);
                    let allFinite=true,closed=true,distinct=new Set();
                    for(const s of data.segments){
                      for(const t of [s.start-.001,s.start,s.start+.15,s.end,s.end+.4]){
                        animation.paint(t);allFinite &&= !/NaN|Infinity|undefined/.test(holder.innerHTML);
                      }
                      animation.paint(s.start+.6);distinct.add(holder.querySelector('#mouth_upper').getAttribute('d'));
                      animation.paint(s.end+.1);closed &&= Number(holder.querySelector('#mouth_fill').getAttribute('opacity'))===0;
                    }
                    animation.paint(3.6);const first=holder.innerHTML;animation.paint(50);animation.paint(3.6);
                    const deterministic=holder.innerHTML===first;animation.stop();
                    return {allFinite,closed,distinct:distinct.size,deterministic};
                }''',data)
                assert checks==dict(allFinite=True,closed=True,distinct=40,deterministic=True),checks
                head_checks=page.evaluate('''async data=>{
                    const {AudioPerformance}=await import('/static/audio-player.mjs');
                    const {ellipseMatrix}=await import('/static/head-follow.mjs');
                    const holder=document.createElement('div');document.body.append(holder);
                    const animation=new AudioPerformance(holder,{currentTime:5.6,paused:true});animation.load(data);
                    const initial=holder.querySelector('#nose').getAttribute('d'),poses=new Set();
                    let clipped=true,finite=true,eyeContact=true;animation.headFollow=true;animation.headMix=1;
                    for(const x of [-1,0,1])for(const y of [-1,0,1]){
                      animation.viewer={x,y,headX:x,headY:y,weight:1};animation.paint(5.6);
                      poses.add(holder.querySelector('#nose').getAttribute('d'));
                      finite &&= !/NaN|Infinity|undefined/.test(holder.innerHTML);
                      for(const side of ['left','right']){
                        const pupil=holder.querySelector('#'+side+'_pupil');
                        clipped &&=pupil.getAttribute('transform')===holder.querySelector('#'+side+'_pupil_geometry').getAttribute('transform');
                        const upper=holder.querySelector('#'+side+'_eye_upper').getBBox(),lower=holder.querySelector('#'+side+'_eye_lower').getBBox();
                        const [a,b,c,d,e,f]=ellipseMatrix(pupil),px=Number(pupil.getAttribute('cx')),py=Number(pupil.getAttribute('cy'));
                        const dx=a*px+c*py+e-(upper.x+upper.width/2),dy=b*px+d*py+f-(upper.y+lower.y+lower.height)/2;
                        if(x)eyeContact &&=dx*x<0;
                        if(y)eyeContact &&=dy*y<0;
                      }
                    }
                    animation.headMix=0;animation.paint(5.6);
                    const optional=holder.querySelector('#nose').getAttribute('d')===initial;
                    animation.stop();holder.remove();return {directions:poses.size,finite,clipped,optional,eyeContact};
                }''',data)
                assert head_checks==dict(directions=9,finite=True,clipped=True,optional=True,eyeContact=True),head_checks
                page.evaluate("document.querySelector('#audio-playback').currentTime=5.6")
                page.wait_for_timeout(150);page.screenshot(path=str(out/'audio_anger.png'),full_page=True)
                before=page.locator('#avatar').inner_html();page.wait_for_timeout(160);assert page.locator('#avatar').inner_html()==before
                page.evaluate("document.querySelector('#audio-playback').play()")
                page.wait_for_function("document.querySelector('#audio-viewer-status').textContent.includes('Blickkontakt aktiv')",timeout=20000)
                assert page.evaluate("window.cameraTestTracks.some(t=>t.readyState==='live')")
                assert page.locator('#avatar').inner_html()!=before
                assert not page.locator('#audio-head-follow').is_checked()
                page.locator('#audio-head-follow').check()
                assert page.evaluate("JSON.parse(localStorage.getItem('audio-preferences')).headFollow")
                # Exercise actual CPU eye-position tracking above, then check
                # controlled screen corners with the same camera response path.
                target={'x':.2,'y':.18}
                page.route('**/api/audio/viewer',lambda r:r.fulfill(json={'tracking':True,'position':target}))
                page.wait_for_timeout(1100)
                up_right,geometry=page.evaluate("['left_pupil','left_pupil_geometry'].map(id=>document.querySelector('#avatar #'+id).getAttribute('transform'))")
                assert up_right==geometry,(up_right,geometry)
                page.screenshot(path=str(out/'audio_viewer_up_right.png'),full_page=True)
                target.update(x=.8,y=.7);page.wait_for_timeout(1100)
                down_left=page.locator('#avatar #left_pupil').get_attribute('transform')
                assert up_right!=down_left
                page.screenshot(path=str(out/'audio_viewer_down_left.png'),full_page=True)
                page.locator('#audio-head-follow').uncheck();page.wait_for_timeout(1100)
                assert page.evaluate("window.cameraTestTracks.some(t=>t.readyState==='live')")
                page.locator('#audio-head-follow').check()
                page.evaluate("document.querySelector('#audio-playback').pause()")
                page.wait_for_function("window.cameraTestTracks.every(t=>t.readyState==='ended')")
                page.locator('#mode-webcam').click();page.wait_for_selector('#preview-card',state='visible')
                assert page.locator('#start').is_enabled()
                page.locator('#mode-audio').click();page.wait_for_selector('#audio-panel',state='visible')
                page.wait_for_function("!document.querySelector('#audio-analyze').disabled")
                assert page.locator('#audio-head-follow').is_checked()
                page.locator('#audio-eye-contact').uncheck()
                assert page.locator('#audio-head-follow').is_disabled()
                page.locator('#audio-eye-contact').check()
                assert page.locator('#audio-head-follow').is_enabled()
                assert not errors,errors
                browser.close()
            report={'input':str(wav) if args.real_audio else 'Synthetic known scores, silent WAV; recognition tested separately','checks':checks,
                'camera_released':True,'viewer_tracking':True,'viewer_corners':True,'camera_released_on_pause':True,
                'seek_pause_resume':True,'mode_switch':True,'head_follow':head_checks,'head_toggle':True,'javascript_errors':errors}
            if args.real_audio:report['real_analysis']={k:actual[k] for k in ('duration','transcript','analysis_seconds','stage_seconds','models')}
            (out/'audio_browser_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
        finally:
            server.terminate();server.wait(timeout=10)

if __name__=='__main__':main()
