"""Pinned real Moondream ASR, synthetic speech fixtures, no production imports."""
import json,os,time
from pathlib import Path
import numpy as np
from benchmark_input_isolation import audio,wer

REVISIONS={'redux':'2bf128600aac4b16946f7ed8372e56117fe5e23b','ultra':'73175eb7aeb0d82f1e2a6b53b3aabc10a90bcd0b'}
def model_path(name):
    return str(Path.home()/f'.cache/robby-photon/models/models--moondream--parakeet-{name}/snapshots'/REVISIONS[name])
def main():
    import torch,moondream
    torch.set_num_threads(4)
    report=[]
    for name,device in [('ultra','cuda'),('redux','cpu'),('redux','cuda')]:
        t=time.perf_counter();print('Loading',name,device,flush=True)
        try:
            model=moondream.photon('moondream/parakeet-'+name,model_path=model_path(name),device=device,single_pass_batch_capacity=4,cpu_threads=4,decode_path='native')
            load=(time.perf_counter()-t)*1000
            rows=[]
            for fixture,ref in [('christoph-followup','Kannst du mir eine kleine Geschichte erzählen?'),('selma-followup-clear','Was können wir heute zusammen machen?')]:
                clean=audio(fixture)
                for gain in (0.,.3):
                    x=clean+gain*np.resize(audio('background'),len(clean))
                    for repeat in range(3):
                        t=time.perf_counter();r=model.transcribe(audio=x,sample_rate=16000,timestamps='word');ms=(time.perf_counter()-t)*1000
                        rows.append({'fixture':fixture,'background_gain':gain,'repeat':repeat,'ms':ms,'wer':wer(ref,r['text']),'result':r})
                        print(name,device,round(ms,1),r['text'],flush=True)
            report.append({'model':name,'device':device,'load_ms':load,'rows':rows})
            model.close()
        except Exception as e:
            import traceback;traceback.print_exc()
            report.append({'model':name,'device':device,'error':str(e)})
        Path('logs/isolation-latency/photon.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
