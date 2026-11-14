"""Real BF16 codec: N=3 eager vs CUDA graphs, including winner forks and resets."""
import os,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TTS=ROOT.parent/'humaneness-small'
if not TTS.is_dir():TTS=ROOT/'tts-runtime/humaneness-small'
sys.path.insert(0,str(TTS))
os.environ['HVS_CODEC_GRAPH']='1';os.environ['HVS_CODEC_FUSED']='1';os.environ['HVS_CODEC_RESET_GRAPH']='1'
import torch
from transformers import AutoModel
from performance_core import StreamingCodec
from search_codec_graph import SearchStreamingCodec
from beam_search import reorder_codec

def main():
 torch.set_num_threads(4);torch.cuda.set_device(1)
 assert torch.cuda.mem_get_info(1)[0]>9*2**30,'Insufficient free GPU1 memory'
 torch.cuda.set_per_process_memory_fraction(.27,1)
 codec=AutoModel.from_pretrained('OpenMOSS-Team/MOSS-Audio-Tokenizer-v2',revision='f6e20e543b33d2c252a7ef71bdf8aa71e5ff9169',trust_remote_code=True,codec_weight_dtype='bf16',local_files_only=True).to('cuda:1').eval();codec.set_compute_dtype('bf16')
 expected={};rows=[]
 with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16):
  # Install identical kernels in both arms; test graph replay/fork semantics.
  import codec_fused;codec_fused.install(codec)
  for mode in ['eager','graph']:
   for repeat in range(3):
    torch.manual_seed(800+repeat%2);chunks=[torch.randint(0,1024,(3,n,12),device='cuda:1') for n in (12,12,5,12)]
    chunks[2][2,3:]=-1
    stream=SearchStreamingCodec(codec,3,-1,12) if mode=='graph' else StreamingCodec(codec,3,-1)
    started=time.perf_counter();out=[];timings=[]
    with stream:
     for i,chunk in enumerate(chunks):
      a,b=[torch.cuda.Event(enable_timing=True) for _ in range(2)];a.record();wave,lengths=stream.decode(chunk);b.record();b.synchronize();timings.append(a.elapsed_time(b));out.append((wave.cpu(),lengths.cpu()))
      if i in (0,2):reorder_codec(codec,torch.tensor([1,1,1],device='cuda:1'),3,inplace=mode=='graph')
    if mode=='eager':expected[repeat%2]=out
    same=all(torch.equal(a,x) and torch.equal(b,y) for (a,b),(x,y) in zip(out,expected[repeat%2]))
    error=max(float((a-x).abs().max()) for (a,b),(x,y) in zip(out,expected[repeat%2]))
    row={'mode':mode,'repeat':repeat,'identical':same,'max_abs_error':error,'decode_ms':timings,'wall_ms':(time.perf_counter()-started)*1000};rows.append(row);print(json.dumps(row),flush=True)
 report={'scope':__doc__,'rows':rows,'passed':all(r['identical'] for r in rows)}
 (ROOT/'logs/candidate-search-codec.json').write_text(json.dumps(report,indent=2));assert report['passed']
if __name__=='__main__':main()
