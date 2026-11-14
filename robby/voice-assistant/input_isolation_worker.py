"""Owned CUDA worker, reached only through an inherited local pipe, never HTTP.

All audio/voice references are session RAM only. CUDA is initialized here after
the parent has selected the physical GPU in the subprocess environment. Exiting
releases every graph, recurrent state and model allocation.
"""
import argparse
from multiprocessing.connection import Connection
import time
import numpy as np


def serve(fd):
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    torch.cuda.set_per_process_memory_fraction(.16)
    from input_isolation_models import VoxTorchGPU, ScicomGPU
    from input_isolation_union import KnownVoiceStream
    conn=Connection(fd)
    model=stream=None
    with torch.inference_mode():
        while True:
            try:message=conn.recv()
            except EOFError:break
            started=time.perf_counter()
            try:
                kind=message['op']
                if kind=='load':
                    if model is not None:raise ValueError('One model per owned worker')
                    name=message['model']
                    if name not in ('voxlock','scicom'):raise ValueError('Unknown filter')
                    model=VoxTorchGPU(True) if name=='voxlock' else ScicomGPU(True,True,40,max_streams=4)
                    result={'model':model.meta,'gpu':torch.cuda.get_device_name(),'chunk_ms':40}
                elif kind=='enroll':
                    refs=[np.asarray(r,np.float32) for r in message.get('references',[message.get('reference')])]
                    if not 1<=len(refs)<=4:raise ValueError('One to four enrolled voices supported')
                    if any(r.ndim!=1 or not 48000<=len(r)<=96000 or not np.isfinite(r).all() for r in refs):
                        raise ValueError('References must be 3–6 seconds of finite mono 16-kHz audio')
                    if stream is not None:stream.flush()
                    stream=KnownVoiceStream(model,refs)
                    torch.cuda.synchronize()
                    result={'reference_s':len(refs[0])/16000,'known_voices':len(refs),'union_delay_ms':24 if len(refs)>1 else 0}
                elif kind=='push':
                    x=np.asarray(message['audio'],np.float32)
                    if x.shape!=(640,) or not np.isfinite(x).all():raise ValueError('Expected one 40-ms audio chunk')
                    if stream is None:raise ValueError('No reference voice')
                    y=stream.push(x)
                    if not np.isfinite(y).all():raise RuntimeError('Non-finite filter output')
                    result={'audio':y}
                elif kind=='flush':
                    tail=np.asarray(message.get('audio',[]),np.float32)
                    if tail.ndim!=1 or len(tail)>=640 or not np.isfinite(tail).all():raise ValueError('Invalid final fragment')
                    if stream is not None:
                        first=stream.push(tail) if len(tail) else np.zeros(0,np.float32)
                        y=np.concatenate([first,stream.flush()])
                    else:y=np.zeros(0,np.float32)
                    stream=None;result={'audio':y}
                else:raise ValueError('Unknown operation')
                conn.send({'ok':True,**result,'compute_ms':(time.perf_counter()-started)*1000})
            except Exception as exc:
                # No audio, transcripts, references or credentials in logs or errors.
                conn.send({'ok':False,'error':type(exc).__name__,'operation':message.get('op')})
                break  # A failed CUDA context is never reused.
    conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fd',type=int,required=True)
    serve(parser.parse_args().fd)
