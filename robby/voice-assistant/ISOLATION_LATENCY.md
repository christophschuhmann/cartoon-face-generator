# Robby latency with microphone isolation — 12 November 2026

This update retains the current Small 1.1 Alpha RL checkpoint, Mira reference,
temperature 0.8, CFG 2, voice isolation choices, raw-audio speaker admission,
neural speech-pause checks, and verified TTS start/end boundaries. It does not
speed up playback, discard words, relax speaker thresholds or bypass the output
word check. The podcast service and existing Cloudflare tunnel stay running.

## Changes and reasons

1. **Final ASR:** Moondream Parakeet Ultra is now the default on GPU 1, using
   Photon native CUDA graphs. Redux is selectable as a CPU comparison; original
   Parakeet v3 and other choices remain available. The unchanged Nemotron/TYGER
   pipeline still supplies streaming previews and turn/interrupt features.
2. **No preview backlog before finalization:** a bounded 30-second ring retains
   the PCM already delivered by the microphone/isolation pipeline. An independent
   final recognizer can analyze this complete audio after the neural speech pause,
   even if TYGER feature processing is behind. Resumed speech invalidates an
   in-flight final check. Missing audio falls back to the old complete-buffer path.
   Committed sample boundaries also reject obsolete partials and barge-in probes.
3. **Speaker work overlaps ASR:** compute the 3.04-second identity reference from
   original microphone audio, not target-conditioned filter output. Reuse is
   allowed only for an exact waveform hash and matching turn epoch. A private
   GPU worker now runs the same pinned ECAPA in FP32; its CPU fallback remains.
   Thresholds and identity rules are unchanged. Names and voiceprints are not
   sent to external APIs by this worker and are never logged or saved here.
4. **Verified TTS boundary ASR:** Ultra on GPU 1 performs the real target-word
   checks; HTTP failure or malformed output falls back to resident original v3.
   Persistent loopback connections avoid per-scan client initialization. The
   strict first-word checks and 100-ms fades remain. Single live output skips
   unused reference-preview MP3 encoding and ranking-only preparation.
5. **Playback reserve:** a first PCM buffer of at least 800 ms now gets a 180-ms
   scheduling reserve. Smaller first buffers retain 300–350 ms (at least 220 ms
   for a quick reply). Old network gaps no longer leave a permanent 650-ms reserve on every
   later response. Actual browser scheduling adds a little overhead.
6. **Warm both common TTS contexts:** a long story triggered a previously unwarmed
   1024-position semantic CUDA bank and delayed first PCM by 71.75 seconds.
   `SmallEngine.warm_live_stream` now prepares the short and long context before
   service readiness. The current live process has both banks captured already.
   This moves work to startup; it does not make compilation free. Unusual batch,
   CFG or longer context shapes may still need their own warm-up.
7. **Short continuation after rejected background speech:** the faster pause
   path exposed a case where a 1.4-second TV sentence tail falsely matched an
   enrolled speaker after the preceding five seconds were correctly rejected.
   For a non-wake continuation shorter than two seconds, within one second of
   rejected speech, identity now uses up to four seconds of adjacent original
   PCM. A wake phrase, longer new utterance, larger gap or reset bypasses this
   extension. This is conservative temporal evidence, not a threshold change;
   a known person speaking very briefly immediately after an unknown voice may
   still need to say Hey Robby. The transcript itself is never extended/replayed.

## Controlled TTS comparison

Two RTX 3090 24-GB cards, driver 550.54.15. Production TTS remains on Torch
2.6.0+cu124. Same three seeds (777–779), prompt, reference, temperature, CFG and
20-frame requested chunk size before/after; the existing 3→6→12→20 frame ramp
is unchanged. No concurrent browser benchmark. Timings include local transport.

| Metric | Before | After |
|---|---:|---:|
| First PCM with word verification, median | 1,213 ms | **925 ms** |
| First verified PCM, all three runs | 1,213 / 1,211 / 1,286 ms | 918 / 952 / 925 ms |
| Whole verified short utterance, median | 2,548 ms | **1,833 ms** |
| First raw PCM, no word gate, median (diagnostic only) | 416 ms | 370 ms |

The unverified diagnostic is not the live default. Old reports of ~78 ms used
an early-release path before strict opening-word confirmation (the old request
still had alignment enabled). The reference was already about 10 seconds; its
length alone does not explain the regression. These are warm measurements, not
startup. See [parallel verification](PARALLEL_TTS_VERIFICATION.md) for the newer
producer/consumer implementation, controlled timings and prefill profiling.

## ASR and speaker measurements

`benchmark_photon_asr.py` uses two authored German voices, clean and with an
independent quieter TV voice. Excluding each first inference, warm medians were
Ultra CUDA **171.8 ms**, Redux CUDA **188.3 ms**, and Redux CPU **1,656.7 ms**.
Ultra had zero word errors on these small fixtures; Redux had mean WER 0.333,
including a compound-word difference and one leaked background sentence. This
is a small smoke comparison, not a general language/noise benchmark. Ultra is
therefore the measured choice here, not an assumption that Redux is always better.

For four synthetic voice clips the GPU and CPU FP32 ECAPA vectors had cosine
similarity 1.0 to reported precision and maximum coordinate error below 1.1e-6.
Warm CPU calls were 319–351 ms; GPU HTTP calls were 48–120 ms, including initial
shape overhead. Prefetch often reduces the remaining foreground speaker wait to
7–18 ms. These values are compute/overlap measurements, not identity accuracy.

## Real browser tests and limits

`browser_isolation_latency.py` runs Chrome over the actual public HTTPS URL,
feeds authored synthetic audio through a real MediaStream and AudioWorklet,
and uses actual isolation, ASR, speaker recognition, API LLM, TTS and playback
scheduling. It checks the complete introduction and first audio of a follow-up;
it does not by itself prove completion of a long follow-up story. The separate
`browser_isolation_enrollment.py` covers full replies, two registered people,
known-person return and rejection of an unknown non-wake TV voice.

The first post-update VoxLock full conversation passed. The first Scicom run
registered both people and recognized their return, but failed on that short TV
tail and also reported a sentence rejected by TTS after three attempts. Its
negative receipt is retained at
`logs/isolation-enrollment-browser-scicom-latency-final.json`; do not describe it
as a pass. The continuation repair is tested separately and does not claim to
fix every synthesis/ASR-verification failure.

After the continuation fix, the full public Scicom test passed with real model
outputs, both people retained, known-person return, unknown TV rejected and no
browser or speech error. Receipt:
`logs/isolation-enrollment-browser-scicom-context-final.json`. Its two-reference
filter reported 12.23 ms compute per 40-ms block at the end of the test. This
is a last observed block, not a whole-run percentile.

Final warm public VoxLock run (`browser-warm-recheck-voxlock.json`), with the
complete introduction and first follow-up audio checked:

| Component | Introduction | Follow-up question |
|---|---:|---:|
| Neural quiet time at submission | 320 ms | 312 ms |
| Final ASR | 222 ms | 185 ms |
| Foreground speaker wait | 13 ms | 5 ms |
| Background speaker work (overlapping) | 64 ms | 56 ms |
| API LLM first sentence | 701 ms | 865 ms |
| Verified TTS first PCM | 1,016 ms | 639 ms |
| Reply request → first PCM | 1,729 ms | 1,509 ms |
| Browser playback lead | 195 ms | 365 ms |
| Fixture speech end → scheduled browser output | **2,234 ms** | **2,240 ms** |

The earlier browser baseline on the same input fixtures was 4,953/6,834 ms, but
the generated responses and API delays differed: this is not an isolated causal
TTS speed comparison. Use the fixed-prompt three-seed table for that comparison.
One preceding `browser-warm-final-voxlock.json` run failed on an external LLM
planning/request error before follow-up audio; it is retained. The recheck passed.

Measured browser first TTS PCM ranged from 618–1,129 ms across different
sentences with filtering active; the detected compilation outlier was 71.75 s.
Do not remove that outlier from a claimed pre-warm reliability distribution.
The API LLM also varied from 555 to 2,999 ms before its first sentence. Individual
rows are in the JSON receipts, including failed/intermediate experiments.
Playback lead was 195 ms for long first buffers and 315–365 ms for short buffers.
ASR was typically 208–265 ms. Speech-end to scheduled audio is not equivalent to
TTS latency and can remain several seconds when the LLM is slow.

The speaker-prefetch metric is background work; the main speaker card shows the
remaining wait. Stages overlap and must not be summed. Browser playback lead is
scheduled Web Audio time, not physically measured loudspeaker/DAC latency.
Camera rendering, real-room echo, accented real users and flaky Wi-Fi were not
covered by these synthetic-media tests. Previous physical echo/short-stop stress
limitations are not declared fixed by this performance update. Isolation can
still suppress a word or leak an unknown speaker; retain the original-audio
admission gate. Generated TTS can still fail verification and use bounded retries.

## Reproduce

Read [PHOTON_ASR.md](PHOTON_ASR.md) for pinned models, environment and service
restart. Do not change the shared production Torch/CUDA stack. Run only one
browser/GPU benchmark at a time and keep other workloads identical.

```bash
# From robo-integration, with the production Python environment activated:
python benchmark_isolation_latency.py --label my-run
SMALL_BOUNDARY_ASR_URL=http://127.0.0.1:8822 python verify_boundary_audio.py
BENCH_LABEL=my-run uv run --no-project --with playwright --python "$VIRTUAL_ENV/bin/python" browser_isolation_latency.py
BENCH_LABEL=my-run ROBBY_FILTER_MODEL=voxlock uv run --no-project --with playwright --python "$VIRTUAL_ENV/bin/python" browser_isolation_enrollment.py
BENCH_LABEL=my-run ROBBY_FILTER_MODEL=scicom uv run --no-project --with playwright --python "$VIRTUAL_ENV/bin/python" browser_isolation_enrollment.py
python -m unittest test_input_isolation test_isolation_enrollment test_sentence_reliability test_stop_commands test_stop_feedback test_wake_mode test_open_speakers test_speaker_management test_pause_endpoint test_gpu_guard test_conversation_focus test_speaker_teacher test_speaker_names test_asr_choice test_asr_priority -q
```

The 159 targeted unit tests passed. They include resumed speech invalidating a
final result, missing audio refusing premature finalization, exact original-PCM
speaker reuse, rejection of changed/filtered voice evidence, and GPU-worker
failure/revision validation with CPU fallback. The boundary suite passed 21
tests; a real injected unwanted leading/trailing utterance was cut with both
target boundaries verified. Exported synthetic test receipts are under
`logs/isolation-latency/` and `logs/streaming-boundaries/`.

Relevant files: `photon_asr_worker.py`, `prepare_photon_models.py`,
`start_photon_asr.sh`, `asr_catalog.py`, `asr_choice.py`, `asr_model_worker.py`,
`prepare_asr_models.py`, `server.py`, `sentence_session.py`, `speaker_teacher.py`,
`ecapa_gpu_worker.py`, `start_ecapa_gpu.sh`, `static/asr-controls.js`,
`static/client.js`, `static/index.html`; sibling TTS `small_app.py`,
`streaming_boundaries.py`, `engine.py`, and `rtx3090-speed.env`.
