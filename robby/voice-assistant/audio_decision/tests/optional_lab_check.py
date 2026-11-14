"""Verify idle-model handoff to the existing audio/video lab, then back to d1."""
import json,time,tempfile,subprocess
from pathlib import Path
import requests
report={};start=time.perf_counter()
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'fixture.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=green:s=320x240:r=5:d=3','-i',str(Path(__file__).parent/'fixtures/beeps.wav'),'-t','3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(p)],check=True)
 with p.open('rb') as f:
  r=requests.post('http://127.0.0.1:8810/analyze',files={'media':('fixture.mp4',f,'video/mp4')},data={'window':'3','stride':'1','separator':'off','model_options':json.dumps({'audio':True,'video':True,'sound_caption':False,'ears':False,'asr':False,'minicpm':False,'salmon':False})},timeout=400)
 report['av_status']=r.status_code;report['av_elapsed_s']=time.perf_counter()-start
 try:report['av_result']=r.json()
 except Exception:report['av_error']=r.text[:1000]
report['robby_ready']=requests.get('http://127.0.0.1:8793/api/state').json().get('ready')
report['d1_status_after_av']=requests.get('http://127.0.0.1:8815/api/status').json()
Path(__file__).with_name('optional-lab-result.json').write_text(json.dumps(report,indent=2))
print('AV',report['av_status'],'seconds',round(report['av_elapsed_s'],1),'Robby ready',report['robby_ready'],'d1 unloaded',not report['d1_status_after_av']['loaded'])
assert r.status_code==200,report.get('av_error',r.text[:500]);assert report['robby_ready']
