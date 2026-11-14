# Pinned Parakeet Ultra / Redux worker

Robby retains the Nemotron/TYGER encoder, partial transcripts, turn taking and
interruption handling. The **pause-final transcript** can use Parakeet Ultra
on GPU 1 (new default), Redux on CPU, or any previous recognizer. The TTS
target-word boundary check also uses Ultra, with the resident original
Parakeet v3 as its failure fallback. Neither path uses forced text as evidence.

Ultra and Redux are from **Moondream**, not Moonshine:

- [Ultra model](https://huggingface.co/moondream/parakeet-ultra), revision
  `73175eb7aeb0d82f1e2a6b53b3aabc10a90bcd0b`.
- [Redux model](https://huggingface.co/moondream/parakeet-redux), revision
  `2bf128600aac4b16946f7ed8372e56117fe5e23b`.
- [Official comparison](https://moondream.ai/blog/introducing-parakeet-redux-and-ultra).

## Runtime and restart

Do **not** upgrade the existing TTS/RobBy Python environment. This worker uses
an isolated Python 3.12 environment, Torch **2.8.0+cu126**, Moondream **2.6.1**,
Kestrel **0.9.1**, native extension **0.1.8**, kernels/bundles **0.7.4** and
torch-c-dlpack-ext **0.1.5**. The shared machine has RTX 3090 GPUs and driver
550.54.15. Native CUDA graph decoding was tested on this machine; the generated
CuTe decoder fails because its runtime requires CUDA 12.8 or newer. It is
explicitly disabled with `decode_path='native'`. Do not enable it blindly.

A clean standalone environment can be built with `uv`:

```bash
uv venv --python 3.12 ~/.cache/robby-photon/venv
uv pip install --python ~/.cache/robby-photon/venv/bin/python \
  torch==2.8.0 --index-url https://download.pytorch.org/whl/cu126
uv pip install --python ~/.cache/robby-photon/venv/bin/python \
  moondream==2.6.1 kestrel==0.9.1 kestrel-native==0.1.8 \
  kestrel-kernels==0.7.4 torch-c-dlpack-ext==0.1.5 \
  fastapi uvicorn numpy huggingface-hub
~/.cache/robby-photon/venv/bin/python prepare_photon_models.py
bash start_photon_asr.sh
```

On the current machine the isolated environment also reads already-installed
pure Python packages through `robby-base.pth`; its Torch/CUDA packages are its
own. The clean installation above does not need that local convenience.

Check `http://127.0.0.1:8822/models` for `ready:true`. Both models are warmed
before being marked ready; first inference includes graph capture and is much
slower. The worker uses physical GPU 1, caps its allocator at 22%, and binds only
to loopback. It does not stop or reconfigure the podcast service on that GPU.
Voice isolation retains its own bounded process on the same card.

Set `ROBO_PHOTON_BASE=http://127.0.0.1:8822` for Robby and
`SMALL_BOUNDARY_ASR_URL=http://127.0.0.1:8822` for TTS. The latter is included in
`humaneness-small/rtx3090-speed.env`. An empty boundary URL restores the original
v3-only gate. Select v3 or original Nemotron in the UI if the optional worker
is unavailable. Existing user choices other than the former default are kept.

## Request and resource limits

`POST /transcribe/parakeet_ultra` (or `parakeet_redux`) accepts mono 16-kHz
little-endian float32 PCM, 0.1–28 seconds. It returns actual decoded `text`,
word `timestamps`, model revision and `transcribe_ms`. No prompt forces words.
Near-silence is skipped, not transcribed. `/batch/parakeet_ultra` accepts up to
eight base64 clips; up to four concurrent calls share Photon batching. A single
admission slot bounds model work; excess callers get HTTP 429 after 500 ms.
Both endpoints reject invalid/nonfinite PCM. No audio or voiceprints are stored
on disk or printed in logs. Keep these routes private behind Robby's backend.

## Measurements and reproducibility

`benchmark_photon_asr.py` compares Ultra CUDA, Redux CPU and Redux CUDA with two
authored German TTS voices, clean and with a quieter independent TV voice.
Receipts: `logs/isolation-latency/photon.json`. Warm medians: Ultra **171.8 ms**,
Redux CPU **1656.7 ms**, Redux CUDA **188.3 ms**. Ultra had zero word errors in
these small fixtures. Redux joined a compound word and, for one noisy voice,
also transcribed the background sentence. This is a smoke test, not a population
quality benchmark or evidence that Ultra always rejects background speech.
The raw-audio speaker admission gate is still required.

Run the benchmark in the isolated environment with `CUDA_VISIBLE_DEVICES=1`.
Do not run it concurrently with latency comparisons or when another workload
needs the card. `benchmark_isolation_latency.py`, `browser_isolation_latency.py`
and `verify_boundary_audio.py` cover TTS, actual HTTPS microphone/playback and
the injected unwanted-speech boundary test. The before/after deployment report
is [ISOLATION_LATENCY.md](ISOLATION_LATENCY.md).

## Optional FP32 speaker accelerator

`ecapa_gpu_worker.py` uses the **existing production** Python environment on GPU
1, not Photon’s environment. Start it separately:

```bash
ROBO_PYTHON=/home/c4r33u19/moss15v2/.venv/bin/python bash start_ecapa_gpu.sh
curl --fail http://127.0.0.1:8823/health
```

For another host, set `ROBO_PYTHON` to its Python executable. The local pinned
SpeechBrain snapshot must exist (see `speaker_teacher.resolve_model_root`), or
set `ROBO_ECAPA_ROOT` to it. The snapshot revision is
`0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`. No download occurs at startup.
The worker uses FP32, disables TF32, caps the CUDA allocator at 6%, warms once,
and binds only to loopback. `POST /embed` accepts 0.64–15 seconds of mono 16-kHz
float32 PCM; one computation runs at a time. Queue admission is limited to
200 ms. Do not expose this endpoint through Cloudflare.

Robby defaults `ROBO_SPEAKER_GPU_URL` to `http://127.0.0.1:8823`; an explicitly
empty value selects CPU only. Invalid responses, wrong revisions, congestion or
failure use the original CPU teacher with a 15-second circuit breaker. The
request timeout is 800 ms, so failure fallback costs more than a healthy worker.
Speaker references and cached vectors remain session/RAM data. No new biometric
persistence is introduced. Four CPU/GPU comparisons had cosine 1.0 to displayed
precision, maximum coordinate error <1.1e-6. This validates numerical agreement
for those samples, not general speaker recognition accuracy.

Current services: Robby 8793, TTS 8792, Photon 8822, ECAPA GPU 8823. PID receipts
are in `.runtime/`; verify actual processes and health before restarting. Do not
start duplicates. The podcast service at 8816 is independent and must remain
running. Both GPU-1 helpers and the on-demand isolation worker fit beside the
current workload, but rerun memory checks before adding another model. Current
Photon files use about 6 GB of system-disk space including the isolated runtime.
