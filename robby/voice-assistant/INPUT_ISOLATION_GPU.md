# GPU streaming target-speaker isolation for Robby

This records the isolated research benchmark on the existing RTX 3090 host.
A subsequent [optional live UI integration](INPUT_ISOLATION_UI.md) now offers
VoxLock and Scicom Agent at 40 ms, off by default. The benchmark extends
[the CPU comparison](INPUT_ISOLATION_REVIEW.md). Raw audio remains available to
the live application. Neither an identity filter nor a speech recognizer is
assumed to remove all television speech.

## Findings — November 12, 2026

**VoxLock's native FP32 CUDA-graph adapter is the most promising implementation
tested for a low-overhead Robby trial.** At 40-ms input chunks it processes a
chunk in about 3.55 ms instead of ONNX CUDA's 34.42 ms. The GPU retained-state
ONNX adapter and ONNX FP16 alone did not provide the expected improvement.
Native eager PyTorch also failed real time: graph capture is essential here.

| Configuration | Input chunk | Compute p50 / p95 | Processing RTF | First output, capture-paced |
| --- | ---: | ---: | ---: | ---: |
| VoxLock native CUDA Graphs | 16 ms | 3.25 / 3.45 ms | 0.212 | 35.70 ms |
| VoxLock native CUDA Graphs | 20 ms | 3.33 / 3.58 ms | 0.167 | 43.78 ms |
| VoxLock native CUDA Graphs | 40 ms | 3.55 / 3.59 ms | 0.089 | 44.12 ms |
| VoxLock native CUDA Graphs | 80 ms | 3.96 / 4.01 ms | 0.050 | 84.30 ms |
| VoxLock ordinary ONNX CUDA | 40 ms | 34.42 / 36.05 ms | 0.874 | 80.22 ms |
| Scicom release CUDA Graphs | 20 ms | 7.41 / 7.54 ms | 0.373 | 27.94 ms |
| Scicom release CUDA Graphs | 40 ms | 7.97 / 8.13 ms | 0.201 | 48.33 ms |
| Scicom release CUDA Graphs | 80 ms | 8.26 / 8.58 ms | 0.105 | 88.86 ms |
| Scicom agent CUDA Graphs | 40 ms | 8.01 / 8.06 ms | 0.202 | 48.57 ms |
| Scicom release eager CUDA | 40 ms | 273.54 / 294.42 ms | 6.955 | 337.00 ms, then growing backlog |

These rows use the identical Christoph + 0.5 TV mixture, with steady-state
compute measured unpaced and first output measured in a separate paced replay.
The complete 15-configuration table, including unsuccessful optimizations and
VRAM, is in `logs/input-isolation-gpu/speed-table.md` and the
[public listening report](https://diane-asylum-understood-invoice.trycloudflare.com/static/input-isolation-gpu.html).

The native 16-ms and 20-ms paths each passed a 30-second capture-paced run:
1,875 and 1,500 chunks respectively, zero processing deadlines missed. Paced
processing p95 was 4.05 / 4.08 ms. The current browser microphone sends 20-ms
packets (`static/client.js`); achieving the measured 35.7-ms first result in the
actual browser would additionally require compatible packetization. Do not
promise that number as deployed browser latency. At the current packet size,
40-ms processing is an attractive lower-compute starting point for integration.

Native VoxLock's six output WAVs closely match ONNX FP32: difference SNR
56.95–99.26 dB, maximum absolute sample difference at most 0.00148. All six ASR
results agree between the native and ordinary ONNX implementations. This is a
numerical cross-check, not bit identity or proof on unseen inputs. The ONNX
provider trace also verifies real CUDA execution: enrollment 179 CUDA nodes;
the short chunk audit 2,676 CUDA and 6 CPU node executions. Profiling is excluded
from performance figures. See `native-onnx-equivalence.json` and
`onnx-provider-audit.json`.

Process VRAM was about 930 MiB for native 16/20 ms, 1,172 MiB for native 40 ms,
and 1,606 MiB for native 80 ms (multiple pre-captured startup/flush shapes).
Scicom used about 1.9 GiB. These are process snapshots, not upper bounds for
unlimited simultaneous calls. Native models load in about 3.8–4.2 seconds;
first graph/enrollment warm-up costs additional seconds and is excluded from
streaming RTF. Keep the initialized model and warmed graphs alive.

**Quality is not ready for a universal default.** Clean speech is transcribed
correctly in all six fully scored configurations. Native VoxLock retains the
target sentence without errors in three of four mixed cases, but background
speech still leaks. Scicom agent strongly suppresses the moderate Christoph TV
tail (32.8 dB, zero active Silero frames versus 71% raw). It fails to consistently
select Selma and can suppress her intended words. In the stronger Selma mixture,
all tested families leave enough TV for VAD to remain active much of the tail.
With VoxLock, tail VAD activity falls from 71% raw to 40%/28% for Christoph,
but only from 62–63% to 57% for Selma. Suppression does not by itself solve
Robby's turn-taking or interruption logic.

Recommendation: evaluate a selectable **native VoxLock CUDA Graphs, 40-ms** input
branch with a verified reference and raw-audio fallback, rather than enabling
speaker isolation unconditionally. Scicom is a useful alternative where its
speaker selection has been verified, not a reliably superior choice based on
these two voices. Alkove remains the existing CPU baseline; no working CUDA
port was found/tested. No separate REAL-TSE checkpoint was benchmarked: VoxLock
uses that causal BSRNN family, but its results cannot stand in for other weights.

## Measurement design

All filter runs use GPU 1, one model/configuration at a time. Robby and the
podcast service stay running. This is a shared-host measurement, not an idle
dedicated-GPU specification. Torch allocations are capped at 16% of GPU memory;
ONNX Runtime has a separate 1-GiB CUDA arena cap per session. Model downloads
go to `~/.cache/robby-input-isolation`, on the system disk rather than NVMe.

Inputs are the same six authored German mixtures used in the CPU experiment:
two target voices, an independent clean introduction for enrollment, and TV
speech at relative full-clip RMS gains 0, 0.5 and 1.0. The competing voice starts
one second before the target and continues four seconds after it. This tests
the specific problematic case of background speech filling a user's pause.
Input hashes allow exact CPU/GPU comparisons. No private microphone recordings
or real user voiceprints are included.

Each backend maintains its recurrent/attention/STFT state across chunks.
20/40/80-ms inputs are pushed sequentially; independent calls on disconnected
chunks would not be an equivalent streaming experiment. All outputs must have
finite samples and the original number of samples after flushing. Scicom's
10-ms left-padding delay is removed for sample-aligned file comparisons.

Two timing protocols are recorded:

1. **Unpaced processing:** push a complete scene as quickly as possible,
   retaining stream state. RTF is total push/flush computation divided by audio
   duration; below 1 is faster than real time. Enrollment, graph capture and
   model loading are reported separately. p50/p95/p99 measure a synchronous
   CPU-audio-input to CPU-audio-output call, including transfers and overlap-add.
2. **Capture-paced replay:** make each input chunk available only at its real
   recording deadline. Measure first nonempty output and the age of the newest
   output sample. Scheduling lag is accumulated, not silently dropped. This is
   an in-process replay, **not browser microphone-to-ASR or conversation latency**.

The newest-output age is not the worst latency of every sample: samples at the
beginning of a packet also waited for that packet to fill. Do not add a packet's
duration again to the measured first-output time; it already includes capture
accumulation. Live deployments should bound queues and explicitly report/drop
overdue work if sustained RTF exceeds 1.

Quality is measured separately with the existing Parakeet v3 worker. Full-scene
WER against only the intended sentence penalizes leaked TV words as insertions
and can exceed 1. Target-interval WER includes 100 ms of padding around the known
target. A TV-only tail is transcribed separately. ASR itself can hallucinate on
quiet residuals, so this is not a substitute for listening or a VAD evaluation.
SI-SDR and tail attenuation provide additional signal diagnostics; a high
attenuation score can also mean the desired speaker was muted.

## Implementations

- **Alkove Focus:** the previous native CPU 16-ms result is a reference. No
  supported CUDA implementation was found or fabricated.
- **VoxLock ONNX CUDA:** official FP32/FP16 enrollment and chunk graphs.
  Compare ordinary `session.run` with an I/O-binding adapter retaining voice
  keys and LSTM h/c on GPU. Only frame waveforms return to CPU for the official
  overlap-add. CUDA-provider availability is asserted; a separate profiler
  audit checks actual operator placement.
- **VoxLock native PyTorch:** the upstream `export_onnx.Enroll/Chunk` modules,
  rather than a different checkpoint or approximate model. Fixed-shape CUDA
  graphs retain recurrent state, and each graph writes its final h/c back to
  the persistent input buffers. CPU framing/OLA remains the published Stream.
  Captures are warmed outside timed steady-state runs.
- **Scicom release and agent:** official `vi.server.Server` and streaming engine
  with FP16 matrix multiplies, FP32 recurrent accumulation, fixed clean manual
  enrollment and automatic re-enrollment disabled. CUDA Graphs are tested
  against eager execution. The agent variant uses its published presence gate.

Primary sources:
[VoxLock](https://github.com/arbazsiddiqui/voxlock),
[Scicom voice-isolator](https://huggingface.co/Scicom-intl/voice-isolator),
[Alkove Focus](https://alkove.ai/docs/models/focus/).
Scicom's model card declares `license: other`; do not label these weights
Apache-2.0 or redistribute them without checking the applicable terms.

## Reproduce

Use a separate environment or the existing compatible research Python. Tested
base versions: Python 3.12, PyTorch 2.6.0+cu124, ONNX Runtime GPU 1.22.0,
safetensors 0.8.0 and huggingface_hub 1.27.0. Do not replace production packages
just to run the benchmark. CUDA/cuDNN libraries must be available to ONNX Runtime.

```sh
cd robo-integration
python prepare_input_isolation_gpu.py
# CPU benchmark first, if its synthetic mixture WAVs do not already exist:
# See INPUT_ISOLATION_REVIEW.md; no need to rerun it on this machine.
CUDA_VISIBLE_DEVICES=1 OMP_NUM_THREADS=2 python benchmark_input_isolation_gpu.py \
  --model vox-naive --chunk 40 --quality --paced
CUDA_VISIBLE_DEVICES=1 OMP_NUM_THREADS=2 python benchmark_input_isolation_gpu.py \
  --model vox-resident --chunk 40 --quality --paced
CUDA_VISIBLE_DEVICES=1 OMP_NUM_THREADS=2 python benchmark_input_isolation_gpu.py \
  --model scicom --chunk 40 --quality --paced
CUDA_VISIBLE_DEVICES=1 OMP_NUM_THREADS=2 python benchmark_input_isolation_gpu.py \
  --model scicom-agent --chunk 40 --quality --paced
# Native VoxLock also needs silero-vad==6.2.1 and tableprint==0.9.1.
# Isolate these optional dependencies; don't replace the production environment:
uv pip install --python /path/to/research/python \
  --target "$HOME/.cache/robby-input-isolation/torch-deps" --no-deps \
  silero-vad==6.2.1 tableprint==0.9.1
CUDA_VISIBLE_DEVICES=1 OMP_NUM_THREADS=2 python benchmark_input_isolation_gpu.py \
  --model vox-torch --chunk 40 --quality --paced
# Repeat --chunk 20 / 80; --no-graphs measures eager native inference.
# Run scoring after GPU timing to reduce cross-service contention:
python score_input_isolation_gpu.py
python vad_input_isolation_gpu.py
python render_input_isolation_gpu.py
```

`logs/input-isolation-gpu/*.json` records arguments, revision hashes, timings,
transcripts and quality diagnostics. Each completed JSON names its output WAVs.
An error leaves a `status: failed` JSON with a traceback, never fabricated scores.
Torch's allocator counters omit ONNX allocations; the process VRAM snapshot
from `nvidia-smi` is recorded separately.

The native VoxLock adapter imports WeSpeaker's real model modules from the
pinned source without executing its unrelated package-level diarization CLI.
This avoids loading UMAP/S3PRL/Whisper frontends that the chosen ECAPA architecture
does not use. The model architecture and learned weights are unchanged.

## Scope and limitations

Two short synthetic German voices are not enough to rank general real-world
quality. Test real consented speakers, expressive speech, a quiet target, room
reverb, changing microphones, loud competing speech, music, actual Robby echo,
and short stop commands before turning a filter on by default. Keep a raw branch
for wake-word/enrollment recovery and explicit target switching. A filter with
the wrong voiceprint can erase the user while efficiently retaining television.

Warm latency does not include collecting a clean reference. Here it is already
available. Acquiring three seconds of enrollment speech from a new user still
takes three seconds of speech, regardless of GPU speed.
