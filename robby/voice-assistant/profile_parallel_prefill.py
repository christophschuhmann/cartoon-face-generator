"""Isolated prefill profiling on GPU1; no service changes or model generation."""
import os,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent/'humaneness-small'))
os.environ['HVS_RL_PRECISION']='bf16_merged';os.environ['HVS_SEMANTIC_CUDA_GRAPH']='1'
import torch
import settings
settings.DEVICE=settings.ACTING_DEVICE='cuda:1'
from acting_engine import ActingEngine
from prompting import build,parse_literal
from dynamic_references import fixed_clip
from performance_core import combine_branches
from semantic_graph import SemanticBank
from parallel_verification_benchmark import PROMPTS

torch.set_num_threads(4);torch.cuda.set_device(1)
assert torch.cuda.mem_get_info(1)[0]>10*2**30,'Insufficient free GPU1 memory'
e=ActingEngine('small_rl');literal=PROMPTS['current'];s=build(parse_literal(literal,'structured'),'structured','de',literal=literal,reference_identity=True)
p,_=fixed_clip('emolia_c1699')
with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):
 ref=e.reference(p);ids,mask=combine_branches([e.pack_many([s],ref),e.pack_many([s],ref,neutral=True)],e.model.config.pad_token_id,e.model.config.audio_pad_token_id)
 bank=SemanticBank(e.model,2,1024,compile_decode=False)
 rows=[]
 for i in range(5):
  a,b=[torch.cuda.Event(enable_timing=True) for _ in range(2)];a.record();t=time.perf_counter();out=bank.prefill(ids,mask);b.record();b.synchronize()
  row={'repeat':i,'ms':a.elapsed_time(b),'wall_ms':(time.perf_counter()-t)*1000,'shape':list(ids.shape)};rows.append(row);print(json.dumps(row),flush=True)
 with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=True) as prof:
  bank.prefill(ids,mask);torch.cuda.synchronize()
 report={'rows':rows,'cpu':prof.key_averages().table(sort_by='self_cpu_time_total',row_limit=25),'cuda':prof.key_averages().table(sort_by='self_cuda_time_total',row_limit=25)}
 (ROOT/'logs/isolation-latency/prefill-profile.json').write_text(json.dumps(report,indent=2));print(report['cpu'],report['cuda'],flush=True)
