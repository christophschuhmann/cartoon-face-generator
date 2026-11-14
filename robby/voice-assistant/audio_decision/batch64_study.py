"""Real 64-class-group batching experiment; production engine stays unchanged.

Run with AUDIO_DECISION_DEVICE=cuda:1 and the existing isolated PYTHONPATH.
No audio recording, model output or HTTP response is mocked. Authored stimuli only.
"""
import gc,json,os,time,types,hashlib,subprocess,statistics
from pathlib import Path
import numpy as np
from .engine import Engine,MODEL,REVISION
from .core import TAXONOMY

ROOT=Path(__file__).parent
OUT=ROOT/'batch64-result.json'
CONTEXT='Evaluate the audible evidence; do not assume events from the scene.'

def prepare(wave,target_samples,repeat=False):
    hop=target_samples/16000;duration=len(wave)/16000
    # Keep wording identical to the deployed engine, including each group.
    state={'task':'Judge actual acoustic presence ONLY in the target interval. Earlier sounds are historical context, not current events. Do not infer expected sounds from the scene without audible evidence.',
        'clip_1':{'role':'audio history including target','duration_seconds':round(duration,4),'target_start_seconds':round(duration-hop,4),'target_end_seconds':round(duration,4)},
        'scene_context':CONTEXT,
        'caution':'Scene descriptions and previous model estimates may be wrong. Prefer acoustic evidence; speech mentioning an object is not the sound of that object.'}
    media=[{'type':'audio','audio':wave,'sampling_rate':16000}]
    if repeat:
        media.append({'type':'audio','audio':wave[-target_samples:].copy(),'sampling_rate':16000})
        state['clip_2']={'role':'exact repeat of the target interval from clip 1; not a second independent event','duration_seconds':round(hop,4)}
    return state,media,hop

def analyze(engine,wave,classes,groups_per_batch,*,repeat=False,reuse_audio=True):
    import torch
    state,media,hop=prepare(wave,3200,repeat)
    model=engine.model;runner=model.engine;body=model.model
    prefix_original=runner._prefix;features_original=body.get_audio_features;slots_original=runner._slot_logits
    old_budget=runner.token_budget;runner.token_budget=65536
    prefix_cache={};feature_cache=[];forward_shapes=[]
    stats={'audio_encoder_calls':0,'encoded_clips':0,'reused_clip_rows':0,'prefix_cache_hits':0}
    def prefix(this,s,items):
        key=(json.dumps(s,sort_keys=True),tuple((m.type,id(m.value),m.sampling_rate) for m in items))
        if key in prefix_cache:stats['prefix_cache_hits']+=1;return prefix_cache[key]
        value=prefix_original(s,items);prefix_cache[key]=value;return value
    def features(this,x,mask):
        if not reuse_audio:
            stats['audio_encoder_calls']+=1;stats['encoded_clips']+=x.shape[0]
            return features_original(x,mask)
        k=len(media)
        # Only deduplicate after checking the exact complete mel/mask pattern.
        # Audio features are flattened clip-by-clip by the official model.
        assert x.shape[0]%k==0,('Unexpected audio layout',tuple(x.shape),k)
        copies=x.shape[0]//k;first=x[:k];first_mask=mask[:k]
        assert torch.equal(x,first.repeat(copies,1,1)), 'Distinct audio unexpectedly batched'
        assert torch.equal(mask,first_mask.repeat(copies,1)), 'Distinct masks unexpectedly batched'
        value=None
        for old_x,old_mask,cached in feature_cache:
            if first.shape==old_x.shape and torch.equal(first_mask,old_mask) and torch.equal(first,old_x):value=cached;break
        if value is None:
            stats['audio_encoder_calls']+=1;stats['encoded_clips']+=k
            value=features_original(first,first_mask);feature_cache.append((first.clone(),first_mask.clone(),value))
            stats['reused_clip_rows']+=x.shape[0]-k
        else:stats['reused_clip_rows']+=x.shape[0]
        return value.repeat(copies,1) if copies>1 else value
    def slots(this,seqs,batch,reads,pointer):
        lengths=[len(seqs[b][2]) for b in batch]
        forward_shapes.append({'rows':len(batch),'lengths':lengths,'padded_tokens':len(batch)*max(lengths)})
        return slots_original(seqs,batch,reads,pointer)
    runner._prefix=types.MethodType(prefix,runner);body.get_audio_features=types.MethodType(features,body);runner._slot_logits=types.MethodType(slots,runner)
    torch.cuda.synchronize(engine.device);torch.cuda.reset_peak_memory_stats(engine.device)
    start=time.perf_counter();scores={};tokens=0;calls=0
    try:
        with torch.inference_mode():
            groups=[classes[i:i+64] for i in range(0,len(classes),64)]
            for first in range(0,len(groups),groups_per_batch):
                selected=groups[first:first+groups_per_batch];requests=[]
                for group in selected:
                    question={'events':{'type':'choice','multiple':True,
                        'instructions':f'Which sound events are acoustically present ONLY in the final {hop*1000:.0f} milliseconds of clip 1? Each may independently be absent or present; earlier history and expected sounds do not count.',
                        'criteria':{c['id']:c['name'] for c in group}}}
                    requests.append((state,question,media))
                outputs=model.system_one_batch(requests,set_size=64);calls+=1
                assert len(outputs)==len(selected)
                for group,out in zip(selected,outputs):
                    tokens+=out['usage']['input_tokens'];values=out['answers']['events']['probabilities']
                    assert set(values)=={c['id'] for c in group}
                    for c in group:
                        p=float(values[c['id']]);assert np.isfinite(p) and 0<=p<=1;scores[c['id']]=p
        torch.cuda.synchronize(engine.device)
        return {'inference_ms':(time.perf_counter()-start)*1000,'scores':scores,'api_calls':calls,
            'forward_shapes':forward_shapes,'input_tokens':tokens,'reuse':stats,
            'peak_allocated_mb':torch.cuda.max_memory_allocated(engine.device)/1024**2,
            'peak_reserved_mb':torch.cuda.max_memory_reserved(engine.device)/1024**2,
            'allocated_mb':torch.cuda.memory_allocated(engine.device)/1024**2}
    finally:
        runner._prefix=prefix_original;body.get_audio_features=features_original;runner._slot_logits=slots_original;runner.token_budget=old_budget
        prefix_cache.clear();feature_cache.clear()

def differences(result,reference):
    a=np.array([result[k] for k in reference]);b=np.array(list(reference.values()));delta=np.abs(a-b)
    topa=np.argsort(-a)[:10];topb=np.argsort(-b)[:10]
    return {'max_abs':float(delta.max()),'mean_abs':float(delta.mean()),'p95_abs':float(np.quantile(delta,.95)),
        'flips_at_0_5':int(np.sum((a>=.5)!=(b>=.5))),'top10_overlap':len(set(topa)&set(topb))}

def main():
    if os.getenv('AUDIO_DECISION_DEVICE')!='cuda:1':raise SystemExit('Set AUDIO_DECISION_DEVICE=cuda:1; this host study preserves production GPU 0.')
    import torch
    from optional_lab_gpu import Lease
    os.environ['ROBO_OPTIONAL_GPU_LOCK']=str(Path.home()/'.cache/robby-d1-batch64-gpu1.lock')
    report={'model':MODEL,'revision':REVISION,'device':os.environ.get('AUDIO_DECISION_DEVICE'),
        'group_size':64,'classes':527,'history_s':10,'target_ms':200,'precision':'BF16',
        'scene_context':CONTEXT,'token_budget':65536,'memory_limit_fraction':.30,'rows':[],
        'software':{'torch':torch.__version__},
        'hardware':subprocess.check_output(['nvidia-smi','--query-gpu=index,name,memory.used,memory.free,utilization.gpu','--format=csv'],text=True),
        'method':'Official system_one_batch with unchanged per-request 64-class multi-label prompts. Exact audio-feature deduplication across repeated rows; single-clip/target-repeat order preserved.'}
    def save():OUT.write_text(json.dumps(report,indent=2,allow_nan=False))
    def run(label,stimulus,wave,batch,repeat=False,reuse=True,reference=None):
        free,_=torch.cuda.mem_get_info(engine.device)
        if free<1024**3:raise RuntimeError('Less than 1 GiB free VRAM; stopping to protect other services')
        row={'label':label,'stimulus':stimulus,'groups_per_batch':batch,'repeat_target':repeat,'reuse_audio':reuse}
        try:
            row.update(analyze(engine,wave,classes,batch,repeat=repeat,reuse_audio=reuse))
            if reference is not None:row['score_difference']=differences(row['scores'],reference)
        except Exception as exc:
            row['error']=type(exc).__name__+': '+str(exc)[:700]
            if isinstance(exc,torch.cuda.OutOfMemoryError):gc.collect();torch.cuda.empty_cache()
        report['rows'].append(row);save()
        print(label,stimulus,'batch',batch,'ms',round(row.get('inference_ms',0),1),'peak',round(row.get('peak_allocated_mb',0)),
            'forwards',[s['rows'] for s in row.get('forward_shapes',[])],row.get('score_difference',{}),row.get('error',''),flush=True)
        return row
    classes=TAXONOMY['classic'];rng=np.random.default_rng(4271);t=np.arange(160000)/16000
    tone=np.zeros(160000,np.float32);tone[-3200:]=.2*np.sin(2*np.pi*880*np.arange(3200)/16000)
    mix=(.035*rng.standard_normal(160000)+.08*np.sin(2*np.pi*(180*t+65*t*t))+.04*np.sin(2*np.pi*440*t)).astype(np.float32)
    silence=np.zeros_like(tone);stimuli={'late_beep':tone,'chirp_noise':mix,'silence':silence}
    report['stimuli_sha256']={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in stimuli.items()}
    with Lease():
        engine=Engine();torch.cuda.set_device(engine.device);torch.cuda.set_per_process_memory_fraction(.30,engine.device)
        engine.load();report['load_ms']=engine.load_ms;save()
        settings={'context':CONTEXT,'use_context':True,'method':'multilabel','group_size':64,'repeat_target':False}
        reference=engine.analyze(tone,3200,classes,settings)
        assert not reference['failures'];report['deployment_reference']=reference;save()
        viable=[]
        for batch in [1,2,4,8]:
            row=run('warmup','late_beep',tone,batch,reference=reference['scores'])
            if 'error' not in row:viable.append(batch)
        baseline=next(r['scores'] for r in report['rows'] if r['label']=='warmup' and r['groups_per_batch']==1)
        report['implementation_vs_deployment']=differences(baseline,reference['scores']);save()
        for name,wave in stimuli.items():
            base=run('reference',name,wave,1)['scores']
            # Rotate order to reduce GPU-clock/order bias between warm repetitions.
            for iteration in range(3):
                order=viable[iteration:]+viable[:iteration]
                for batch in order:
                    row=run('timing',name,wave,batch,reference=base);row['repetition']=iteration;save()
        best=min(viable,key=lambda b:statistics.median(r['inference_ms'] for r in report['rows'] if r['label']=='timing' and r['groups_per_batch']==b and 'error' not in r))
        report['fastest_groups_per_batch']=best
        # Check whether feature deduplication preserves a truly native batched pass.
        native=run('native_comparison','late_beep',tone,best,reuse=False)
        if 'scores' in native:run('dedup_comparison','late_beep',tone,best,reference=native['scores'])
        repeated=run('repeat_reference','late_beep',tone,1,repeat=True)
        if 'scores' in repeated:run('repeat_comparison','late_beep',tone,best,repeat=True,reference=repeated['scores'])
        engine.unload();report['completed']=True;save()

if __name__=='__main__':main()
