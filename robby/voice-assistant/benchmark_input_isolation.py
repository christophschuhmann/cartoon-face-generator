"""CPU-only exploratory comparison; does not change the live microphone path.

Run in an isolated environment with alkove==0.4.0, voxlock==1.3.0,
numpy and soundfile. --asr subsequently scores saved outputs using the already
running Parakeet v3 worker. Inputs are authored synthetic regression fixtures.
"""
import argparse,hashlib,json,os,re,subprocess,time,urllib.request
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'logs/input-isolation';OUT.mkdir(exist_ok=True)
FIXTURES=Path(os.environ.get('ROBBY_TEST_FIXTURES','/mnt/nvme/robo-speaker-studies/speaker-live-fixtures'))
SR=16000

def audio(name):
    raw=subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(FIXTURES/(name+'.mp3')),
                                 '-ar',str(SR),'-ac','1','-f','f32le','pipe:1'])
    x=np.frombuffer(raw,'<f4').copy()
    return x*(.055/max(1e-8,float(np.sqrt(np.mean(x*x)))))

def sisdr(y,x):
    y=y.astype(np.float64);x=x.astype(np.float64);y-=y.mean();x-=x.mean()
    target=x*(np.dot(y,x)/max(1e-12,np.dot(x,x)))
    return float(10*np.log10((np.sum(target**2)+1e-12)/(np.sum((y-target)**2)+1e-12)))

def wer(ref,hyp):
    a=re.findall(r'\w+',ref.casefold());b=re.findall(r'\w+',hyp.casefold());row=list(range(len(b)+1))
    for i,w in enumerate(a,1):
        nxt=[i]
        for j,v in enumerate(b,1):nxt.append(min(row[j]+1,nxt[-1]+1,row[j-1]+(w!=v)))
        row=nxt
    return row[-1]/max(1,len(a))

def benchmark():
    # Keep downloads off the nearly full NVMe and out of production packages.
    os.environ['HF_HUB_CACHE']=str(Path.home()/'.cache/robby-input-isolation/hub')
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
    import alkove,voxlock
    from voxlock.core import REVISION
    start=time.perf_counter();models=alkove.Models.load(['focus','timbre','cue'])
    alkove_load=time.perf_counter()-start
    start=time.perf_counter();vl=voxlock.VoxLock(threads=1)
    vox_load=time.perf_counter()-start
    report={'date':'2026-11-11','synthetic_only':True,'physical_room_test':False,
            'cpu':'AMD Ryzen Threadripper 3960X','threads':1,'gpu_used_for_filters':False,
            'packages':{'alkove':'0.4.0','voxlock':'1.3.0'},'voxlock_revision':REVISION,
            'alkove_manifest':alkove.MANIFEST,'load_including_download_s':{'alkove':alkove_load,'voxlock':vox_load},
            'rows':[],'limitations':['Two synthetic German voices, one synthetic TV source; not a population benchmark.',
            'CPU processing time excludes chunk accumulation, network, VAD, ASR and browser buffering.',
            'Separate clean enrollment utterance; no unattended live enrollment.',
            'No physical reverb, far-field microphones or emotional delivery robustness measured.']}
    background=audio('background')
    for speaker,spoken in [('christoph','Kannst du mir eine kleine Geschichte erzählen?'),('selma','Was können wir heute zusammen machen?')]:
        enrollment=audio(speaker+'-intro');target=audio(speaker+'-followup'+('-clear' if speaker=='selma' else ''))
        start=time.perf_counter();print_=alkove.Timbre(models).embed(enrollment);embed_ms=(time.perf_counter()-start)*1000
        n=SR+len(target)+4*SR;oracle=np.zeros(n,np.float32);oracle[SR:SR+len(target)]=target
        for level in (0.,.5,1.):
            mixture=oracle+np.resize(background,n)*level
            case=f'{speaker}-bg{level:g}';sf.write(OUT/(case+'-raw.wav'),mixture,SR,subtype='FLOAT')
            base={'speaker':speaker,'case':case,'background_gain':level,'reference_text':spoken,
                  'seconds':n/SR,'target_start_s':1.,'target_end_s':1+len(target)/SR,
                  'input_sha256':hashlib.sha256(mixture.tobytes()).hexdigest(),
                  'raw_si_sdr_db':sisdr(mixture[SR:SR+len(target)],target)}
            # 16 ms Focus, efficient 40 ms VoxLock. Separate state for every run.
            for name,chunk in [('alkove',256),('voxlock',640)]:
                start=time.perf_counter()
                stream=(alkove.Processor(models,focus=True,voiceprint=print_,cue=False,rate=SR)
                        if name=='alkove' else vl.stream(enrollment))
                setup_ms=(time.perf_counter()-start)*1000+(embed_ms if name=='alkove' else 0)
                outputs=[];times=[];first_output=None;started=time.perf_counter()
                for at in range(0,n,chunk):
                    t=time.perf_counter();out=stream.push(mixture[at:at+chunk])
                    times.append((time.perf_counter()-t)*1000)
                    if name=='alkove':out=out.audio
                    if len(out) and first_output is None:first_output=(at+len(mixture[at:at+chunk]))/SR
                    outputs.append(out)
                tail=stream.end().audio if name=='alkove' else stream.flush();outputs.append(tail)
                elapsed=time.perf_counter()-started;y=np.concatenate(outputs)
                assert len(y)==n,(name,len(y),n)
                assert np.isfinite(y).all()
                sf.write(OUT/(case+'-'+name+'.wav'),y,SR,subtype='FLOAT')
                bg=mixture[SR+len(target)+SR:];residual=y[SR+len(target)+SR:]
                row={**base,'model':name,'chunk_ms':chunk/SR*1000,'setup_ms':round(setup_ms,2),
                     'rtf':round(elapsed/(n/SR),4),'processing_ms':round(elapsed*1000,2),
                     'chunk_p50_ms':round(float(np.median(times)),3),'chunk_p95_ms':round(float(np.percentile(times,95)),3),
                     'first_output_after_input_ms':first_output*1000,
                     'target_si_sdr_db':round(sisdr(y[SR:SR+len(target)],target),2),
                     'background_only_attenuation_db':round(float(10*np.log10((np.mean(bg**2)+1e-12)/(np.mean(residual**2)+1e-12))),2) if level else None}
                report['rows'].append(row);(OUT/'report.json').write_text(json.dumps(report,indent=2))
                print(json.dumps(row),flush=True)

def score_asr():
    path=OUT/'report.json';report=json.loads(path.read_text());raw={}
    for r in report['rows']:
        for model in ('raw',r['model']):
            key=(r['case'],model)
            if key not in raw:
                y,sr=sf.read(OUT/(r['case']+'-'+model+'.wav'),dtype='float32')
                # Whole timeline intentionally contains background-only tails.
                req=urllib.request.Request('http://127.0.0.1:8801/transcribe/parakeet_v3',data=y.astype('<f4').tobytes(),
                    headers={'Content-Type':'application/octet-stream'},method='POST')
                d=json.load(urllib.request.urlopen(req,timeout=90));raw[key]={'text':d.get('text',''),'wer':wer(r['reference_text'],d.get('text',''))}
            r[model+'_asr']=raw[key]
        path.write_text(json.dumps(report,indent=2));print(r['case'],r['model'],r[r['model']+'_asr'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--asr',action='store_true');args=parser.parse_args()
    score_asr() if args.asr else benchmark()
