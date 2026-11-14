"""Real GPU probe; uses authored beeps/silence, never simulated model outputs."""
import json,time
from pathlib import Path
import numpy as np,requests
from optional_lab_gpu import Lease
from audio_decision.engine import Engine

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    with Lease():
        r=requests.post('http://127.0.0.1:8810/internal/offload',timeout=30);r.raise_for_status()
        engine=Engine();engine.load();wave=np.zeros(2*16000,dtype=np.float32)
        wave[-3200:]=.2*np.sin(2*np.pi*880*np.arange(3200)/16000)
        classes=[{'id':'beep','name':'Beep, bleep'},{'id':'speech','name':'Speech'},{'id':'music','name':'Music'}]
        outputs=[]
        for repeat in (False,True):
            for method in ('binary','multilabel'):
                out=engine.analyze(wave,3200,classes,{'repeat_target':repeat,'method':method,'group_size':16})
                outputs.append({'repeat_target':repeat,'method':method,**out})
        result={'model_load_ms':engine.load_ms,'outputs':outputs}
        (root/'probe-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
