# Context-aware AudioSet Decision Lab

An additive research page for Robby, using **LiquidAI/d1-Omni-2B** on the local GPU. Upload audio, record with the browser, or inspect a live stream. The original conversation, avatar, ASR and TTS services remain separate.

Live page: https://diane-asylum-understood-invoice.trycloudflare.com/audio-decision/

The page's **Measurements & methods** link contains actual hardware timings, browser results, and temporal-focus limitations. This is a research visualization of model decisions, not a validated 100 ms sound-event detector.

## New group-batching experiment — 9 November 2026

[Detailed methodology and reproduction](BATCH64.md) · [public measured report](https://diane-asylum-understood-invoice.trycloudflare.com/audio-decision/batch64.html). Batching eight unchanged 64-class groups reduced the same-run median from 2.091 to 1.676 seconds. An additional all-nine-group test reached 1.572 seconds in one verified forward. Small numerical score differences remain. This is an isolated prototype; the live engine and its defaults have not been switched.

## What runs

- Checkpoint: [`LiquidAI/d1-Omni-2B`](https://huggingface.co/LiquidAI/d1-Omni-2B), revision `81222dae8bf8bdd7f903643b5b2a8803bf2e3176`.
- RTX 3090 24 GB, GPU 0; BF16, PyTorch 2.6.0+cu124, NVIDIA driver 550.54.15. Other workloads remain on both GPUs. Results are not isolated-device peak benchmarks.
- Transformers 5.19.0, huggingface-hub 2.4.0 and tokenizers 0.23.3 are isolated in `/mnt/nvme/robby-audio-decision/env`. Robby's original Python environment is not upgraded.
- Official `system_one` API, independent `noul` binary decisions or `choice` with `multiple=True`. No softmax across sound classes and no generated JSON probabilities.
- AudioSet Strong: **456** classes, default. Classic AudioSet: **527** classes, selectable. Strong is its own label set, not an assumed synonym for the classic list. The full ontology contains 632 nodes; these are not all evaluated classes.
- These are text-queried event labels, not a claim that d1 has a trained 456/527-way AudioSet classification head.

Each class retains its official MID, display name, ontology description, parents and children. Source URLs, hashes and licensing are in `data/taxonomy.json`.

## Interpretation matters

The audio-history clip includes the target. The prompt gives its exact duration, target start/end, and says to evaluate only the final hop. The optional second audio item repeats exactly that hop, using the documented ordered multi-audio interface. The repeat is not an extra event.

**The model does not reliably enforce subsecond localization.** In an authored 2-second beep probe, a beep only in the first 200 ms still received a higher final-interval beep score than a beep actually in the last 200 ms. Repeating the silent target did not fix this. Silence also produced false positives. This is a concrete failure, not a claimed detection benchmark. Prompted time ranges and finer output grids do not create calibrated temporal resolution. Inspect the report before interpreting event boundaries.

“Raw” means the unsmoothed native d1 score. The checkpoint's own release calibration is applied by its official runner. We do not expose pre-calibration logits and do not claim an AudioSet, scene-context, or short-window calibration. Smoothed values are a causal visualization only. The optional context and previous-detection feedback may bias results; both can be disabled. Disabling scene context does not disable the explicit target-interval instruction.

## Operating the page

1. Upload WAV, MP3, M4A, OGG, FLAC or WebM (up to 32 MB / 120 s), or explicitly press Record. There is no microphone permission request on page load.
2. Set a scene description, output hop (100–1,000 ms; default 200 ms), and history (2–20 s; default 10 s). Initial windows use available past samples; they do not wait ten seconds.
3. Select all classes or a smaller set. Default: all Strong classes, independent binary questions, groups of 16. **Fast grouped mode** chooses multi-label groups of 64; it is faster but uses a different question formulation and has not been shown more accurate.
4. Analyze. A short job-submission request returns immediately; progress polling avoids Cloudflare 524 timeouts. Partial rows can be explored while processing continues. Stop retains computed rows; unevaluated rows are null.
5. Play or seek: Top-N, waveform and heatmap follow the actual audio position, including while paused. Select 1–10 classes, a minimum score, raw/smoothed view, class filtering, sorting, zoom, and derived event outlines.
6. Live mode sends real PCM through AudioWorklet/WebSocket. One inference runs at a time; the next uses the newest complete interval. Skipped intervals stay null. The displayed latency is from the browser's AudioContext-based capture timestamp to the next rendering frame. The audio-frame clock is mapped to the monotonic browser clock per packet, accounting for graph startup/suspension and queued worklet delivery rather than using a fixed page-start offset. It includes buffering, transport, inference and UI scheduling; unmeasured microphone hardware latency is not included.
7. After stopping live capture, the recording and all scored/missing intervals remain available for playback and JSON/CSV export. CSV empty cells mean missing, not zero. JSON carries class IDs, settings, context, model revision, raw/smoothed matrices, group failures, events and timing metrics.

Changing a context or inference setting does not relabel old scores. A warning and the original settings remain visible. Repeat Analyze to create a new, separately keyed result. Results and audio can be reopened from the private session library.

## Architecture and isolation

```text
existing Cloudflare tunnel (unchanged)
  └─ Robby aiohttp origin :8793
       ├─ existing conversation / avatar / ASR routes (unchanged behavior)
       └─ /audio-decision/*  →  private FastAPI service :8815
                                   ├─ browser capability cookie + job admission
                                   ├─ ffmpeg → 16 kHz mono private audio
                                   ├─ causal windows / bounded live ring buffer
                                   ├─ d1 engine on GPU 0
                                   └─ private results → canvas roll / exports
optional FastAPI facade :8798 also forwards /audio-decision/*
```

`audio_decision_proxy.py` installs the new aiohttp routes; `bolt_api.py` also supports the existing facade. Internal model-management endpoints are blocked by both proxies. The tunnel is reused, not restarted. No new public listening port is created.

The optional AV lab and this decision lab share a nonblocking file lease (`optional_lab_gpu.py`). On demand they unload each other's **idle optional models** and reload from local disk when next used. This is disk-backed unloading/reloading, not CPU-RAM weight offloading. Conversation models and other users' GPU processes are never stopped by this coordination. There must be at least 6 GiB free VRAM before d1 loading. Busy optional-lab conflicts are explicit; there is no GPU job backlog.

Audio preprocessing and audio-encoder/projector outputs are reused across question groups within one window. The cache is local to that inference, keyed by the exact input features/masks, and discarded afterward. A cached/uncached comparison produced maximum absolute score difference **0.0**. Language-model prefix KV reuse across question groups is deliberately not attempted: the official decision set uses bidirectional joint processing, so ordinary autoregressive KV reuse would change semantics. A 527-class call is split into 33 groups of 16 or 9 groups of 64; it is not claimed to be a single forward pass.

## Privacy and resource limits

- Recordings and scene text are not exposed as static files. Random browser capability cookies are HttpOnly, SameSite=Strict and Secure over HTTPS; stored owner directories use a hash. Another browser cannot read an asset merely by knowing its ID.
- Session isolation is not account authentication. This existing public tunnel has no additional account-level access control. GPU admission, limits and same-origin checks reduce accidental overload; a determined public client can create new sessions. Add Cloudflare Access if stronger access control is required.
- One GPU job globally, up to two concurrent decodes, 12 starts/hour per capability, 12 recordings/session, 120 seconds audio and 32 MB uploads. File jobs stop after two hours. Live capture has a 120-second audio cap, about 140-second receive lifetime and 15-second input idle timeout.
- Private files: `/mnt/nvme/robby-audio-decision/private`, owner-only access, one-hour inactivity retention, global 1 GB budget, periodic cleanup. Active jobs/audio are protected. Explicit Delete removes this browser's records. Server restart retains completed cache files, but not in-flight computation.
- A recent result may be evicted early to maintain the storage cap. Export before leaving if needed. Private source audio, cookies, profiles and credentials are not included in the repository or public report.
- FFmpeg permits only local file/pipe protocols and selected audio containers. No network playlists or remote URL inputs are accepted.

## Reproduce and restart

Run from `robby/voice-assistant` in a source checkout, or `/mnt/nvme/moss-15-v2/robo-integration` on this host. The host's base Python is `/home/c4r33u19/moss15v2/.venv/bin/python`.

```bash
# First setup on this host; downloads about 4.34 GB, with a pinned revision.
/home/c4r33u19/moss15v2/.venv/bin/python -m audio_decision.bootstrap

# This controls only the new service, never the tunnel / TTS / ASR.
/home/c4r33u19/moss15v2/.venv/bin/python audio_decision/manage.py status
/home/c4r33u19/moss15v2/.venv/bin/python audio_decision/manage.py restart
```

Wait for graceful shutdown before starting again. Logs: `/mnt/nvme/robby-audio-decision/service.log`; PID: `service.pid`. `ROBBY_PYTHON` and `AUDIO_DECISION_ASSETS` override host paths; `AUDIO_DECISION_DEVICE` defaults to `cuda:0`. The proxy routes must already be installed in the running origin. Restarting the origin must preserve its existing environment; never reconstruct or publish secret environment values. The new service is process-managed, not installed as a boot-time systemd unit.

For a new machine install PyTorch/CUDA suited to its hardware, FastAPI, uvicorn, aiohttp, httpx, NumPy, SoundFile, Pydantic v2 and ffmpeg in a dedicated environment. The isolated installer intentionally assumes those existing host dependencies instead of mutating the live environment. Hugging Face remote code is used at the pinned, inspected revision; review it before changing revisions.

## Repeat the tests

```bash
/home/c4r33u19/moss15v2/.venv/bin/python -m unittest audio_decision.tests.test_core -v
# Run benchmarks only while the lab is idle, after offloading its resident model:
curl -X POST http://127.0.0.1:8815/internal/offload
PYTHONPATH=/mnt/nvme/robby-audio-decision/env:. /home/c4r33u19/moss15v2/.venv/bin/python -m audio_decision.benchmark
# Node + Playwright + Chrome; no API/model response mocks:
node audio_decision/tests/browser.cjs
node audio_decision/tests/full_live.cjs
/home/c4r33u19/moss15v2/.venv/bin/python audio_decision/tests/api_checks.py
```

Set `PLAYWRIGHT_MODULE` for a different Playwright installation and `AUDIO_DECISION_URL` for a different host in the main browser test. The deterministic fake microphone file is **authored input audio**, not fake model output. Browser tests use real HTTPS uploads, actual model inference and real WebSockets. `tests/make_fixture.py` recreates the beep fixture. Unit tests cover class/parameter validation, partial intervals, cache identity, causal smoothing, missing values and CSV semantics. `benchmark.py` stores every real class score and group timing, not only aggregates.

The optional `optimize.py` tests the official `model.compile()`. It produced `InternalTorchDynamoError` here and is not enabled. Do not upgrade the shared Torch installation to work around that. Benchmark this in a separate environment if pursuing it.

## Included and deferred

Implemented: upload/record/live, free context, both verified taxonomies, arbitrary class selection, both official question formats, history versus history+target, optional feedback, all selected class scores with explicit missing values, raw/causal EMA/hysteresis/events, synchronized Top-N/seek/roll, cache, JSON/CSV, bounded scheduling, timing and privacy controls.

Not implemented: MIDI export, foreground/proximity/dominance questions, empirical score calibration, a trained AudioSet time-localization head, acoustic hardware loopback latency measurement, robust source separation, or an accuracy claim over labeled AudioSet test recordings. These are not simulated in the UI.

## Attribution

AudioSet class-label lists: Google AudioSet, CC BY 4.0. Hierarchy/definitions: [audioset/ontology](https://github.com/audioset/ontology), CC BY-SA 4.0; redistributed ontology-derived metadata retains that license. The model has the [LFM Open License v1.0](https://huggingface.co/LiquidAI/d1-Omni-2B/blob/main/LICENSE), separate from this integration and its generated research results. Model weights and vendor inspection copies are not bundled with the source.
