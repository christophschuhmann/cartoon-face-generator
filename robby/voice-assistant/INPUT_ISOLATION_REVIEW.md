# Target-speaker filtering for Robby — November 11, 2026

**GPU follow-up (November 12):** [stateful CUDA streaming measurements and
reproducible adapters](INPUT_ISOLATION_GPU.md). Native VoxLock with CUDA Graphs
reaches ~3.55 ms per 40-ms chunk on RTX 3090; quality limitations remain.
The CPU-only status below describes the original experiment.

Status: source review and isolated CPU experiments only. Neither filter has
been inserted into the live microphone path. Robby's existing identity,
turn-taking, wake-word and echo-reference systems remain in use.

## Why this could help

An identity check after ASR cannot remove words already mixed into the ASR
input, and ordinary speech VAD will continue firing while a television talks.
A causal target-speaker filter before both VAD and ASR could address both
problems. It is complementary to identity management, not a replacement for it.
It cannot fix garbled TTS output; see [the separate repair](TURN_RELIABILITY.md).

## Official interfaces and constraints

| Candidate | Documented operation | Enrollment | Integration caveat |
| --- | --- | --- | --- |
| Alkove Focus preview | Native CPU or browser WASM; 16 kHz, 256-sample steps, 16-ms model delay; 1.1 MB weights | Closest voice without a print; a Timbre print selects one voice | Near-microphone use; explicitly unsuitable for microphones several metres away |
| VoxLock 1.3 | Python/ONNX CPU; causal state, 24-ms algorithmic delay; 40-ms or larger efficient chunks | `stream(sample)` uses at least three seconds of a selected voice | `live()` initially passes raw audio while enrolling; this can enroll a television |

Sources: [Focus](https://alkove.ai/docs/models/focus/),
[Alkove Python](https://alkove.ai/docs/start/python/),
[VoxLock](https://github.com/arbazsiddiqui/voxlock).
Both publish Apache-2.0 code/weights. Preserve their attribution notices.

Model delay is not complete end-to-end latency: chunk accumulation, processing,
queues and microphone/playback devices add time. A larger SDK may add its own
gate/lookahead. The low-level Processor/stream APIs fit our existing pipeline
better than adding a second end-of-turn decision engine.

The acoustic print formats are model-specific. An existing 192-dimensional
ECAPA embedding is not interchangeable with a 192-dimensional Timbre print.
Learn from a clean, verified current speaker; do not update from Robby's own
playback, uncertain overlap or an unattended loudest-voice guess.

## Reproducible local experiment

`benchmark_input_isolation.py` uses the existing public synthetic regression
fixtures: Christoph (`anime_088`), Selma (`emolia_c0542`), and a separate synthetic
weather-news voice (`mediathek_0184`). Enrollment uses a different introductory
utterance from the test utterance. No private microphone audio is used.

Each source is normalized to full-clip RMS 0.055. Trials use background gains
0, 0.5 and 1.0; these are full-clip level ratios, not calibrated perceived
foreground distance. The background starts one second before the target and
continues four seconds after it. This intentionally checks the difficult case
where background speech continues during the intended user's pause.

The host is an AMD Ryzen Threadripper 3960X with other services running. Filter
inference is CPU-only. The primary comparison uses one thread, 16-ms Focus
chunks and 40-ms int8 VoxLock chunks. Downloads and enrollment are excluded
from processing RTF and reported separately. RTF below 1 means faster than
real time; it is not a measured browser latency. Output length and finite
samples are checked, and both adapters flush their withheld tail.

```sh
cd robo-integration
uv run --no-project --with alkove==0.4.0 --with voxlock==1.3.0 \
  --python /path/to/robby/python benchmark_input_isolation.py
# Only after the above finishes, using the existing Parakeet v3 worker:
uv run --no-project --with alkove==0.4.0 --with voxlock==1.3.0 \
  --python /path/to/robby/python benchmark_input_isolation.py --asr
```

Results and authored audio: `logs/input-isolation/report.json` and WAVs beside
it. Package versions, model revisions, input hashes and timings are recorded.
`speed-probe.json` adds one-second VoxLock int8/FP32/thread/chunk probes; these
are short timing probes, not quality comparisons. `enrollment-check.json`
contains Timbre similarities only, never saved biometric vectors.

Parakeet v3 transcribes the whole scene, including the background-only tail.
Its WER against only the intended sentence therefore penalizes leaked
background words as insertions. It is a useful task metric, not conventional
single-speaker recognition WER. SI-SDR on the known target interval and
attenuation in the background-only tail provide additional diagnostics.
Neither metric alone proves that pauses or stop commands work in Robby.

## Measured results

| Filter/configuration | Processing RTF | Chunk p95 | Assessment on this host |
| --- | ---: | ---: | --- |
| Focus, one thread, 16-ms chunks | 0.524–0.731 | 11.5–14.6 ms | Faster than real time, but limited headroom on an active chunk |
| VoxLock int8, one thread, 40-ms chunks | 5.768–5.813 | 240–246 ms | Too slow for continuous input in this configuration |
| VoxLock int8, four threads, 40-ms chunks | 2.639 | 109 ms | One-second probe; still slower than real time |
| VoxLock FP32, one / four threads | 5.823 / 3.573 | 247 / 156 ms | One-second probes; neither reached real time |
| VoxLock int8, two threads, 80-ms chunks | 3.081 | 254 ms | One-second probe; larger buffering did not solve throughput |

Focus enrollment/stream setup took about 150–177 ms; VoxLock about 272–332 ms.
These are session costs, not costs per audio chunk. First nonempty output
required 32 ms of input for Focus and 40 ms for VoxLock with these chunk sizes,
before adding computation and downstream processing. Tests run faster than
wall-clock capture, so these are not measurements of microphone-to-ASR delay.

Clean speech was transcribed correctly for both synthetic voices, with and
without filtering. However, neither model reliably removed the competing
weather-news voice. Background-only attenuation was 0.15–9.42 dB for Focus and
−0.07–8.90 dB for VoxLock across the four mixed trials. Attenuation by itself
does not mean the ASR stops hearing the background.

The table below gives whole-scene ASR edit distance divided by the intended
sentence's word count. Values over 1 are possible because background words
are counted as insertions; this is NOT ordinary clean-speech WER.

| Synthetic target / background gain | Raw | Focus | VoxLock |
| --- | ---: | ---: | ---: |
| Christoph / 0.5 | 1.571 | 0.714 | 1.571 |
| Christoph / 1.0 | 1.571 | 1.714 | 1.143 |
| Selma / 0.5 | 3.167 | 3.167 | 2.500 |
| Selma / 1.0 | 3.000 | 1.833 | 2.667 |

For the harder Christoph mixture, Focus changed the intended final verb; in
the harder Selma mixture, it lost the beginning of the target question. This
is a reason to retain the raw branch and measure clean/quiet speech damage,
not to assume all suppression improves understanding.

Timbre's enrollment-to-target similarities were approximately 0.491 and 0.474;
enrollment-to-background was 0.232 and 0.379 respectively. Synthetic TTS voice
consistency and the small target/background margin for Selma limit conclusions.
These scores are not calibrated acceptance probabilities.

**Recommendation:** Focus is the practical first optional integration candidate
on this CPU because it kept up. Neither filter is justified as an unconditional
production default by this small experiment. VoxLock improved target SI-SDR
more in these mixtures, but needs a different/tuned runtime to meet the live
deadline here. Published speeds on other CPUs are not host measurements.
No browser-WASM speed or real-microphone robustness has been measured yet.

## Safe integration boundary

Keep two aligned branches from the same microphone packets:

1. Raw bounded audio for explicit sound questions, wake/handover detection and
   separately validated enrollment. Do not let this branch submit ordinary
   background conversation while a target is selected.
2. Target-filtered audio for neural speech VAD, conversational ASR and
   interruption decisions. Use the same timeline, accounting for the actual
   samples buffered by the filter and its measured processing delay.

Keep WebRTC echo cancellation and TYGER's playback reference. Suspend print
learning during robot playback. A filter reset or target switch must occur
at a controlled boundary. A new person needs the raw wake/handover path;
otherwise a correctly functioning filter would hide that person completely.

An initial optional server-side worker is easier to compare and instrument
than enabling an unmeasured browser model for all clients. CPU inference must
run off the asyncio/UI event loop, with bounded queues and explicit reporting
of overload/fallback. Browser WASM can be evaluated later on actual laptops
and phones. Never silently claim filtering is active while forwarding raw
audio after a load failure.

## Before making a filter the default

Test real German/English near-microphone voices, emotional pitch changes,
whispers, quiet syllables, same-gender overlap, music, reverb, wrong/dirty
enrollment and a deliberately louder TV. Measure target WER, background words,
missed short stop commands, premature submissions, response delay after a
target pause and false speaker switches. Keep a clean-speech baseline and
verify guest handover. Two synthetic speakers do not establish population
robustness or guarantee real-room behavior.
