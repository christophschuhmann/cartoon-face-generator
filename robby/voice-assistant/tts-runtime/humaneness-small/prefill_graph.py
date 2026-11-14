"""Bounded, left-padded CUDA graphs for Qwen3 semantic prompt prefilling.

Weights/position IDs/attention stay unchanged. Only masked leading padding is
added; cache outputs are sliced back to the original width before decoding.
This reduces thousands of Python/CUDA launches to one replay per prompt.
"""
from collections import OrderedDict
from types import SimpleNamespace
import torch

class PrefillGraphs:
    def __init__(self,model,forward,limit=2):
        self.model=model;self.forward=forward;self.limit=limit;self.banks=OrderedDict()
        self.capture_seconds=0.

    def __call__(self,ids,mask):
        rows,length,channels=ids.shape
        width=((length+255)//256)*256
        # Bound VRAM and preserve eager operation for unusual batch/prompt sizes.
        if rows!=2 or width>512:
            return self.forward(inputs_embeds=self.model._build_inputs_embeds(ids),input_ids=None,
                attention_mask=mask,past_key_values=None,use_cache=True,return_dict=True)
        key=(rows,width);pad=width-length
        if key not in self.banks:
            import time
            started=time.perf_counter()
            static=torch.full((rows,width,channels),self.model.config.audio_pad_token_id,dtype=ids.dtype,device=ids.device)
            static[:,:,0]=self.model.config.pad_token_id
            valid=torch.zeros((rows,width),dtype=torch.bool,device=ids.device)
            static[:,pad:].copy_(ids);valid[:,pad:].copy_(mask)
            def run():
                return self.forward(inputs_embeds=self.model._build_inputs_embeds(static),input_ids=None,
                    attention_mask=valid,past_key_values=None,use_cache=True,return_dict=True)
            side=torch.cuda.Stream(device=ids.device);side.wait_stream(torch.cuda.current_stream(ids.device))
            with torch.cuda.stream(side):
                for _ in range(2):run()
            torch.cuda.current_stream(ids.device).wait_stream(side)
            graph=torch.cuda.CUDAGraph()
            with torch.cuda.graph(graph):out=run()
            self.banks[key]=(static,valid,graph,out)
            self.capture_seconds+=time.perf_counter()-started
            while len(self.banks)>self.limit:self.banks.popitem(last=False)
        self.banks.move_to_end(key)
        static,valid,graph,out=self.banks[key]
        static[:,:,:].fill_(self.model.config.audio_pad_token_id)
        static[:,:,0].fill_(self.model.config.pad_token_id)
        valid.zero_();static[:,pad:].copy_(ids);valid[:,pad:].copy_(mask)
        graph.replay()
        return SimpleNamespace(last_hidden_state=out.last_hidden_state[:,pad:],
            past_key_values=tuple((k[:,pad:],v[:,pad:]) for k,v in out.past_key_values))
