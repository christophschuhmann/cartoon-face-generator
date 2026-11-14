# Live Robby and Podcast GPU allocation

The running services use the two physical RTX 3090 GPUs independently:

| Service | Device | Local port |
| --- | --- | --- |
| Robby ASR, TYGER and speaker identity | GPU 0 | 8793, 8801 |
| Robby Humaneness Small RL streaming TTS and scorers | GPU 0 | 8792 |
| Robby Humaneness Ears voice captions | GPU 0 | 8802 |
| Robby optional diarization worker | GPU 0 | 8796 |
| Robby sound captions | GPU 0 | 8803 |
| Optional local Nemotron Bolt LLM | CPU (`-ngl 0`) | 8799 |
| Humaneness Podcast API and generation worker | GPU 1 | 8816 |

Robby still defaults to Qwen 27B through Cerebras/OpenRouter. Moving the optional
local Bolt fallback to CPU does not change that selected provider. The idle
Audio Decision lab model was unloaded from VRAM; its HTTP service stays online.
Its existing minimum-free-VRAM guard prevents it loading when there is
insufficient room alongside Robby. Do not reload optional research models by
stopping the Podcast worker or other active services.

The conversation process was also restarted while no browser session was
connected, releasing accumulated GPU allocator caches. Both Cloudflare tunnel
processes and the Podcast API stayed running. The first Podcast job completed
and its queued successor started during this operation.

Public entry points (existing tunnels, no new tunnel created):

- [Robby](https://diane-asylum-understood-invoice.trycloudflare.com/desk-robot/)
- [Podcast API UI](https://arrive-locations-parade-research.trycloudflare.com/podcast/)
- [Podcast Swagger](https://arrive-locations-parade-research.trycloudflare.com/podcast/docs)

## Restarting

`humaneness-small/gpu-layout.local.env` now supplies the physical GPU 0 allocation
to both existing TTS launchers (`run.sh` and `start_rtx3090_tts.sh`). Keep the
existing optimized precision settings and private environment. Do not launch a
second TTS instance on port 8792. CPU checkpoint loading and CUDA compilation
must finish before `/api/state` reports `ready: true`.

For the caption sidecar use `ROBO_CAPTION_DEVICE=cuda:0`. For the diarization
sidecar use `CUDA_VISIBLE_DEVICES=0 ROBO_DIARIZATION_DEVICE=cuda`. Leave the
Podcast deployment at `PODCAST_DEVICE=cuda:1`; its deployment file and running
worker were not modified. The Podcast restart utility is documented in the
separate `Humaneness-Podcast-Server` repository; do not restart it during jobs
merely to restart Robby.

`rebalance_live_gpus.py` records the one-time migration procedure. It requires
current, explicitly verified PIDs and idle Robby TTS/Decision services. It reads
private environment variables directly from the owned processes in RAM, never
prints or saves them, and never stops Podcast. It is not a boot-time supervisor.
Nonsecret current PIDs are in `logs/gpu-split-deployment.json`.

## Verification

`verify_gpu_split.py` tests the public HTTPS page, a typed two-sentence request,
and a real browser capture/worklet/WebSocket path using an authored synthetic
wake-phrase WAV. It checks submitted ASR text, LLM responses, nonzero real PCM,
completion and advancing browser playback. It uses an isolated browser profile,
so it does not change the user's camera, memory or microphone preferences.

Results are recorded in `logs/gpu-split-browser-verification.json`, with browser
screenshots alongside it. This test does not establish physical microphone,
webcam, loudspeaker or room-echo behavior. The current deployment should only be
called verified after that report says `passed: true`.

On this machine, the already cached Playwright environment can be used without
installing packages into the model runtime:

```bash
cd /mnt/nvme/moss-15-v2
PYTHONPATH="$PWD/.cache/uv/archive-v0/aLz2M8LD3mNySYW7/lib/python3.12/site-packages" \
  /home/c4r33u19/moss15v2/.venv/bin/python -u robo-integration/verify_gpu_split.py
```

The first readiness check reached its ten-minute wait limit during cold
Inductor autotuning after the GPU/index change. No speech test had run at that
point. The checker now allows thirty minutes for startup; this cold compilation
time must not be confused with the latency of a warmed speech request.

Verified on 2026-11-09: both browser cases passed through the public HTTPS
tunnel. The typed request produced two complete reply sentences and 16 PCM
chunks. The synthetic microphone case exercised actual browser capture,
resampling, ASR submission and spoken response, with more than 1,000 captured
microphone blocks and no page JavaScript errors. Both TTS and the conversation
server reported ready with no errors afterward. The Podcast queue continued
processing jobs throughout the migration and tests.

All original inference optimizations, including `ACTING_COMPILE_GLOBAL=1`, are
retained. Cold compilation completed before a fallback restart was needed.
The separate fallback restart was therefore not executed. Full process/device
evidence and public HTTP checks are in `logs/gpu-split-deployment.json`.
