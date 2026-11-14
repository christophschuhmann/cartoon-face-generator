"""Real GPU1 prefill numerical/caching check, and warmed whole-TTS comparison."""
import os,sys,json,time,hashlib,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SMALL=ROOT.parent/'humaneness-small';sys.path.insert(0,str(SMALL))
for line in (SMALL/'rtx3090-speed.env').read_text().splitlines():
 if '=' in line and not line.startswith('#'):
  k,v=line.split('=',1);os.environ[k]=v
os.environ['HVS_PREFILL_GRAPH']='1'
import torch,numpy as np,soundfile as sf
import settings
settings.DEVICE=settings.ACTING_DEVICE='cuda:1'
from acting_engine import ActingEngine
from prompting import build,parse_literal
from dynamic_references import fixed_clip
from performance_core import combine_branches
from prefill_graph import PrefillGraphs
from semantic_graph import raw_forward
from parallel_verification_benchmark import PROMPTS

def main():
 torch.set_num_threads(4);torch.cuda.set_device(1)
 assert torch.cuda.mem_get_info(1)[0]>10*2**30
 e=ActingEngine('small_rl');refpath,_=fixed_clip('emolia_c1699')
 report={'device':'RTX3090 GPU1, isolated temporary model','prefill':[],'generation':[]}
 dest=ROOT/'logs/isolation-latency/prefill-graph.json';audio=Path('/tmp/robby-prefill-graph');audio.mkdir(exist_ok=True)
 def save():dest.write_text(json.dumps(report,indent=2))
 specs={}
 for name,prompt in {**PROMPTS,'english':'GENERAL: Natural spontaneous conversation.\nSCRIPT:\n(gentle, natural) Please do not open the door. We can talk about it tomorrow.',
     'long':'GENERAL: Warm and natural, quietly thoughtful.\nSCRIPT:\n(gentle, natural) '+('I can tell you a longer story when you are ready. '*8)}.items():
  specs[name]=build(parse_literal(prompt,'structured'),'structured','en' if name in ('english','long') else 'de',literal=prompt,reference_identity=True)
 with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):
  ref=e.reference(refpath);forward=raw_forward(e.model.transformer);graph=PrefillGraphs(e.model,forward)
  for name in ['current','original','english','long','current']:
   s=specs[name];ids,mask=combine_branches([e.pack_many([s],ref),e.pack_many([s],ref,neutral=True)],e.model.config.pad_token_id,e.model.config.audio_pad_token_id)
   expected=forward(inputs_embeds=e.model._build_inputs_embeds(ids),input_ids=None,attention_mask=mask,past_key_values=None,use_cache=True,return_dict=True)
   result=graph(ids,mask)
   comparisons={'last_hidden_max_abs':float((expected.last_hidden_state[:,-1].float()-result.last_hidden_state[:,-1].float()).abs().max()),
    'last_hidden_cosine':float(torch.nn.functional.cosine_similarity(expected.last_hidden_state[:,-1].float(),result.last_hidden_state[:,-1].float()).min()),
    'valid_kv_max_abs':max(float((a[mask].float()-b[mask].float()).abs().max()) for aa,bb in zip(expected.past_key_values,result.past_key_values) for a,b in zip(aa,bb))}
   for mode in ['eager','graph']:
    for repeat in range(3):
     a,b=[torch.cuda.Event(enable_timing=True) for _ in range(2)];a.record();t=time.perf_counter()
     if mode=='eager':forward(inputs_embeds=e.model._build_inputs_embeds(ids),input_ids=None,attention_mask=mask,past_key_values=None,use_cache=True,return_dict=True)
     else:graph(ids,mask)
     b.record();b.synchronize();report['prefill'].append({'case':name,'mode':mode,'repeat':repeat,'ms':a.elapsed_time(b),'wall_ms':(time.perf_counter()-t)*1000,'width':ids.shape[1],**comparisons})
   print(name,comparisons,flush=True);save()
  del expected,result,graph;gc.collect();torch.cuda.empty_cache()
  runner=e.fast.semantic.prefill_runner
  for mode in ['eager','graph']:
   e.fast.semantic.prefill_runner=runner if mode=='graph' else None
   for bank in e.fast.semantic.banks.values():bank.prefill_runner=e.fast.semantic.prefill_runner
   for name in ['current','original','english']:
    for seed in [777,778,779]:
     t=time.perf_counter();wave=e.generate_many([specs[name]],guidance=2.,seed=seed,temperature=.8,reference_path=refpath,streaming=True,batch_size=1,chunk_frames=20)[0]
     row={'case':name,'mode':mode,'seed':seed,'wall_ms':(time.perf_counter()-t)*1000,'audio_s':len(wave)/48000,'codes_sha256':hashlib.sha256(e.last_codes[0].numpy().tobytes()).hexdigest(),'performance':e.last_performance}
     sf.write(audio/f'{mode}-{name}-{seed}.wav',wave,48000)
     report['generation'].append(row);save();print(name,mode,seed,round(row['wall_ms']),flush=True)
  report['max_reserved_gib']=torch.cuda.max_memory_reserved()/2**30;report['passed_prefill']=all(x['last_hidden_cosine']>.999 for x in report['prefill']);save()
if __name__=='__main__':main()
