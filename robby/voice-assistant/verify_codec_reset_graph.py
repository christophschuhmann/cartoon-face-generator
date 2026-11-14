"""Real codec reset equivalence with deterministic synthetic token arrays."""
import os,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent/'humaneness-small'))
os.environ['HVS_CODEC_GRAPH']='1';os.environ['HVS_CODEC_FUSED']='1'
import torch
from transformers import AutoModel
from performance_core import StreamingCodec

def main():
 torch.set_num_threads(4);torch.cuda.set_device(1)
 assert torch.cuda.mem_get_info(1)[0]>8*2**30,'Insufficient free GPU1 memory'
 # A podcast job can be active here. Bound this temporary test's allocator.
 torch.cuda.set_per_process_memory_fraction(.23,1)
 codec=AutoModel.from_pretrained('OpenMOSS-Team/MOSS-Audio-Tokenizer-v2',revision='f6e20e543b33d2c252a7ef71bdf8aa71e5ff9169',trust_remote_code=True,codec_weight_dtype='bf16',local_files_only=True).to('cuda:1').eval()
 codec.set_compute_dtype('bf16')
 rows=[];outputs={}
 with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):
  for mode in ['eager','graph']:
   os.environ['HVS_CODEC_RESET_GRAPH']='1' if mode=='graph' else '0'
   for repeat in range(4):
    stream=StreamingCodec(codec,1,-1)
    a,b=[torch.cuda.Event(enable_timing=True) for _ in range(2)];a.record()
    with stream:
     b.record();b.synchronize();reset_ms=a.elapsed_time(b)
     torch.manual_seed(777+repeat%2)
     chunks=[stream.decode(torch.randint(0,1024,(1,n,12),device='cuda:1'))[0].cpu() for n in [3,6,12,20]]
    out=torch.cat(chunks,-1);key=repeat%2
    if mode=='eager':outputs[key]=out
    same=torch.equal(outputs[key],out)
    row={'mode':mode,'repeat':repeat,'reset_ms':reset_ms,'identical':same};rows.append(row);print(json.dumps(row),flush=True)
 report={'scope':__doc__,'rows':rows,'passed':all(r['identical'] for r in rows)}
 (ROOT/'logs/isolation-latency/codec-reset-graph.json').write_text(json.dumps(report,indent=2));assert report['passed']
if __name__=='__main__':main()
