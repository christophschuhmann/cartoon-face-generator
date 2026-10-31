"""Isolated video-SALMONN 2 Pro 4B audio+video captioning worker."""
import argparse,contextlib,json,os,re,sys,time,traceback
import torch
from transformers import AutoTokenizer,BitsAndBytesConfig

PROJECT='/mnt/raid/robby-models/video-SALMONN-2/video_SALMONN2_pro'
sys.path.insert(0,PROJECT+'/scripts')
from inference import Qwen3VLProcessor,Qwen3VLForConditionalGeneration,build_dataset,prepare_inputs

path=os.environ.get('SALMON_MODEL_PATH','/mnt/raid/robby-models/hf-cache/hub/models--tsinghua-ee--video-SALMONN-2-Pro-4B/snapshots/97c1d4e6e774732cf357a17d73d62002dcc1ceea')
device=torch.device('cuda:0');start=time.perf_counter()
args=argparse.Namespace(video_min_frames=4,video_max_frames=12,base_interval=.2,min_pixels=3136,max_pixels=50176,video_min_frame_pixels=3136,video_max_frame_pixels=50176,feature_size=128,sampling_rate=16000,hop_length=160,chunk_length=30)
with contextlib.redirect_stdout(sys.stderr):
    processor=Qwen3VLProcessor.from_pretrained(path)
    tokenizer=AutoTokenizer.from_pretrained(path,model_max_length=8192,padding_side='right',use_fast=False)
    dataset=build_dataset(args,tokenizer,processor)
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_quant_type='nf4')
    model=Qwen3VLForConditionalGeneration.from_pretrained(path,attn_implementation='sdpa',torch_dtype=torch.bfloat16,device_map={'':'cuda:0'},quantization_config=quant).eval()
    torch.cuda.synchronize()
print(json.dumps({'ready':True,'model':'video-SALMONN 2 Pro 4B NF4','load_ms':round((time.perf_counter()-start)*1000,1)}),flush=True)

def run(q):
    previous=json.dumps(q.get('previous',[])[-2:],ensure_ascii=False)[:2000]
    context=json.dumps(q.get('context',{}),ensure_ascii=False)[:1000]
    prompt=('Analyze this video and its original audio together. Describe observable foreground and background, '
      'speech and intelligible words, music only if audible, other sounds, objects, visible people, facial expressions, '
      'gestures, gaze, movements and changes. Use concise factual descriptions. Do not guess hidden emotions, identity, '
      'song titles, inaudible words or events. Return one JSON object with foreground, background, observations '
      '(array of {category, description, relevance: 0, 1 or 2}), people (array of {id, description}), and '
      'events (array of {start_s, end_s, person_id, kind, description, relevance}). '
      'Times are approximate seconds relative to this window; use null when unsure. Keep person labels consistent only '
      'if visual evidence supports it. Context is for relevance, not evidence: '+context+' Earlier windows may be wrong: '+previous)
    t=time.perf_counter()
    with contextlib.redirect_stdout(sys.stderr):inputs=prepare_inputs(dataset,q['path'],prompt,True,device)
    torch.cuda.synchronize();prep=time.perf_counter()-t;t=time.perf_counter()
    with contextlib.redirect_stdout(sys.stderr),torch.inference_mode():output=model.generate(**inputs,max_new_tokens=320,do_sample=False)
    torch.cuda.synchronize();elapsed=time.perf_counter()-t;seq=output[0,inputs['input_ids'].shape[1]:]
    raw=tokenizer.decode(seq,skip_special_tokens=True).strip();clean=re.sub(r'^```(?:json)?\s*|\s*```$','',raw).strip()
    try:parsed=json.loads(clean);assert isinstance(parsed,dict);wrapped=False
    except (ValueError,AssertionError):
        parsed={'observations':[{'category':'audio_visual','description':raw,'relevance':None}],
                'format_warning':'Model returned prose; this is one unstructured observation.'} if raw else None
        wrapped=parsed is not None
    return {'annotation':parsed,'parse_ok':parsed is not None,'parse_repaired':wrapped,'raw_text':raw if parsed is None or wrapped else None,
      'preprocess_ms':round(prep*1000,1),'generation_ms':round(elapsed*1000,1),'total_ms':round((prep+elapsed)*1000,1),
      'output_tokens':len(seq),'output_tokens_per_s':round(len(seq)/elapsed,2) if elapsed else 0.,'model_calls':1,
      'model':'video-SALMONN 2 Pro 4B NF4','video_max_frames':12}

for line in sys.stdin:
    try:print(json.dumps({'ok':True,'result':run(json.loads(line))},ensure_ascii=False),flush=True)
    except Exception as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc)[:200]}),flush=True);traceback.print_exc(file=sys.stderr)
