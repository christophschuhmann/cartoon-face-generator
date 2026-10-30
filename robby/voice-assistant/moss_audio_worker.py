"""Single local MOSS audio worker. JSONL protocol; recordings are not retained."""
import json, os, sys, time, traceback
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from transformers import BitsAndBytesConfig
from src.modeling_moss_audio import MossAudioModel
from src.processing_moss_audio import MossAudioProcessor

path=os.environ['MOSS_AUDIO_MODEL_PATH']
gpu=int(sys.argv[1]);device=f'cuda:{gpu}'
torch.cuda.set_device(gpu)
start=time.perf_counter()
quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.bfloat16)
model=MossAudioModel.from_pretrained(path,trust_remote_code=True,torch_dtype=torch.bfloat16,
                                     device_map={'':device},quantization_config=quant).eval()
processor=MossAudioProcessor.from_pretrained(path,trust_remote_code=True,enable_time_marker=True)
torch.cuda.synchronize();print(json.dumps({'ready':True,'mode':'audio','model':'MOSS-Audio-4B-Instruct','quantization':'NF4','load_s':round(time.perf_counter()-start,2)}),flush=True)

def run(x):
    start=time.perf_counter();samples,sr=sf.read(x['path'],dtype='float32')
    if samples.ndim>1:samples=samples.mean(axis=1)
    if sr!=processor.config.mel_sr:
        from scipy.signal import resample_poly
        from math import gcd
        g=gcd(sr,processor.config.mel_sr);samples=resample_poly(samples,processor.config.mel_sr//g,sr//g).astype('float32')
    rms=float(np.sqrt(np.mean(samples*samples))) if samples.size else 0
    prompt=('Describe the audio accurately. Distinguish foreground speech and background sounds. '
            'Transcribe intelligible words. Describe music, instruments, rhythm, tempo and mood only if audible. '
            'Describe changes and vocal delivery when supported. Use concise factual sentences. '
            'Do not invent sounds, recording location, relationships, intentions or emotional certainty.')
    context=json.dumps(x.get('context',{}),ensure_ascii=False)[:1000]
    previous=json.dumps(x.get('previous',[])[-2:],ensure_ascii=False)[:1000]
    prompt+=' Context for relevance only, not evidence: '+context+' Previous descriptions may be wrong: '+previous
    inputs=processor(text=prompt,audios=[samples],return_tensors='pt').to(device)
    if inputs.get('audio_data') is not None:inputs['audio_data']=inputs['audio_data'].to(torch.bfloat16)
    inputs['audio_input_mask']=inputs['input_ids']==processor.audio_token_id
    torch.cuda.synchronize();prep=time.perf_counter()-start;started=time.perf_counter()
    with torch.inference_mode():
        output=model.generate(**inputs,max_new_tokens=256,do_sample=False,num_beams=1,use_cache=True)
    torch.cuda.synchronize();elapsed=time.perf_counter()-started
    seq=output[0,inputs['input_ids'].shape[1]:];raw=processor.decode(seq,skip_special_tokens=True).strip()
    quiet=rms<0.0003
    if quiet:annotation={'observations':[],'level_note':'Very quiet input; interpretation is uncertain.'}
    elif raw:annotation={'observations':[{'category':'audio','description':raw,'relevance':None}]}
    else:annotation={'observations':[{'category':'signal','description':'Audio exceeds the silence threshold; the model provided no description.','relevance':None}]}
    return {'annotation':annotation,'parse_ok':True,'parse_repaired':False,'raw_text':raw if quiet else None,'silence_gate':quiet,
        'preprocess_ms':round(prep*1000,1),'generation_ms':round(elapsed*1000,1),'total_ms':round((prep+elapsed)*1000,1),
        'output_tokens':len(seq),'output_tokens_per_s':round(len(seq)/elapsed,2) if elapsed else 0,'model_calls':1,'model':'MOSS-Audio-4B-Instruct NF4'}

for line in sys.stdin:
    try:print(json.dumps({'ok':True,'result':run(json.loads(line))},ensure_ascii=False),flush=True)
    except Exception as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc)[:250]}),flush=True);traceback.print_exc(file=sys.stderr)
