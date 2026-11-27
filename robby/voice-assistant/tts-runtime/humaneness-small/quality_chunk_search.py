"""Causal ASR + VoiceCLAP + ECAPA selection without a second ASR pass."""
import time
import httpx
import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F
import torchaudio
from asr_chunk_search import ASRSearchScorer
from search_scoring import style_query

ECAPA_URL='http://127.0.0.1:8823/embed'

def combine(row,clap,speaker,weight=.6):
    """Historical Studio formula: bounded inverse WER times 40/60 CLAP/ID."""
    a=float(np.clip((clap+1.)/2.,0,1));b=float(np.clip((speaker+1.)/2.,0,1))
    gate=1.-min(1.,max(0.,float(row['prefix_wer'])))
    return {**row,'clap':float(clap),'speaker_similarity':float(speaker),
            'n_clap':a,'speaker_score':b,'gate':gate,'quality':(1.-weight)*a+weight*b,
            'reward':gate*((1.-weight)*a+weight*b),'reward_model':'clap_plus_speaker'}

class QualitySearchScorer(ASRSearchScorer):
    def __init__(self,scorers,spec,reference_path,check_cancel=lambda:None):
        super().__init__(scorers.asr,check_cancel)
        if reference_path is None:raise ValueError('Quality candidate search requires a reference voice')
        self.scorers=scorers;self.retriever=scorers.retriever;self.device=self.retriever.device
        self.want=scorers.judge.want_vector(style_query(spec),'')
        if self.want is None:raise RuntimeError('VoiceCLAP prompt embedding unavailable')
        self.client=httpx.Client(timeout=15.,trust_env=False)
        ref,sr=sf.read(reference_path,dtype='float32')
        if ref.ndim>1:ref=ref.mean(1)
        ref=torch.as_tensor(ref[:int(sr*15.)]);ref=torchaudio.functional.resample(ref,sr,16000).numpy()
        self.target=self._embed(ref)

    def _embed(self,wave):
        wave=np.asarray(wave,dtype='<f4')[-15*16000:]
        if len(wave)<10240:wave=np.pad(wave,(0,10240-len(wave)))
        for attempt in range(3):
            self.check_cancel();r=self.client.post(ECAPA_URL,content=wave.astype('<f4').tobytes())
            if r.status_code==429 and attempt<2:time.sleep(.08);continue
            r.raise_for_status();v=np.asarray(r.json()['embedding'],np.float32)
            if v.shape!=(192,) or not np.isfinite(v).all() or np.linalg.norm(v)<1e-8:raise ValueError('Invalid speaker embedding')
            return v/np.linalg.norm(v)
        raise RuntimeError('Speaker worker unavailable')

    @torch.inference_mode()
    def score(self,waves,text,final):
        rows=super().score(waves,text,final);started=time.perf_counter()
        # Bounded recent audio reduces the repeated speaker/CLAP encoding cost;
        # ASR retains its separate prefix history and explicit word timestamps.
        audio=[torchaudio.functional.resample(torch.as_tensor(w[-15*48000:],dtype=torch.float32,device=self.device),48000,16000) for w in waves]
        batch=torch.stack([F.pad(w,(0,max(len(x) for x in audio)-len(w))) for w in audio])
        embeds=self.retriever.model.encode_waveform(batch,sample_rate=16000).float()
        centered=F.normalize(embeds-torch.as_tensor(self.retriever.qmu,device=self.device),dim=-1)
        clap=(centered@torch.as_tensor(self.want,device=self.device)).cpu().tolist()
        speaker=[float(self._embed(w.detach().cpu().numpy())@self.target) for w in audio]
        self.rows=[combine(row,c,s) for row,c,s in zip(rows,clap,speaker)]
        self.last_timing['quality_seconds']=time.perf_counter()-started
        self.last_timing['total_seconds']+=self.last_timing['quality_seconds']
        return self.rows

    def close(self):self.client.close()
