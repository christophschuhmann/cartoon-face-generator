"""Real, stateful GPU speaker-isolation experiments; no production configuration edits.

Use CUDA_VISIBLE_DEVICES to select a spare GPU. Weights/source locations are in
~/.cache/robby-input-isolation/locations.json, pinned by prepare instructions in
INPUT_ISOLATION_GPU.md. Existing synthetic fixtures match the CPU comparison.
Outputs are mono 16-kHz FLOAT WAVs; no private microphone recordings are used.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

import numpy as np
import soundfile as sf
import torch  # Load CUDA/cuDNN libraries before ONNX Runtime's CUDA provider.

from benchmark_input_isolation import audio, sisdr, SR

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'logs/input-isolation-gpu'
OUT.mkdir(exist_ok=True)
CACHE = Path.home() / '.cache/robby-input-isolation'
LOCATIONS = json.loads((CACHE / 'locations.json').read_text())
VOX_REV = '2413b292bc2c337bfc19a9802aaf3e011e68e9c4'
torch.set_num_threads(2)
torch.set_num_interop_threads(2)
torch.cuda.set_per_process_memory_fraction(.16)


def sync():
    torch.cuda.synchronize()


class VoxGPU:
    """Official streaming STFT/OLA, with optional GPU-resident LSTM and voice state."""
    def __init__(self, mode, precision='fp32', profile=False):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        sys.path.insert(0, LOCATIONS['voxlock_source'])
        from voxlock import core
        self.ort, self.core, self.mode = ort, core, mode
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        options.enable_profiling = profile
        options.profile_file_prefix = str(OUT / ('ort-' + mode))
        providers = [('CUDAExecutionProvider', {'device_id': 0,
                      'gpu_mem_limit': 1024**3, 'arena_extend_strategy': 'kSameAsRequested'}),
                     'CPUExecutionProvider']
        names = core.PRECISIONS[precision]
        paths = [hf_hub_download('arbazsiddiqui/voxlock', f'onnx/v2/{n}.onnx',
                 revision=VOX_REV, cache_dir=str(CACHE / 'hub'), token=False) for n in names]
        self.enroll = ort.InferenceSession(paths[0], options, providers=providers)
        self.chunk = ort.InferenceSession(paths[1], options, providers=providers)
        assert self.chunk.get_providers()[0] == 'CUDAExecutionProvider'
        assert self.enroll.get_providers()[0] == 'CUDAExecutionProvider'
        self.state = tuple(next(x.shape for x in self.chunk.get_inputs() if x.name == 'h'))
        self.meta = {'model': 'arbazsiddiqui/voxlock', 'revision': VOX_REV,
                     'source_commit': '48b9a71e9b6ce853670c9a4dbc64ddb532638d53',
                     'precision': precision, 'mode': mode,
                     'providers': self.chunk.get_providers(), 'algorithmic_delay_ms': 24}

    def stream(self, enrollment, chunk_ms):
        owner, core, ort = self, self.core, self.ort
        class ResidentStream(core.Stream):
            def __init__(self):
                super().__init__(owner, core.fit_sample(enrollment))
                self.voice_gpu = {k: ort.OrtValue.ortvalue_from_numpy(v, 'cuda', 0)
                                  for k, v in self.voice.items()}
                self.h_gpu = ort.OrtValue.ortvalue_from_numpy(self.h, 'cuda', 0)
                self.c_gpu = ort.OrtValue.ortvalue_from_numpy(self.c, 'cuda', 0)

            def _run(self, frames_per_run):
                # Identical causal framing, flush and normalization to the official Stream.
                out = []
                while self.buf is not None and len(self.buf) >= core.NFFT:
                    k = min(frames_per_run, 1 + (len(self.buf) - core.NFFT) // core.HOP)
                    seg = np.ascontiguousarray(self.buf[:(k - 1) * core.HOP + core.NFFT][None])
                    io = owner.chunk.io_binding()
                    wav = ort.OrtValue.ortvalue_from_numpy(seg, 'cuda', 0)
                    io.bind_ortvalue_input('wav', wav)
                    for name, val in {**self.voice_gpu, 'h': self.h_gpu, 'c': self.c_gpu}.items():
                        io.bind_ortvalue_input(name, val)
                    for output in owner.chunk.get_outputs():
                        io.bind_output(output.name, 'cuda', 0)
                    owner.chunk.run_with_iobinding(io)
                    vals = io.get_outputs()
                    fr = vals[0].numpy()  # Only waveform frames return to CPU, not recurrent state.
                    self.h_gpu, self.c_gpu = vals[1:]
                    ola = np.concatenate([self.ola, np.zeros(k * core.HOP, np.float32)])
                    env = np.concatenate([self.env, np.zeros(k * core.HOP, np.float32)])
                    for j in range(k):
                        ola[j*core.HOP:j*core.HOP+core.NFFT] += fr[0, j]
                        env[j*core.HOP:j*core.HOP+core.NFFT] += core.WIN2
                    done = k * core.HOP
                    y = ola[:done] / np.where(env[:done] > 1e-11, env[:done], 1.)
                    self.ola, self.env, self.buf = ola[done:], env[done:], self.buf[done:]
                    cut = min(self.dropped, len(y)); self.dropped -= cut
                    out.append(y[cut:] * core.GAIN)
                return np.concatenate(out) if out else np.zeros(0, np.float32)
        return ResidentStream() if self.mode == 'resident' else core.Stream(self, core.fit_sample(enrollment))

    def finish_profile(self):
        result = {}
        for kind, session in [('enroll', self.enroll), ('chunk', self.chunk)]:
            path = session.end_profiling()
            if not path:
                continue
            data = json.loads(Path(path).read_text())
            counts, durations = {}, {}
            for event in data:
                provider = event.get('args', {}).get('provider')
                if provider:
                    counts[provider] = counts.get(provider, 0) + 1
                    durations[provider] = durations.get(provider, 0) + event.get('dur', 0)
            result[kind] = {'node_execution_counts': counts, 'node_duration_us': durations}
            Path(path).unlink()  # Huge trace is redundant after the provider audit summary.
        return result


from input_isolation_models import ScicomGPU, VoxTorchGPU


def replay(model, x, enrollment, chunk_ms, paced=False):
    t = time.perf_counter(); stream = model.stream(enrollment, chunk_ms); sync()
    setup_ms = (time.perf_counter() - t) * 1000
    chunk = round(SR * chunk_ms / 1000)
    outputs, times, lags = [], [], []
    first = None
    started = time.perf_counter()
    for at in range(0, len(x), chunk):
        end = min(len(x), at + chunk)
        if paced:
            time.sleep(max(0, started + end / SR - time.perf_counter()))
        t = time.perf_counter(); y = stream.push(x[at:end])
        ms = (time.perf_counter() - t) * 1000
        times.append(ms); outputs.append(y)
        if len(y) and first is None:
            first = {'input_ms': end/SR*1000, 'wall_ms': (time.perf_counter()-started)*1000}
        if len(y) and paced:
            # Age of newest available output sample, including buffering + processing.
            lags.append((time.perf_counter()-started - sum(map(len,outputs))/SR)*1000)
    t = time.perf_counter(); outputs.append(stream.flush()); sync()
    tail_ms = (time.perf_counter()-t)*1000
    elapsed = time.perf_counter()-started
    y = np.concatenate(outputs)
    assert len(y) == len(x), (len(y),len(x))
    assert np.isfinite(y).all()
    stats = {'setup_ms': setup_ms, 'chunk_ms': chunk_ms, 'paced': paced,
             'duration_s': len(x)/SR, 'processing_rtf': (sum(times)+tail_ms)/(len(x)/SR*1000),
             'wall_s': elapsed, 'chunk_count': len(times),
             'chunk_p50_ms': float(np.percentile(times,50)),
             'chunk_p95_ms': float(np.percentile(times,95)),
             'chunk_p99_ms': float(np.percentile(times,99)),
             'chunk_max_ms': max(times), 'deadline_misses': sum(t > chunk_ms for t in times),
             'first_output': first, 'tail_flush_ms': tail_ms}
    if lags:
        stats['output_age_p50_ms'] = float(np.percentile(lags,50))
        stats['output_age_p95_ms'] = float(np.percentile(lags,95))
        stats['output_age_max_ms'] = max(lags)
    return y, stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', choices=['vox-naive','vox-resident','vox-torch','scicom','scicom-agent'], required=True)
    p.add_argument('--precision', choices=['fp32','fp16'], default='fp32')
    p.add_argument('--chunk', type=int, choices=[16,20,40,80], default=40)
    p.add_argument('--graphs', action=argparse.BooleanOptionalAction, default=True)
    p.add_argument('--quality', action='store_true')
    p.add_argument('--paced', action='store_true')
    p.add_argument('--paced-seconds', type=float, default=0,
                   help='Repeat the paced test scene to this duration; tests sustained stateful throughput.')
    p.add_argument('--profile', action='store_true')
    p.add_argument('--warmup-seconds',type=float,default=0)
    p.add_argument('--timing-seconds',type=float,default=0,
                   help='Short diagnostic timing probe; not a full quality comparison.')
    p.add_argument('--tag',default='',help='Optional separate artifact name for repeat/probe runs.')
    a = p.parse_args()
    if a.model.startswith('scicom') and a.chunk==16:
        p.error('Scicom requires a multiple of 20 ms.')
    label = f'{a.model}-{a.precision if a.model in ("vox-naive","vox-resident") else ("graph" if a.graphs else "eager")}-{a.chunk}'
    if a.tag: label+='-'+a.tag
    report = {'date': '2026-11-12', 'label': label, 'arguments': vars(a),
              'gpu': torch.cuda.get_device_name(), 'torch': torch.__version__,
              'cuda': torch.version.cuda, 'synthetic_only': True,
              'input_device_network_and_asr_in_timing': False, 'rows': []}
    path = OUT / (label + '.json')
    def save():
        path.write_text(json.dumps(report,indent=2))
    try:
        t = time.perf_counter()
        model = (VoxTorchGPU(a.graphs) if a.model=='vox-torch' else
                 VoxGPU(a.model.split('-')[1],a.precision,a.profile) if a.model.startswith('vox')
                 else ScicomGPU(a.model=='scicom-agent',a.graphs,a.chunk))
        sync(); report['model_initialize_ms'] = (time.perf_counter()-t)*1000
        report['model'] = model.meta
        print(json.dumps({'initialized':label,'ms':report['model_initialize_ms']}),flush=True)
        # Exclude first-use CUDA/cuDNN/allocator costs from the steady-state comparisons.
        warm = audio('christoph-followup')
        ref = audio('christoph-intro')
        warm=np.tile(warm,2)
        if a.warmup_seconds: warm=warm[:round(a.warmup_seconds*SR)]
        t=time.perf_counter();replay(model,warm,ref,a.chunk)
        report['additional_warmup_ms']=(time.perf_counter()-t)*1000
        cases = [('christoph',0.5)] if not a.quality else [(s,l) for s in ['christoph','selma'] for l in [0.,.5,1.]]
        for speaker,level in cases:
            case=f'{speaker}-bg{level:g}'
            x,sr = sf.read(ROOT/'logs/input-isolation'/(case+'-raw.wav'),dtype='float32')
            assert sr == SR
            if a.timing_seconds: x=x[:round(a.timing_seconds*SR)]
            ref=audio(speaker+'-intro')
            target=audio(speaker+'-followup'+('-clear' if speaker=='selma' else ''))
            y,stats=replay(model,x,ref,a.chunk)
            stats.update(case=case,speaker=speaker,background_gain=level,
                         input_sha256=hashlib.sha256(x.tobytes()).hexdigest(),
                         target_si_sdr_db=sisdr(y[SR:SR+len(target)],target) if len(y)>=SR+len(target) else None,
                         target_start_s=1., target_end_s=1+len(target)/SR)
            if level and len(x)>2*SR+len(target):
                start=2*SR+len(target)
                stats['background_only_attenuation_db']=float(10*np.log10((np.mean(x[start:]**2)+1e-12)/(np.mean(y[start:]**2)+1e-12)))
            filename=f'{label}-{case}.wav';sf.write(OUT/filename,y,SR,subtype='FLOAT')
            stats['audio']=filename
            report['rows'].append(stats);save()
            print(json.dumps({'label':label,**stats}),flush=True)
        if a.paced:
            x,sr=sf.read(ROOT/'logs/input-isolation/christoph-bg0.5-raw.wav',dtype='float32')
            if a.paced_seconds:
                x=np.resize(x,round(a.paced_seconds*SR))
            _,report['paced']=replay(model,x,audio('christoph-intro'),a.chunk,True);save()
            print(json.dumps({'label':label,'paced':report['paced']}),flush=True)
        report['torch_peak_allocated_mib']=torch.cuda.max_memory_allocated()/1024**2
        report['torch_peak_reserved_mib']=torch.cuda.max_memory_reserved()/1024**2
        # Torch counters omit ONNX Runtime's allocator: do not mistake them for total process VRAM.
        import subprocess
        report['gpu_process_memory']=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory',
            '--format=csv,noheader'],text=True).strip().splitlines()
        report['pid']=os.getpid()
        if a.profile: report['provider_profile']=model.finish_profile()
        report['status']='completed';save()
    except Exception:
        report['status']='failed';report['error']=traceback.format_exc();save()
        raise


if __name__ == '__main__':
    with torch.inference_mode():
        main()
