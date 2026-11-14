"""Investigate ordered timestamp merging using authored long-form audio."""
import sys,os,base64,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent/'humaneness-small'));sys.path.insert(0,str(ROOT.parent))
os.environ['SMALL_BOUNDARY_ASR_URL']='http://127.0.0.1:8822'
import torch;torch.set_num_threads(4)
import httpx,numpy as np,soundfile as sf
from parallel_verification_benchmark import PROMPTS
from prompting import parse_literal
from streaming_boundaries import BoundaryASR,SpeechBoundaryGate
from parallel_boundaries import ParallelBoundaryStream
wavepath=ROOT/'logs/streaming-boundaries/long-777-raw.wav'
if not wavepath.exists():
 b={'model':'small_rl','input_mode':'manual','format':'structured','message':PROMPTS['long'],'language':'en','generation':'single','n':1,'batch_size':1,'streaming':True,'stream_transport':'pcm_f32','live_only':True,'chunk_frames':20,'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699','voice_conversion':False,'speaker_steering':False,'dynamic_reference':False,'align':False,'seed':777}
 chunks=[]
 with httpx.Client(timeout=90,trust_env=False) as c:
  with c.stream('POST','http://127.0.0.1:8792/api/turn',json=b) as r:
   for l in r.iter_lines():
    if not l.startswith('data: '):continue
    e=json.loads(l[6:])
    if e.get('pcm_f32'):chunks.append(np.frombuffer(base64.b64decode(e['pcm_f32']),'<f4'))
 sf.write(wavepath,np.concatenate(chunks),48000,subtype='FLOAT')
wave,sr=sf.read(wavepath,dtype='float32')
class Traced(ParallelBoundaryStream):
 def _check(self,final):
  offset,end,_=self._snapshot();super()._check(final)
  print(json.dumps({'offset':offset/48000,'end':end/48000,'prefix':self.gate.report.get('ordered_target_words'),'verified_end':(self.gate.verified_end or 0)/48000,'evidence':self.evidence}),flush=True)
g=SpeechBoundaryGate(parse_literal(PROMPTS['long'],'structured')['text']);out=[]
p=Traced(g,BoundaryASR(None),lambda x,m:out.append(x),first_scan_seconds=1)
for at in range(0,len(wave),76800):
 if p.feed(wave[at:at+76800]):break
 time.sleep(.1)
p.finish();p.close();print('FINAL',g.report)
