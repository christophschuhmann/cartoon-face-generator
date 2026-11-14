# Optional CUDA microphone isolation

Robby now offers **Off**, **VoxLock**, and **Scicom Agent** under **Settings &
details → Speech recognition & quick replies → Microphone voice isolation**.
Both filters process 640 mono samples at 16 kHz: **40 ms per inference chunk**.
They use CUDA Graphs on physical GPU 1. Off remains the default.

Public page: https://diane-asylum-understood-invoice.trycloudflare.com/desk-robot/

## Using it

1. Choose a filter. The microphone stays unfiltered during loading.
2. Say “Hey Robbie” and continue speaking alone for about four seconds.
   Accepted speech builds a separate four-second reference for each matched
   person. A shorter introduction is completed by later matching speech; it
   is not padded or combined with another person. Alternatively press **Learn my voice** and speak
   alone for four seconds. This button starts microphone capture and stops
   Robby's current playback. Playback-tagged microphone blocks are excluded.
3. Wait for **ACTIVE**. The status shows reference length, GPU, measured last
   chunk compute time, buffered samples, and processed chunks in this session.
4. A new person can say **Hey Robby** to join automatically. Existing known
   people remain registered. **Allow another speaker** also allows enrollment;
   **Reset learned filter voices** clears the bank. **Talk without speaker
   filter** also switches this new audio isolation off.

See [automatic enrollment, multi-person behavior and limitations](ISOLATION_AUTO_ENROLLMENT.md).
The waveform bank supports four known people; independent identity admission
rejects unknown non-wake speech that leaks through the separator. This is
approximate speaker matching, not authentication or perfect sound removal.

Only the model choice persists in browser settings. Reference audio, the short
raw ring and learned voice keys are session RAM, never files or browser memory.
Disconnecting ends the GPU worker and discards its voice reference. Persistent
text memory does not acquire audio or voiceprints from this feature.

## Routing and timing

```text
Browser AudioWorklet (20 ms, original playback-position tags)
  ├── raw environmental-sound analysis and bounded 30-s reference ring
  └── optional CUDA child, 40 ms, fixed reference and recurrent state
        └── original sample positions / playback tags preserved
              └── neural VAD + Nemotron/TYGER + final Parakeet/selected ASR
                    └── existing identity / wake / interruption decisions
```

The worker removes causal left padding and retains the corresponding unfinished
tail: 24 ms for native VoxLock and 10 ms for Scicom. Original playback tags
travel with the samples, rather than being replaced by the time an IPC result
arrives. This keeps TYGER's second-ear reference aligned with the filtered
microphone. Switching flushes the retained tail and sub-40-ms fragment. A failed
worker releases unheard original samples and continues with raw input; it never
fills missing audio with fabricated silence. Already delivered audio is never
replayed. These transitions preserve the sample clock; waveform discontinuities
can still occur when a filter is bypassed.

Loading/enrollment run in background threads, outside the microphone event loop.
Each chunk has a bounded 250-ms worker deadline; a failure returns to raw input
with a visible error. No unlimited inference queue is introduced. Only one
filter worker owns GPU admission. It checks at least 4 GiB free VRAM before
starting and caps its PyTorch allocator at 16% of GPU capacity. This is not a
reservation against other processes; external contention can still cause a
fallback. Off/disconnect terminates only this owned child, releasing its graphs
and CUDA context. Robby and the podcast service are not restarted by selection.

## Measured integration performance

RTX 3090, CUDA 12.4 / PyTorch 2.6, November 12, 2026. A paced 20-ms synthetic
microphone feeds the real controller, local IPC worker and CUDA model; Parakeet
then recognizes the result. Measurements include process/IPC overhead, but not
browser hardware capture, network, endpointing or LLM/TTS latency.

| Filter | Setup including reference | First forwarded audio | 20-ms packet handler p95 | Last GPU-worker chunk compute | Final transcript |
| --- | ---: | ---: | ---: | ---: | --- |
| VoxLock native FP32 CUDA Graphs | 15.65 s | 49.57 ms | 6.86 ms | 4.16 ms | Correct complete German sentence |
| Scicom Agent mixed FP16/FP32 CUDA Graphs | 37.33 s | 56.22 ms | 11.86 ms | 9.03 ms | Correct complete German sentence |

Initialization costs are paid on selection, not per chunk. Each replay submitted
77,280 samples and recovered exactly 77,280 on switching Off. Environmental
analysis received the same number of original samples. These are small tests,
not latency guarantees under arbitrary GPU contention.

The public HTTPS Chrome test also passed: a fake microphone went through the
actual AudioWorklet/WebSocket, both CUDA choices became active, German speech
was recognized, real LLM/TTS audio reached the player, clear returned to raw
input, and Off persisted. No JavaScript or server-reported errors occurred.
There was no physical-microphone/room test.

**Additional stress-test failure:** a separate synthetic 120-ms delayed bot-echo
case (gain .05), with a long typed response and spoken Stop, hit the existing
ASR five-second backlog limit (`audio_too_fast`). It failed both with VoxLock and
with isolation Off. The filter computes in milliseconds, but cannot guarantee
that the downstream ASR/TTS workload keeps up. This comparison does not establish
reliable echo-room barge-in and must not be reported as a passing interruption
test. The ordinary browser selector/conversation test above passed separately.
See `logs/input-isolation-stop-browser.json` (first VoxLock attempt) and
`logs/input-isolation-stop-off.json` (same test with raw audio). The independent
Scicom run also missed Stop, with a final-ASR backlog of about 4.23 s and bot echo
in the preview (`logs/input-isolation-stop-scicom.json`); its cancellation in the
log was the test's manual cleanup, not successful acoustic interruption.

## Quality limitations

Use a clean reference of the **human input speaker**, not Robby's TTS voice.
The manual reference meter checks duration and audible energy; it does not prove
that exactly one person spoke. Automatic enrollment requires an accepted
identity and excludes playback-tagged audio, but background mixtures can still
contaminate a reference. Neither filter guarantees preservation of every word.

Earlier synthetic mixture tests found competing TV leakage with VoxLock and
occasional suppression of the target with Scicom. Try VoxLock first; switch Off
if desired speech disappears. New speakers and brief interruptions may be
suppressed while an old reference is active. Raw fallback handles computational
failure, not semantic mistakes by a healthy model. The raw environmental branch
is intentionally independent: enabled proactive sound responses still follow
their existing settings. See [quality comparisons and pinned sources](INPUT_ISOLATION_GPU.md).

## Reproduce and maintain

Use the existing Robby Python environment; do not replace its CUDA packages.
Bootstrap pinned source/weights with `prepare_input_isolation_gpu.py` and the
optional isolated dependencies listed in [the benchmark guide](INPUT_ISOLATION_GPU.md#reproduce).
Runtime never downloads models and requires no credentials. Files live under
`~/.cache/robby-input-isolation`; no new large copy is kept on the small NVMe.
`ROBO_ISOLATION_GPU` defaults to physical `1`. It must have enough spare memory.
Scicom weights declare a nonstandard license, not Apache-2.0; keep source and
weight terms separate from this integration's code.

```sh
cd robo-integration
python -m unittest test_input_isolation test_sentence_reliability test_stop_commands test_stop_feedback
python test_input_isolation_cuda.py
uv run --no-project --with playwright --python /path/to/robby/python browser_input_isolation.py
```

Receipts: `logs/input-isolation-ui-cuda.json`,
`logs/input-isolation-ui-browser.json`, `logs/input-isolation-controls.png`.
The unit tests explicitly use a fake worker for sample-clock and failure cases;
CUDA/browser tests use real weights. Preserve this distinction in reports.

Modules: `input_isolation.py` (routing/reference/clock),
`input_isolation_process.py` (single-owner admission and IPC),
`input_isolation_worker.py` (CUDA child), `input_isolation_models.py` (shared
benchmark/production adapters). Hooks: `server.py`, `sentence_session.py`;
controls: `static/input-isolation-controls.js`, `static/index.html`, `static/ui.js`.
No second tunnel or separate public worker endpoint is needed.

Restart with the existing Robby launcher and environment (`manage.py stop` /
`manage.py start`). Keep `ROBO_SENTENCE_STREAM=1` and existing director/TTS settings;
`ROBO_ISOLATION_GPU=1` is optional because it is already the default. Do not stop
the podcast or TTS services when changing this selector.
