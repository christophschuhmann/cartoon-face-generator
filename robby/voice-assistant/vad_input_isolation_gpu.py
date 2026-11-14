"""Check actual Silero VAD on target and TV-only intervals, without ASR gain normalization."""
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
import torch

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'logs/input-isolation-gpu'
sys.path.append(str(Path.home()/'.cache/robby-input-isolation/torch-deps'))
from silero_vad import load_silero_vad
torch.set_num_threads(2)
model=load_silero_vad().eval()


@torch.inference_mode()
def measure(path,start,end):
    x,sr=sf.read(path,dtype='float32');assert sr==16000
    model.reset_states()
    ts=[];ps=[]
    for at in range(0,len(x),512):
        block=np.pad(x[at:at+512],(0,max(0,at+512-len(x))))
        ps.append(float(model(torch.from_numpy(block),16000)))
        ts.append((at+256)/16000)
    ts=np.array(ts);ps=np.array(ps)
    def portion(mask):
        p=ps[mask]
        return None if not len(p) else {'fraction_over_0_5':float(np.mean(p>.5)),
            'mean_probability':float(np.mean(p)), 'max_probability':float(np.max(p)), 'frames':len(p)}
    return {'target':portion((ts>=start)&(ts<=end)),
            'background_only':portion(ts>=end+1), 'threshold':.5, 'frame_ms':32,
            'model':'silero-vad 6.2.1 bundled TorchScript', 'causal':True}


cache={}
for path in sorted(OUT.glob('*.json')):
    d=json.loads(path.read_text())
    if d.get('status')!='completed' or not d.get('arguments',{}).get('quality'):continue
    for r in d['rows']:
        if 'vad' in r:continue
        r['vad']=measure(OUT/r['audio'],r['target_start_s'],r['target_end_s'])
        raw=ROOT/'logs/input-isolation'/(r['case']+'-raw.wav')
        if r['case'] not in cache:cache[r['case']]=measure(raw,r['target_start_s'],r['target_end_s'])
        r['raw_vad']=cache[r['case']]
    path.write_text(json.dumps(d,indent=2))
    print(d['label'],[(r['case'],round(r['vad']['background_only']['fraction_over_0_5'],3)) for r in d['rows']],flush=True)
