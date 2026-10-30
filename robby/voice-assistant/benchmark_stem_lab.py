"""Small reproducible synthetic source-separation pilot; no private recordings."""
import json,os,subprocess,tempfile,time
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from environment_fixtures import music_fixture

ROOT=Path(__file__).resolve().parent

def fit(x,n):return np.pad(x[:n],(0,max(0,n-len(x))))
def sdr(target,estimate):
    target=np.asarray(target);estimate=fit(np.asarray(estimate),len(target));error=estimate-target
    return round(float(10*np.log10((np.sum(target*target)+1e-12)/(np.sum(error*error)+1e-12))),2)

def main():
    with tempfile.TemporaryDirectory(prefix='stem-fixture-',dir=ROOT/'.runtime') as t:
        t=Path(t);n=3*48000;voices=[]
        for i,(voice,text) in enumerate((('en-us','Hello Robby, can you hear me?'),('en-sc','Yes, I can hear you clearly.'))):
            wav=t/f'voice{i}.wav';subprocess.run(['espeak-ng','-v',voice,'-s','150','-w',str(wav),text],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            x,sr=sf.read(wav,dtype='float32');g=np.gcd(sr,48000);x=resample_poly(x,48000//g,sr//g);x=fit(x,n);voices.append(x*.3)
        speech=voices[0]+np.r_[np.zeros(24000,dtype='float32'),voices[1][:-24000]]*.7
        music=fit(resample_poly(music_fixture(3),3,1),n)*.22
        effects=np.zeros(n,dtype='float32');rng=np.random.default_rng(42)
        for start in (int(.9*48000),int(2.2*48000)):
            length=5000;effects[start:start+length]+=rng.standard_normal(length).astype('float32')*np.exp(-np.arange(length)/800)*.18
        mixture=np.clip(speech+music+effects,-.99,.99);source=t/'mix.wav';sf.write(source,mixture,48000,subtype='FLOAT')
        env={**os.environ,'ROBO_TUSS_DEVICE':'cpu','PYTHONPATH':':'.join((str(ROOT/'vendor/tuss'),'/mnt/nvme/moss-15-v2/tuss-env',str(ROOT/'vendor/bandit-infer/src')))}
        t0=time.perf_counter();p=subprocess.Popen([os.sys.executable,str(ROOT/'stem_separation_worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        try:
            assert json.loads(p.stdout.readline())['ready'];p.stdin.write(json.dumps({'model':'tuss','path':str(source),'outdir':str(t),'two_speakers':True})+'\n');p.stdin.flush()
            raw=p.stdout.readline();result=json.loads(raw);assert result['ok'],result
        finally:p.terminate();p.wait(timeout=10)
        item=result['result'];scores={}
        for name,reference in [('speech',speech),('music',music),('effects',effects)]:
            pred,_=sf.read(item['paths'][name],dtype='float32');scores[name]={'mixture_sdr_db':sdr(reference,mixture),'estimate_sdr_db':sdr(reference,pred)}
        item.pop('paths');report={'scope':'One synthetic English 3 s overlap mixture, espeak voices plus generated music and impulses; not representative of real rooms or trained model accuracy.','scores':scores,'timing':item,'wall_s':round(time.perf_counter()-t0,2)}
        (ROOT/'static/stem-lab-synthetic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
