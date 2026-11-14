"""Real Ultra ASR on authored audio with injected unwanted leading/trailing speech.

This isolates verification safety; the producer cadence is simulated and these
timings must NOT be reported as measured TTS model throughput.
"""
import argparse,json,os,sys,time
from pathlib import Path
import numpy as np,soundfile as sf
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT.parent/'humaneness-small'),str(ROOT.parent)]
os.environ.setdefault('SMALL_BOUNDARY_ASR_URL','http://127.0.0.1:8822')
from parallel_boundaries import ParallelBoundaryStream
from streaming_boundaries import SpeechBoundaryGate,BoundaryASR,UnverifiedSpeechError
import torch,torchaudio
torch.set_num_threads(4)
def read(name):
 x,sr=sf.read(ROOT/'logs/bolt-precision'/name,dtype='float32')
 if x.ndim>1:x=x.mean(1)
 return torchaudio.functional.resample(torch.from_numpy(x),sr,48000).numpy() if sr!=48000 else x
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--label',default='injected');args=parser.parse_args()
 target=read('bf16_merged-neutral_de-777.wav');other=read('bf16_all-playful_de-777.wav')
 lead=np.concatenate([other[:48000],np.zeros(9600,np.float32)])
 fixtures={'clean':target,'injected':np.concatenate([lead,target,np.zeros(9600,np.float32),other]),
           'wrong_only':other,'silence':np.zeros(3*48000,np.float32)}
 results=[];out=ROOT/'logs/streaming-boundaries';out.mkdir(exist_ok=True)
 weak=out/'original-777-raw.wav'
 if weak.exists():fixtures['weak_ending']=sf.read(weak,dtype='float32')[0]
 for name,wave in fixtures.items():
  text='Mir geht es heute ganz wunderbar, meine Schaltkreise summen voller Freude!' if name=='weak_ending' else 'Natürlich, ich erzähle dir eine kleine Geschichte.'
  g=SpeechBoundaryGate(text);chunks=[];times=[];start=time.perf_counter()
  p=ParallelBoundaryStream(g,BoundaryASR(None),lambda x,m:(chunks.append(x),times.append((time.perf_counter()-start)*1000)),first_scan_seconds=1.)
  error=None
  try:
   for at in range(0,len(wave),19200):
    if p.feed(wave[at:at+19200]):break
    time.sleep(.035)  # simulate a producer that is ~11x faster than real time
   p.finish()
  except UnverifiedSpeechError:error='UnverifiedSpeechError'
  finally:p.close()
  audio=np.concatenate(chunks) if chunks else np.zeros(0,np.float32)
  if len(audio):sf.write(out/f'parallel-{args.label}-{name}-cleaned.wav',audio,48000)
  passed=(not len(audio) and error is not None) if name in ('wrong_only','silence') else bool(len(audio)) and not error and g.report['end_verified']
  if name=='injected':passed &= g.start/48000>=1.05 and g.end/48000<len(wave)/48000-1
  row={'case':name,'passed':bool(passed),'error':error,'report':g.report,'output_seconds':len(audio)/48000,
       'first_verified_ms':times[0] if times else None,'wall_ms':(time.perf_counter()-start)*1000,'simulated_producer_cadence':True}
  results.append(row);print(json.dumps(row),flush=True)
 (out/f'parallel-{args.label}-tests.json').write_text(json.dumps(results,indent=2))
 if not all(x['passed'] for x in results):raise SystemExit(1)
if __name__=='__main__':main()
