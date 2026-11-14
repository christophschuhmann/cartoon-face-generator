"""Experimental causal union of enrolled-speaker estimates, never a sum of voices.

Maximum spectral gain against the original mixture avoids amplifying duplicate
estimates. It cannot repair separator leakage or prove absence of unknown voices.
512-sample sqrt-Hann, 128-sample hop adds 24 ms when two or more voices are kept.
"""
import numpy as np

class SpectralUnion:
    def __init__(self,n):
        self.n=n;self.win=np.sqrt(np.hanning(513)[:-1]);self.buf=np.zeros((n+1,384))
        self.ola=np.zeros(512);self.norm=np.zeros(512);self.drop=384;self.total=self.emitted=0
    def push(self,raw,estimates):
        self.total+=len(raw);self.buf=np.c_[self.buf,np.vstack([raw,estimates])];ys=[]
        while self.buf.shape[1]>=512:
            z=np.fft.rfft(self.buf[:,:512]*self.win,axis=1);self.buf=self.buf[:,128:]
            mask=np.minimum(1.,np.max(np.abs(z[1:]),axis=0)/np.maximum(np.abs(z[0]),1e-8))
            self.ola+=np.fft.irfft(z[0]*mask,n=512)*self.win;self.norm+=self.win**2
            out=self.ola[:128]/np.maximum(self.norm[:128],1e-8)
            k=min(128,self.drop);self.drop-=k;ys.append(out[k:].copy());self.emitted+=128-k
            self.ola=np.r_[self.ola[128:],np.zeros(128)];self.norm=np.r_[self.norm[128:],np.zeros(128)]
        return np.concatenate(ys).astype(np.float32) if ys else np.zeros(0,np.float32)
    def flush(self):
        missing=self.total-self.emitted
        return self.push(np.zeros(896),np.zeros((self.n,896)))[:missing]

class KnownVoiceStream:
    def __init__(self,model,references):
        self.n=len(references);self.raw=np.zeros(0,np.float32)
        self.group=model.streams(references,40) if hasattr(model,'streams') else None
        self.streams=[] if self.group else [model.stream(r,40) for r in references]
        self.union=SpectralUnion(self.n) if self.n>1 else None
    def consume(self,y):
        count=y.shape[1];raw=self.raw[:count];self.raw=self.raw[count:]
        if len(raw)!=count:raise ValueError('Separator alignment mismatch')
        return self.union.push(raw,y) if self.union else y[0]
    def push(self,x):
        self.raw=np.r_[self.raw,x]
        y=self.group.push(x) if self.group else np.stack([s.push(x) for s in self.streams])
        return self.consume(y)
    def flush(self):
        y=self.group.flush() if self.group else np.stack([s.flush() for s in self.streams])
        result=self.consume(y)
        if len(self.raw):raise ValueError('Separator did not flush all samples')
        return np.r_[result,self.union.flush()] if self.union else result
