"""HTTP/security/codec regression checks against the real local origin."""
import io,json,time,subprocess,tempfile
from pathlib import Path
import requests
BASE='http://127.0.0.1:8793/audio-decision/api/'
s=requests.Session();s.headers['X-Audio-Decision']='1';s.post(BASE+'session').raise_for_status();checks=[]
fixture=Path(__file__).parent/'fixtures/beeps.wav'
with tempfile.TemporaryDirectory() as directory:
 for extension,codec in [('wav','pcm_s16le'),('mp3','libmp3lame'),('m4a','aac'),('ogg','libopus')]:
  p=Path(directory)/('test.'+extension);subprocess.run(['ffmpeg','-v','error','-i',str(fixture),'-t','1','-c:a',codec,str(p)],check=True)
  r=s.post(BASE+'upload',data=p.read_bytes(),headers={'X-Filename':p.name});r.raise_for_status();a=r.json();assert .9<a['duration_s']<1.2,(extension,a['duration_s'])
  audio=s.get(BASE+'audio/'+a['asset_id'],headers={'Range':'bytes=0-99'});assert audio.status_code==206 and len(audio.content)==100
  checks.append(extension+' upload and HTTP Range playback')
  asset=a['asset_id']
 other=requests.Session();other.headers['X-Audio-Decision']='1';other.post(BASE+'session').raise_for_status();assert other.get(BASE+'audio/'+asset).status_code==404;checks.append('Cross-session recording isolation')
 assert s.post(BASE+'upload',data=b'bad').status_code==422;checks.append('Invalid media rejected')
 assert s.post(BASE+'session',headers={'Origin':'https://untrusted.invalid'}).status_code==403;checks.append('Cross-origin writes rejected')
 assert requests.get('http://127.0.0.1:8793/audio-decision/internal/offload').status_code==404;checks.append('Private model controls not exposed')
 # An actual audio inference verifies job caching and context-specific keys.
 settings={'taxonomy':'classic','selected_ids':['/m/09x0r','/m/02fs_r'],'hop_ms':300,'method':'multilabel','group_size':16}
 def submit(config):
  r=s.post(BASE+'analyze',json={'asset_id':asset,'settings':config});r.raise_for_status();return r.json()
 first=submit(settings)
 for _ in range(180):
  j=s.get(BASE+'jobs/'+first['job_id']).json()
  if j['state']!='running':break
  time.sleep(1)
 assert j['state']=='done',j.get('error');assert all(len(r['raw'])==2 and all(p is not None for p in r['raw']) for r in j['rows'])
 second=submit(settings);assert second['cached'] and second['job_id']==first['job_id'];checks.append('Exact analysis cache hit')
 third=submit(settings|{'context':'A dog is expected; use evidence only.'});assert not third['cached'] and third['job_id']!=first['job_id'];checks.append('Context change starts an independent analysis')
 # Admission control is global across distinct browser capabilities.
 r=other.post(BASE+'analyze',json={'asset_id':asset,'settings':settings});assert r.status_code==404
 for _ in range(180):
  j=s.get(BASE+'jobs/'+third['job_id']).json()
  if j['state']!='running':break
  time.sleep(1)
 assert j['state']=='done',j.get('error')
 export=s.get(BASE+'export/'+third['job_id']).json();assert len(export['raw_scores'])==len(export['smoothed_scores'])
 assert s.delete(BASE+'library').status_code==200;assert s.get(BASE+'audio/'+asset).status_code==404;checks.append('Private cache reset deletes audio and results')
Path(__file__).with_name('api-result.json').write_text(json.dumps({'checks':checks,'completed':True},indent=2));print('\n'.join(checks))
