"""Freeze the reviewed LAION score graph once, then check multiple clip lengths.

TorchScript avoids importing the large Transformers package for every audio job.
Weights, 192 score outputs, and Whisper log-mel preprocessing stay unchanged.
"""
import faulthandler
import argparse
import json
import time
from pathlib import Path
import numpy as np
import torch
from .audio_inference import load_ears,ROOT

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=('base','medium'),default='base');args=parser.parse_args()
    faulthandler.enable()
    torch.set_num_threads(2)
    print('Loading reference implementation for '+args.variant+' (one-time export)',flush=True)
    started=time.monotonic();model,extractor,norm,display=load_ears(reference=True,variant=args.variant)
    print('Reference loaded',round(time.monotonic()-started,2),flush=True)
    folder=ROOT/'webcam_mapper/models/ears'
    if args.variant=='medium':folder=folder/'medium'
    np.save(folder/'mel_filters.npy',extractor.mel_filters,allow_pickle=False)
    (folder/'feature_config.json').write_text(json.dumps({'n_fft':extractor.n_fft,'hop_length':extractor.hop_length,'dither':extractor.dither}))
    class Scores(torch.nn.Module):
        def __init__(self,model):super().__init__();self.model=model
        def forward(self,mel,mask):return self.model(mel,mask,predict_events=False)['scores']
    wrapper=Scores(model).eval()
    with torch.inference_mode():
        traced=torch.jit.trace(wrapper,(torch.randn(1,80,100),torch.ones(1,100,dtype=torch.int64)),check_trace=False,strict=False)
        traced=torch.jit.freeze(traced.eval())
    from .audio_inference import LocalWhisperFeatures
    local=LocalWhisperFeatures(folder);checks=[]
    for samples in (6400,16017,47431):
        wave=np.random.default_rng(samples).normal(0,.03,samples).astype(np.float32)
        a=extractor([wave],sampling_rate=16000,padding='longest',truncation=True,max_length=480000,return_attention_mask=True,return_tensors='np')
        b=local([wave])
        np.testing.assert_allclose(a['input_features'],b['input_features'],rtol=1e-6,atol=1e-6)
        np.testing.assert_array_equal(a['attention_mask'],b['attention_mask'])
        mel=a['input_features'];mask=a['attention_mask']
        if mel.shape[-1]%2:mel=np.pad(mel,((0,0),(0,0),(0,1)));mask=np.pad(mask,((0,0),(0,1)))
        with torch.inference_mode():
            expected=wrapper(torch.from_numpy(mel),torch.from_numpy(mask))
            actual=traced(torch.from_numpy(mel),torch.from_numpy(mask))
        difference=float((actual-expected).abs().max());assert difference<1e-4,difference
        checks.append({'samples':samples,'maximum_score_error':difference})
    temporary=folder/'scores_cpu.partial.pt';traced.save(str(temporary));temporary.replace(folder/'scores_cpu.pt')
    report={'source':'LAION '+args.variant+', pinned weights; score-only TorchScript','torch':torch.__version__,'checks':checks,'seconds':time.monotonic()-started}
    (folder/'runtime_verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    faulthandler.cancel_dump_traceback_later()

if __name__=='__main__':main()
