"""Small bounded batched codec graphs; isolated from the batch-one codec banks."""
import os,time
import torch
from performance_core import CodecGraphs,StreamingCodec

BANKS={}

class BatchedCodecGraphs(CodecGraphs):
    def __init__(self,codec,audio_pad,n,frames):
        self.codec=codec;self.audio_pad=audio_pad;self.batch_size=n;self.max_frames=frames
        self.device=next(codec.parameters()).device
        self.modules=[m for m in codec.decoder.modules() if hasattr(m,'_init_streaming_state')]
        self.states=[m._init_streaming_state(n) for m in self.modules]
        if os.environ.get('HVS_CODEC_FUSED','0')=='1':
            import codec_fused
            codec_fused.install(codec,self.states)
        self.graphs={};self.capture_seconds=0.

    @torch.inference_mode()
    def capture(self):
        started=time.perf_counter();pool=torch.cuda.graph_pool_handle();stream=torch.cuda.Stream(device=self.device)
        stream.wait_stream(torch.cuda.current_stream(self.device))
        for frames in range(1,self.max_frames+1):
            static=torch.zeros(self.batch_size,frames,12,dtype=torch.long,device=self.device)
            with torch.cuda.stream(stream):
                self.eager(static);self.eager(static)
            graph=torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph,pool=pool,stream=stream):output=self.eager(static)
            self.graphs[frames]=(graph,static,output)
        torch.cuda.current_stream(self.device).wait_stream(stream);torch.cuda.synchronize(self.device)
        self.capture_seconds=time.perf_counter()-started

    def decode(self,codes):
        entry=self.graphs.get(codes.shape[1])
        if entry is None:return self.eager(codes)
        graph,static,(audio,lengths)=entry;static.copy_(codes);graph.replay()
        return audio.clone(),lengths.clone()

class SearchStreamingCodec(StreamingCodec):
    def __init__(self,codec,n,audio_pad,frames):
        if n not in (3,4) or frames not in (10,12,20):raise ValueError('Unsupported search codec shape')
        self.codec=codec;self.audio_pad=audio_pad;self.context=None
        key=(id(codec),n,frames)
        self.key=key
        if key not in BANKS:BANKS[key]=BatchedCodecGraphs(codec,audio_pad,n,frames)
        self.graphs=BANKS[key]

    def __enter__(self):
        try:return super().__enter__()
        except BaseException:
            # Failed graph capture must not leave a streaming state attached;
            # otherwise even the one-stream OOM fallback cannot enter the codec.
            for module,state in zip(self.graphs.modules,self.graphs.states):
                if module._streaming_state is state:
                    module._streaming_state=None
                    module.__dict__.pop('_update_streaming_cache',None)
            BANKS.pop(self.key,None);self.graphs=None
            raise
