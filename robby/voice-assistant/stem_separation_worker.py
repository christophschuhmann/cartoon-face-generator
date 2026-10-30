"""Isolated CPU source separation; JSONL, temporary WAVs only, no network."""
import contextlib,json,os,sys,time,traceback
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly

ROOT=Path(__file__).resolve().parent
torch.set_num_threads(int(os.environ.get('ROBO_STEM_CPU_THREADS','4')))
models={}

def load_model(name):
    if name in models:return models[name],0.
    t=time.perf_counter()
    if name=='tuss':
        from nets.model_wrapper import SeparationModel
        from utils.config import yaml_to_parser
        from utils.average_model_params import average_model_params
        root=ROOT/'vendor/tuss/pretrained_models/tuss.medium.2-4src'
        h=yaml_to_parser(root/'hparams.yaml').parse_args([])
        model=SeparationModel(h.encoder_name,h.encoder_conf,h.decoder_name,h.decoder_conf,h.model_name,h.model_conf,h.css_conf,h.variance_normalization)
        with contextlib.redirect_stdout(sys.stderr):sd=average_model_params([root/'checkpoints/model.pth'])
        model.load_state_dict({k.replace('model.',''):v for k,v in sd.items()});model.eval()
    elif name=='bandit':
        from bandit_infer import BanditSession
        model=BanditSession('v2-multi',device='cpu',weights_dir=Path(os.environ.get('BANDIT_INFER_WEIGHTS','/mnt/nvme/moss-15-v2/.cache/bandit'))).load()
    else:raise ValueError('Unknown separator')
    models[name]=model
    return model,round((time.perf_counter()-t)*1000,1)

def run(q):
    name=q['model'];model,load_ms=load_model(name)
    wave,sr=sf.read(q['path'],dtype='float32');wave=wave.mean(axis=1) if wave.ndim>1 else wave
    if sr!=48000:
        from math import gcd
        g=gcd(sr,48000);wave=resample_poly(wave,48000//g,sr//g).astype('float32')
    n=len(wave);started=time.perf_counter()
    with torch.inference_mode():
        if name=='tuss':
            outputs=model(torch.from_numpy(wave.copy()).unsqueeze(0),[['speech','sfxbg','musicbg']])[0].cpu().numpy()
            stems=dict(zip(('speech','effects','music'),outputs))
        else:stems=model.infer(wave,sample_rate=48000)
    separation_ms=round((time.perf_counter()-started)*1000,1)
    paths={};levels={}
    for label in ('speech','music','effects'):
        signal=np.asarray(stems[label],dtype='float32')
        if signal.ndim>1:signal=signal.mean(axis=0)
        signal=signal[:n];signal=np.clip(signal,-1,1)
        p=Path(q['outdir'])/(label+'.wav');sf.write(p,signal,48000,subtype='PCM_16');paths[label]=str(p)
        levels[label]=float(np.sqrt(np.mean(signal*signal))) if signal.size else 0.
    speech_split_ms=None
    if q.get('two_speakers') and name=='tuss' and levels['speech']>0.001:
        speech,_=sf.read(paths['speech'],dtype='float32');started=time.perf_counter()
        with torch.inference_mode():both=model(torch.from_numpy(speech.copy()).unsqueeze(0),[['speech','speech']])[0].cpu().numpy()
        speech_split_ms=round((time.perf_counter()-started)*1000,1)
        for i,signal in enumerate(both):
            label='speaker_'+str(i+1);signal=np.clip(signal[:n],-1,1);p=Path(q['outdir'])/(label+'.wav')
            sf.write(p,signal,48000,subtype='PCM_16');paths[label]=str(p);levels[label]=float(np.sqrt(np.mean(signal*signal))) if len(signal) else 0.
    return {'model':'TUSS Medium' if name=='tuss' else 'Bandit v2 Multi','device':'CPU','load_ms':load_ms,
            'separation_ms':separation_ms,'input_s':round(n/48000,3),'realtime_factor':round(separation_ms/(n/48),3) if n else None,
            'speech_split_ms':speech_split_ms,'paths':paths,'rms':levels}

print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
    try:print(json.dumps({'ok':True,'result':run(json.loads(line))}),flush=True)
    except Exception as exc:
        print(json.dumps({'ok':False,'error':type(exc).__name__+': '+str(exc)[:200]}),flush=True);traceback.print_exc(file=sys.stderr)
