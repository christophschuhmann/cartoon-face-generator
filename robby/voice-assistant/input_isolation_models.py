"""Pinned, measured CUDA-graph speaker filters. Import only in the isolated worker.

One active stream per model instance: the owner enforces exclusive session use.
See INPUT_ISOLATION_GPU.md for measurements, source licenses and failure cases.
"""
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
import torch
SR = 16000
CACHE = Path(os.environ.get('ROBO_ISOLATION_CACHE',str(Path.home()/'.cache/robby-input-isolation')))
LOCATIONS = json.loads((CACHE/'locations.json').read_text())
VOX_REV = '2413b292bc2c337bfc19a9802aaf3e011e68e9c4'
def sync(): torch.cuda.synchronize()

class ScicomGPU:
    def __init__(self, agent, graphs, chunk_ms, max_streams=1):
        sys.path.insert(0, LOCATIONS['scicom'])
        from vi.infer import load_model
        from vi.server import Server
        from vi.model import parse_gate
        path = Path(LOCATIONS['scicom']) / ('agent' if agent else '')
        t = time.perf_counter()
        self.model = load_model(str(path), device='cpu')
        self.load_ms = (time.perf_counter() - t) * 1000
        gate = parse_gate(self.model.serve_cfg['gate']) if agent else None
        self.srv = Server(self.model, max_streams=max_streams, chunk_hops=chunk_ms//10,
                          dtype=torch.float16, graphs=graphs, self_enroll=False,
                          loud=False, device='cuda', gate=gate)
        t = time.perf_counter(); self.srv.warmup(); sync()
        self.warmup_ms = (time.perf_counter() - t) * 1000
        self.meta = {'model': 'Scicom-intl/voice-isolator',
                     'revision': LOCATIONS['scicom_revision'], 'agent': agent,
                     'cuda_graphs': graphs, 'precision': 'FP16 matmul / FP32 LSTM and accumulation',
                     'algorithmic_delay_ms': self.srv.delay / SR * 1000,
                     'load_cpu_ms': self.load_ms, 'graph_warmup_ms': self.warmup_ms,
                     'gate': gate, 'enrollment': 'manual fixed clean reference; self-enrollment disabled'}

    def stream(self, enrollment, chunk_ms):
        srv = self.srv
        class S:
            def __init__(self):
                self.call = srv.open()
                srv._enroll(self.call, enrollment)
                self.buf = np.zeros(0, np.float32)
                self.total = self.emitted = 0
                self.drop = srv.delay

            def push(self, x):
                self.total += len(x)
                self.buf = np.concatenate([self.buf, x])
                ys = []
                while len(self.buf) >= srv.n:
                    y, _ = srv.step_calls([self.call], self.buf[:srv.n][None])
                    assert not self.call.nonfinite, 'Model produced non-finite samples'
                    self.buf = self.buf[srv.n:]
                    # Match original sample positions, removing causal left-padding.
                    k = min(self.drop, len(y[0])); self.drop -= k
                    ys.append(y[0, k:]); self.emitted += len(y[0]) - k
                return np.concatenate(ys) if ys else np.zeros(0, np.float32)

            def flush(self):
                total = self.total
                missing = total - self.emitted
                tail = self.push(np.zeros(srv.n + srv.delay, np.float32))[:missing]
                srv.close(self.call)
                return tail
        return S()

    def streams(self, references, chunk_ms):
        """One GPU batch: identical microphone, independent enrolled caller states."""
        srv=self.srv
        class Group:
            def __init__(self):
                self.calls=[];self.buf=np.zeros(0,np.float32)
                self.total=self.emitted=0;self.drop=srv.delay
                for ref in references:
                    call=srv.open();self.calls.append(call);srv._enroll(call,ref)
            def push(self,x):
                self.total+=len(x);self.buf=np.r_[self.buf,x];ys=[]
                while len(self.buf)>=srv.n:
                    y,_=srv.step_calls(self.calls,np.tile(self.buf[:srv.n],(len(self.calls),1)))
                    if any(c.nonfinite for c in self.calls):raise ValueError('Non-finite model output')
                    self.buf=self.buf[srv.n:];k=min(self.drop,y.shape[1]);self.drop-=k
                    ys.append(y[:,k:]);self.emitted+=y.shape[1]-k
                return np.concatenate(ys,axis=1) if ys else np.zeros((len(self.calls),0),np.float32)
            def flush(self):
                missing=self.total-self.emitted
                y=self.push(np.zeros(srv.n+srv.delay,np.float32))[:,:missing]
                for c in reversed(self.calls):srv.close(c)
                return y
        return Group()


class VoxTorchGPU:
    """Official VoxLock Enroll/Chunk modules, captured as stateful CUDA graphs.

    The causal DSP remains the published Stream. Graph inputs, voice keys and
    recurrent state stay in VRAM; only input audio and reconstructed frames cross
    the device boundary. Captures are shared serially, never between concurrent calls.
    """
    def __init__(self, graphs=True):
        from huggingface_hub import hf_hub_download
        import types
        import importlib.machinery
        sys.path.append(str(CACHE/'torch-deps'))
        sys.path.insert(0,str(CACHE/'wespeaker-src'))
        sys.path.insert(0, LOCATIONS['voxlock_source'])
        # We only use the actual WeSpeaker model modules. Its package __init__
        # imports an unrelated diarization CLI (UMAP JIT, clustering and more).
        # Bootstrap the package namespace without that CLI; no model is mocked.
        if 'wespeaker' not in sys.modules:
            package=types.ModuleType('wespeaker')
            package.__path__=[str(CACHE/'wespeaker-src/wespeaker')]
            package.__spec__=importlib.machinery.ModuleSpec('wespeaker',None,is_package=True)
            sys.modules['wespeaker']=package
        from isolate import load
        from export_onnx import Enroll, Chunk
        from voxlock import core
        paths = [hf_hub_download('arbazsiddiqui/voxlock', name, revision=VOX_REV,
                 cache_dir=str(CACHE/'hub'), token=False) for name in ['config.yaml','model.safetensors']]
        tse = load(str(Path(paths[0]).parent), device='cuda').model.eval()
        tse.spk_ft.context.fbank.dither = 0.
        self.enroll = Enroll(tse).eval().cuda()
        self.chunk = Chunk(tse).eval().cuda()
        self.core, self.graphs = core, graphs
        self.state = (6,32,256)
        self.h = torch.zeros(self.state,device='cuda')
        self.c = torch.zeros_like(self.h)
        self.voice = None
        self.captures = {}
        self.meta = {'model':'arbazsiddiqui/voxlock','revision':VOX_REV,
                     'source_commit':'48b9a71e9b6ce853670c9a4dbc64ddb532638d53',
                     'precision':'FP32','cuda_graphs':graphs,'algorithmic_delay_ms':24,
                     'backend':'native PyTorch official export_onnx Chunk; GPU-resident state'}

    def stream(self,enrollment,chunk_ms):
        from types import SimpleNamespace
        owner = self
        voice = self.enroll(torch.from_numpy(self.core.fit_sample(enrollment)[None]).cuda())
        if self.voice is None:
            self.voice = tuple(x.clone() for x in voice)
        else:
            for dst,src in zip(self.voice,voice): dst.copy_(src)
        self.h.zero_();self.c.zero_()
        # Graph buffers are shared serially; each enrolled person owns separate
        # recurrent state and voice keys. Creating another stream cannot retarget it.
        local_voice=tuple(v.clone() for v in voice)
        local_h=torch.zeros_like(self.h);local_c=torch.zeros_like(self.c)

        def capture(k):
            wav = torch.zeros((1,k*128+384),device='cuda')
            work = torch.cuda.Stream()
            work.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(work):
                for _ in range(3): owner.chunk(wav,*owner.voice,owner.h,owner.c)
            torch.cuda.current_stream().wait_stream(work)
            graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph):
                frames,h,c = owner.chunk(wav,*owner.voice,owner.h,owner.c)
                owner.h.copy_(h);owner.c.copy_(c)
            owner.h.zero_();owner.c.zero_()
            return wav,graph,frames

        if self.graphs:
            # Include startup and flush lengths; avoid a graph capture on a live chunk.
            for k in range(1,chunk_ms//8+4):
                if k not in self.captures: self.captures[k] = capture(k)
            self.h.zero_();self.c.zero_()

        class En:
            def run(self,*_): return [v.cpu().numpy() for v in local_voice]
        class Ch:
            def run(self,_,feeds):
                for dst,src in zip(owner.voice,local_voice):dst.copy_(src)
                owner.h.copy_(local_h);owner.c.copy_(local_c)
                wav = feeds['wav']
                if owner.graphs:
                    k=(wav.shape[-1]-384)//128
                    w,g,frames=owner.captures[k]
                    w.copy_(torch.from_numpy(wav));g.replay()
                else:
                    frames,h,c=owner.chunk(torch.from_numpy(wav).cuda(),*owner.voice,owner.h,owner.c)
                    owner.h.copy_(h);owner.c.copy_(c)
                local_h.copy_(owner.h);local_c.copy_(owner.c)
                # CPU h/c placeholders satisfy the official Stream API. Actual state stays above in VRAM.
                return frames.cpu().numpy(),feeds['h'],feeds['c']
        proxy=SimpleNamespace(enroll=En(),chunk=Ch(),state=self.state)
        return self.core.Stream(proxy,self.core.fit_sample(enrollment))
