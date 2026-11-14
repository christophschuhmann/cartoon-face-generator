"""Pinned official d1 API with bounded question groups and per-window audio reuse."""
import gc,json,os,time,types
from pathlib import Path
import numpy as np

MODEL='LiquidAI/d1-Omni-2B'
REVISION='81222dae8bf8bdd7f903643b5b2a8803bf2e3176'
PROMPT_VERSION='target-interval-v1'
ASSETS=Path(os.getenv('AUDIO_DECISION_ASSETS','/mnt/nvme/robby-audio-decision'))

class Engine:
    def __init__(self):
        self.model=None;self.load_ms=None;self.device=os.getenv('AUDIO_DECISION_DEVICE','cuda:0');self.compiled=False
    def load(self):
        if self.model is not None:return
        import torch
        from transformers import AutoModel
        torch.set_num_threads(4);torch.cuda.set_device(self.device)
        free,_=torch.cuda.mem_get_info(self.device)
        if free<6*1024**3:raise RuntimeError('At least 6 GiB free VRAM is required; other workloads are preserved.')
        start=time.perf_counter();path=(ASSETS/'model-path.txt').read_text().strip()
        self.model=AutoModel.from_pretrained(path,trust_remote_code=True,dtype=torch.bfloat16,local_files_only=True).to(self.device).eval()
        # Initializes official fused projections once, not on every request.
        self.model.engine.token_budget=4096
        torch.cuda.synchronize(self.device);self.load_ms=(time.perf_counter()-start)*1000
    def unload(self):
        if self.model is None:return
        import torch
        self.model=None;gc.collect();torch.cuda.empty_cache();self.compiled=False
    def compile(self):
        self.load()
        if not self.compiled:self.model.compile();self.compiled=True
    def analyze(self,audio,target_samples,classes,settings,event_history=None,*,reuse=True):
        import torch
        self.load();audio=np.asarray(audio,dtype=np.float32)
        if audio.ndim!=1 or not np.isfinite(audio).all() or not 0<len(audio)<=20*16000:raise ValueError('Invalid analysis audio')
        target_samples=min(len(audio),int(target_samples));duration=len(audio)/16000;hop=target_samples/16000
        state={'task':'Judge actual acoustic presence ONLY in the target interval. Earlier sounds are historical context, not current events. Do not infer expected sounds from the scene without audible evidence.',
            'clip_1':{'role':'audio history including target','duration_seconds':round(duration,4),'target_start_seconds':round(duration-hop,4),'target_end_seconds':round(duration,4)},
            'scene_context':settings.get('context','') if settings.get('use_context',True) else '',
            'caution':'Scene descriptions and previous model estimates may be wrong. Prefer acoustic evidence; speech mentioning an object is not the sound of that object.'}
        media=[{'type':'audio','audio':audio,'sampling_rate':16000}]
        if settings.get('repeat_target'):
            media.append({'type':'audio','audio':audio[-target_samples:].copy(),'sampling_rate':16000})
            state['clip_2']={'role':'exact repeat of the target interval from clip 1; not a second independent event','duration_seconds':round(hop,4)}
        if settings.get('feedback') and event_history:state['previous_estimates_uncertain']=event_history
        runner=self.model.engine;body=self.model.model
        original_prefix=runner._prefix;original_audio=body.get_audio_features;prefix_cache={};audio_cache=[]
        stats={'audio_encoder_calls':0,'audio_feature_cache_hits':0,'prefix_cache_hits':0}
        def prefix(this,s,items):
            key=(json.dumps(s,sort_keys=True),tuple((m.type,id(m.value),m.sampling_rate) for m in items))
            if reuse and key in prefix_cache:stats['prefix_cache_hits']+=1;return prefix_cache[key]
            value=original_prefix(s,items)
            if reuse:prefix_cache[key]=value
            return value
        def features(this,x,mask):
            if reuse:
                for old_x,old_mask,value in audio_cache:
                    if x.shape==old_x.shape and torch.equal(mask,old_mask) and torch.equal(x,old_x):
                        stats['audio_feature_cache_hits']+=1;return value
            stats['audio_encoder_calls']+=1;value=original_audio(x,mask)
            if reuse:audio_cache.append((x.clone(),mask.clone(),value))
            return value
        runner._prefix=types.MethodType(prefix,runner);body.get_audio_features=types.MethodType(features,body)
        start=time.perf_counter();scores={c['id']:None for c in classes};failures=[];groups=[]
        group_size=int(settings.get('group_size',16));method=settings.get('method','binary');tokens=0
        try:
            with torch.inference_mode():
                for offset in range(0,len(classes),group_size):
                    group=classes[offset:offset+group_size]
                    if method=='binary':
                        questions={c['id']:{'type':'noul','instructions':f'Is the sound event "{c["name"]}" acoustically present specifically in the target interval (the final {hop*1000:.0f} milliseconds of clip 1)? Ignore events only in earlier history and mere contextual plausibility.'} for c in group}
                    else:
                        questions={'events':{'type':'choice','multiple':True,'instructions':f'Which sound events are acoustically present ONLY in the final {hop*1000:.0f} milliseconds of clip 1? Each may independently be absent or present; earlier history and expected sounds do not count.',
                            'criteria':{c['id']:c['name'] for c in group}}}
                    tick=time.perf_counter()
                    try:
                        out=self.model.system_one(state,questions,media=media,set_size=group_size)
                        torch.cuda.synchronize(self.device);tokens+=out['usage']['input_tokens']
                        values=out['answers'] if method=='binary' else out['answers']['events']['probabilities']
                        for c in group:
                            value=values[c['id']]['noul'] if method=='binary' else values[c['id']]
                            value=float(value)
                            if not np.isfinite(value) or not 0<=value<=1:raise ValueError('Invalid model score')
                            scores[c['id']]=value
                    except Exception as exc:
                        failures.append({'ids':[c['id'] for c in group],'error':type(exc).__name__})
                        # Never turn an unevaluated question into a zero score.
                        for c in group:scores[c['id']]=None
                        if isinstance(exc,torch.cuda.OutOfMemoryError):torch.cuda.empty_cache()
                    groups.append({'ids':[c['id'] for c in group],'ms':(time.perf_counter()-tick)*1000})
        finally:
            runner._prefix=original_prefix;body.get_audio_features=original_audio;prefix_cache.clear();audio_cache.clear()
        return {'scores':scores,'failures':failures,'inference_ms':(time.perf_counter()-start)*1000,'groups':groups,'input_tokens':tokens,'reuse':stats,
            'allocated_mb':torch.cuda.memory_allocated(self.device)/1024**2,'reserved_mb':torch.cuda.memory_reserved(self.device)/1024**2}
