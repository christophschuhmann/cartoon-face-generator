"""Isolated CPU worker: MP3/WAV -> Redux word timings -> LAION Ears segments.

Run with .venv-audio, leaving MediaPipe's NumPy/dependencies untouched.
The local, reviewed LAION implementation is loaded from the pinned model folder.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('HF_HOME',str(ROOT/'webcam_mapper/models/hf-cache'))
os.environ.setdefault('OMP_WAIT_POLICY','passive')
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('TOKENIZERS_PARALLELISM','false')

def progress(stage, fraction, **extra):
    print(json.dumps({'stage':stage,'progress':fraction,**extra}),flush=True)

class LocalWhisperFeatures:
    """Exact CPU Whisper feature path, using the upstream-exported mel filters."""
    def __init__(self,folder):
        import numpy as np
        self.filters=np.load(folder/'mel_filters.npy',allow_pickle=False)
        self.config=json.loads((folder/'feature_config.json').read_text())
        if self.config['dither']!=0:raise ValueError('Expected deterministic Whisper preprocessing')
    def __call__(self,waves,**kwargs):
        import numpy as np
        import torch
        if len(waves)!=1:raise ValueError('One audio segment at a time')
        wave=torch.from_numpy(np.asarray(waves[0],np.float32)[:480000])[None]
        n_fft=self.config['n_fft'];hop=self.config['hop_length']
        stft=torch.stft(wave,n_fft,hop,window=torch.hann_window(n_fft),return_complex=True)
        power=(stft[...,:-1].abs()**2).contiguous()
        mel=torch.from_numpy(self.filters).float().T@power
        log=mel.clamp_min(1e-10).log10();log=torch.maximum(log,log.amax()-8.)
        return {'input_features':((log+4.)/4.).numpy(),'attention_mask':np.ones((1,log.shape[-1]),np.int64)}

def load_ears(reference=False,variant='base'):
    if variant not in ('base','medium'):raise ValueError('Unknown Ears variant')
    import torch
    torch.set_num_threads(2)
    folder=ROOT/'webcam_mapper/models/ears'
    runtime=folder if variant=='base' else folder/'medium'
    norm=json.loads((folder/'training_normalization.json').read_text())
    display=json.loads((folder/'display_normalization.json').read_text())
    display['variant']=variant
    if not reference and (runtime/'scores_cpu.pt').is_file():
        return torch.jit.load(str(runtime/'scores_cpu.pt'),map_location='cpu').eval(),LocalWhisperFeatures(runtime),norm,display
    from safetensors.torch import load_file
    from transformers import WhisperFeatureExtractor
    spec=importlib.util.spec_from_file_location('local_ears_model',folder/'model.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    classes=json.loads((folder/'classes.json').read_text())['names']
    model=module.LayeredMultiTaskWhisper(folder/variant,len(classes),initialize_pretrained=False)
    model.load_state_dict(load_file(folder/variant/'model.safetensors',device='cpu'),strict=True)
    model.eval()
    extractor=WhisperFeatureExtractor.from_pretrained(folder/variant,local_files_only=True)
    return model,extractor,norm,display

def transcribe_redux(wav,duration):
    folder=ROOT/'webcam_mapper/models/parakeet-redux'
    binary=folder/'cpp/parakeet-v0.6.1-bin-win-cpu-x64/parakeet-cli.exe'
    command=[str(binary),'transcribe','--model',str(folder/'redux-q8.gguf'),'--input',str(wav),
             '--threads','2','--json','--vad','--vad-model',str(folder/'redux-bundle.gguf'),'--vad-component','vad']
    try:
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf8',errors='replace',
            timeout=max(240,duration*12),env=dict(os.environ,PARAKEET_DEVICE='cpu'),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Die Spracherkennung hat das CPU-Zeitlimit erreicht. Bitte zunächst einen kürzeren Audioausschnitt versuchen.') from error
    if result.returncode:raise RuntimeError('Redux CPU: '+result.stderr[-1400:])
    data=json.loads(result.stdout)
    return {'segments':[{'words':[{'word':w['w'],'start':w['start'],'end':w['end']} for w in data['words']]}]}

def ears_scores(wave, bundle):
    import numpy as np
    import torch
    model,extractor,norm,display=bundle
    features=extractor([wave],sampling_rate=16000,padding='longest',truncation=True,max_length=480000,
                       return_attention_mask=True,return_tensors='np')
    mel=features['input_features'].astype(np.float32);mask=features['attention_mask'].astype(np.int64)
    if mel.shape[-1]%2:
        mel=np.pad(mel,((0,0),(0,0),(0,1)));mask=np.pad(mask,((0,0),(0,1)))
    with torch.inference_mode():
        out=model(torch.from_numpy(mel),torch.from_numpy(mask))
    standardized=(out['scores'] if isinstance(out,dict) else out)[0].float().numpy()
    raw=standardized*np.asarray(norm['score_std'])+np.asarray(norm['score_mean'])
    if not np.isfinite(raw).all():raise ValueError('Nonfinite LAION scores')
    scores=dict(zip(norm['score_names'],map(float,raw)))
    from .audio_scores import normalize_scores
    return normalize_scores(scores,display,display.get('variant','base'))

def analyze(source, output, maximum_seconds=600,variant='base'):
    import numpy as np
    import soundfile as sf
    from .audio_timeline import group_words,loudness_envelope,audible_words
    started=time.monotonic();progress('decode',.02)
    wav=output.parent/'decoded.wav'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(source),'-t',str(maximum_seconds+1),
                    '-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],check=True,capture_output=True,timeout=120)
    wave,rate=sf.read(wav,dtype='float32');duration=len(wave)/rate
    if not .1<=duration<=maximum_seconds:raise ValueError('Audio muss 0,1 Sekunden bis 10 Minuten lang sein.')
    envelope=loudness_envelope(wave,rate)
    progress('asr',.08,duration=duration)
    # Dequantized Q8 Redux avoids the slow packed-ternary scalar Windows kernel.
    asr_started=time.monotonic()
    transcript=transcribe_redux(wav,duration)
    asr_seconds=time.monotonic()-asr_started
    words,_=group_words(transcript,duration)
    words=audible_words(words,envelope)
    _,segments=group_words({'segments':[{'words':words}]},duration)
    progress('emotions',.40,segments=len(segments),words=len(words))
    ears_started=time.monotonic();bundle=load_ears(variant=variant) if segments else None
    ears_load_seconds=time.monotonic()-ears_started;ears_started=time.monotonic()
    for index,segment in enumerate(segments):
        # Context is reported separately; it does not shift any word timings.
        a=max(0.,segment['start']-.20);b=min(duration,segment['end']+.20)
        if b-a<1.4:
            center=(a+b)/2;a=max(0.,center-.7);b=min(duration,a+1.4);a=max(0.,b-1.4)
        crop=wave[round(a*rate):round(b*rate)]
        segment.update(ears_scores(crop,bundle),context_start=a,context_end=b)
        progress('emotions',.40+.55*(index+1)/max(1,len(segments)),segment=index+1,segments=len(segments))
    result={'version':1,'duration':duration,'words':words,'segments':segments,'envelope':envelope,
            'transcript':' '.join(w['word'].strip() for w in words),
            'models':{'asr':'moondream/parakeet-redux','emotion':'laion/humaneness-ears-base-medium/'+variant},
            'runtime':{'asr':'parakeet.cpp 0.6.1 CPU; Redux Q8 GGUF','vad':'Silero from Redux bundle','emotion':'Ears '+variant+' CPU TorchScript'},
            'stage_seconds':{'asr':asr_seconds,'ears_load':ears_load_seconds,'ears_inference':time.monotonic()-ears_started},
            'analysis_seconds':time.monotonic()-started,'score_kind':'40 simultaneous regression intensities; not probabilities'}
    output.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf8')
    progress('complete',1.,analysis_seconds=result['analysis_seconds'])

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--variant',choices=('base','medium'),default='base');a=p.parse_args()
    try:analyze(a.source,a.output,variant=a.variant)
    except Exception as error:
        progress('error',0,error=str(error));raise

if __name__=='__main__':main()
