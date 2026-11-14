"""Actual Parakeet CPU inference on authored TTS with unwanted speech at edges.
No private microphone audio and no second GPU allocation.
"""
import sys,json,time,os
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT.parent/'humaneness-small'),str(ROOT.parent)]
from asr_engine import ParakeetASR
from streaming_boundaries import SpeechBoundaryGate,BoundaryASR
import torchaudio

def read(name):
    x,sr=sf.read(ROOT/'logs/bolt-precision'/name,dtype='float32')
    if x.ndim>1:x=x.mean(1)
    if sr!=48000:x=torchaudio.functional.resample(torch.from_numpy(x),sr,48000).numpy()
    return x

torch.set_num_threads(4)
remote=os.environ.get('SMALL_BOUNDARY_ASR_URL')
asr=BoundaryASR(None if remote else ParakeetASR(device='cpu'))
target=read('bf16_merged-neutral_de-777.wav')
other=read('bf16_all-playful_de-777.wav')
lead=np.concatenate([other[:48000],np.zeros(9600,np.float32)])
wave=np.concatenate([lead,target,np.zeros(9600,np.float32),other])
g=SpeechBoundaryGate('Natürlich, ich erzähle dir eine kleine Geschichte.')
outputs=[];checks=[];tick=time.perf_counter()
for begin in range(0,len(wave),19200):
    outputs.append(g.feed(wave[begin:begin+19200]))
    if g.due():
        s=asr.scores([g])[0];checks.append({'seconds':g.total/48000,**s})
        outputs.append(g.feed([],s))
    if g.done:break
if g.due(final=True):outputs.append(g.feed([],asr.scores([g])[0]))
outputs.append(g.finish())
result={'report':g.report,'wall_seconds':time.perf_counter()-tick,'checks':checks,
        'inserted_lead_seconds':len(lead)/48000,'original_target_seconds':len(target)/48000,
        'output_seconds':sum(len(x) for x in outputs)/48000}
result['passed']=g.report['start_verified'] and g.report['end_verified'] and g.start/48000>=1.05 and g.end/48000<len(wave)/48000-1
out=ROOT/'logs/streaming-boundaries';out.mkdir(exist_ok=True)
suffix='-ultra' if remote else ''
(out/f'injected-edge-test{suffix}.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
sf.write(out/f'injected-edge-input{suffix}.wav',wave,48000);sf.write(out/f'injected-edge-cleaned{suffix}.wav',np.concatenate(outputs),48000)
print(json.dumps({k:v for k,v in result.items() if k!='checks'}),flush=True)
if not result['passed']:raise SystemExit(1)
