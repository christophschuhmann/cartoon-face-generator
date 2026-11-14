# Causal best-of-three streaming for Robby

The optional **Speed & verification → Best-of-3 streaming** checkbox makes
Small 1.1 Alpha RL generate three continuations in one GPU batch. It evaluates
each continuation after 12 semantic frames (960 ms of generated audio), keeps
one winner, and forks that winner into three new continuations. It does not
generate three complete sentences first. Settings persist in the browser.

## What is copied, and what is played

The winning conditional and unconditional semantic KV caches, input token,
attention masks, acoustic tokens, completion flags and stateful audio decoder
state are copied together. CUDA-graph cache addresses remain stable; duplicate
rows have separate mutable storage. Random sampling continues independently.
Only the winning prefix is played. Already played audio is never revised.

The dedicated three/four-row codec banks also replay CUDA graphs. Winner forks
copy decoder tensors in place, preserving graph addresses and shared execution
masks. `verify_search_codec_graph.py` compares actual eager and graphed BF16
outputs through forks, short/padded chunks and resets. All 24 tested chunks were
bit-identical; warm 12-frame codec decoding fell from about 400 to 20 ms on this
RTX 3090. That is a codec-only improvement, not a 20× whole-pipeline claim.
The optimized single-candidate Triton token kernel remains specific to N=1;
three-way token prediction uses the existing batched CUDA-graph fallback.

Startup still warms normal streaming. The optional quick-reaction continuous
batch warmup is now opt-in (`SMALL_WARM_CONTINUOUS=1`), because it can delay the
whole service for minutes even when quick reactions are disabled. That feature
still initializes on first use. New candidate shapes also require a cold first
request; prewarm before a demonstration. Do not confuse audio chunk duration
with wall-clock latency.

The normal single-stream mode remains available. Large, quick reactions and
optional idle speech keep their existing paths. This experiment is off by
default. Three-way selection may increase first-audio latency and cannot
guarantee correct words, naturalness or voice similarity.

## ASR selection

The private Photon/Parakeet Ultra worker recognizes the three candidate prefixes
as a batch. Resident Parakeet v3 is a fallback. No quality, emotion or VoiceCLAP
model is called by this mode. Normalized word edit alignment is compared to the
expected text prefix; incomplete future words are not counted as deletions.
Finished candidates are compared against the complete text. The ranking is:

```
(number of ordered matched words − 2 × edit errors) / target word count
```

Pure inverse WER can prefer an empty or stalled continuation. This score rewards
actual text progress and penalizes substitutions, insertions and deletions.
It is a search heuristic, not a calibrated quality estimate. A 100-ms unstable
word tail is excluded until more audio arrives. ASR uses at most approximately
12 seconds of recent audio plus a three-word overlap, capped at 27 seconds.
Older winner words are retained through an exact two/three-word overlap and
timestamp-consistency check. Timestamp-only joins lost words in the initial
long-text experiment; those initial results remain recorded for comparison.

When edge trimming is enabled, the **same** ASR timestamps identify the opening
and ending and apply 100-ms fades. There is no second output ASR pass. Missing
opening evidence is bounded to 3.84 seconds of generated audio. An ASR mistake
can still select or reject the wrong candidate. Long rolling-window alignment
and short clipped words need particular care.

## Recovery and interruptions

- A transient failed candidate ASR batch is tried once again.
- An unrecognized opening or empty TTS result can trigger up to three sentence
  attempts with new seeds and progressively simpler acting instructions.
- A CUDA OOM before any published audio switches a search request to one stream
  for its single OOM retry. Persistent OOMs are surfaced rather than looped.
- Once audio has been published, the sentence is never automatically restarted:
  that would replay words the listener has already heard.
- Ambiguous midstream transport loss and cancellation are not blindly retried.
- Cancellation is checked at every generated 80-ms frame and before each ASR
  batch and output commit; a running GPU/HTTP operation must finish first.
- Non-streaming conversation planning retries a transient transport/server
  failure once. Authentication and arbitrary invalid-request errors are not
  retried. Provider rate-limit delays remain bounded.

## Reproduce

Use the pinned TTS runtime documented in `tts-runtime/README.md` in the exported
repository; the local deployment has `../humaneness-small` at that relative
path. Keep the existing private ASR worker on port 8822 and TTS on 8792. One
worker owns TTS GPU state; do not run concurrent benchmark clients.

```
python candidate_search_benchmark.py --label final-cold --modes search_asr --prompts de --seeds 777
python candidate_search_benchmark.py --label graph-warm --prompts de en negation long --seeds 777 778 779
python candidate_search_report.py final-cold graph-warm
python candidate_search_cancel_check.py
# In a Python environment with Playwright and system Google Chrome:
python browser_candidate_search_check.py
python build_candidate_search_report.py
```

Cold graph capture/compilation must be reported separately. The benchmark saves
only authored test utterances and actual SSE events in `logs/candidate-search`.
It measures HTTP request to first PCM, completion wall time, emitted duration,
real-time factor and each selection's TTS/codec and ASR time. These exclude the
LLM, browser device latency and microphone. Using selection ASR to check final
transcripts is not an independent evaluation of perceived audio quality.

Relevant sources: `verification_settings.py`, `bolt_pipeline.py`,
`speech_retry.py`, `static/verification-controls.js`; TTS `beam_search.py`,
`asr_chunk_search.py`, `search_codec_graph.py`, `small_app.py`. Unit tests include alignment, negation,
independent codec copies, timestamp fades, bounded missing openings, API shape
validation, request propagation, OOM fallback and refusal to replay spoken
audio. The browser test exercises the public page and real sentence pipeline.

## Measured result — 14 November 2026

Two RTX 3090 24-GiB cards: TTS GPU 0, private Photon/Parakeet Ultra on GPU 1.
Same fixed Mira reference, temperature 0.8, CFG 2, four authored prompts
(German, English, German negation and a longer English explanation), three
seeds per mode. Warm results below exclude model loading and graph setup.
There were no concurrent unit tests in this final measurement.

| Mode | Median request → first PCM (s) | Median wall RTF | Mean final ASR WER | Completed |
|---|---:|---:|---:|---:|
| single | 0.673 | 0.259 | 4.17% | 12/12 |
| search_asr | 0.867 | 0.558 | 1.19% | 12/12 |

This is local HTTP timing for TTS plus its ASR selection/checking, not full
microphone → LLM → audible-playback latency. All final cases had zero simulated
playback underrun even without initial reserve. The browser adds its normal
playback reserve. Twelve cases per arm and the same ASR family for selection
and evaluation do not establish broad quality or reliability guarantees. One
single-stream English case emitted only a verified prefix; search emitted
complete target endings in all twelve final cases. Search still had two
one-word deviations in a separate final transcription by the same ASR model.

Before batched codec graphs, the search median wall RTF was 0.982. The final
optimized median is shown above. Warm 12-frame codec decoding alone fell from
about 400 ms to 20 ms with bit-identical results in 24 synthetic-token chunks.
A complete authored German search output was also identical across the codec
change. These checks do not imply every stochastic generation is identical.

The first new six-row semantic graph required roughly 7.7 minutes before first
PCM; subsequent service restarts with disk caches still incurred roughly
1.5–1.7 minutes for the first search request. This includes initialization and
new codec graph capture, not normal warm inference. Normal service startup
has separate warmup costs. Prewarm before presenting the demo.

Reproducible data and an English report are in
[static/candidate-search-results.json](static/candidate-search-results.json) and
[static/candidate-search.html](static/candidate-search.html). Public demo:
https://diane-asylum-understood-invoice.trycloudflare.com/desk-robot/

Next bottlenecks are the multi-row local token decoder (the specialized Triton
shortcut currently supports only one candidate), repeated ASR encoding of the
shared prefix, and semantic prefill. Shorter anchored ASR windows or a verified
shared-prefix recognizer could help, but require a new accuracy comparison.
No untested token-kernel or prefill optimization was enabled.

The final public Playwright run passed both modes and persisted the toggle. Its
search reply reached first PCM at 1.473 s including the actual Qwen call
(TTS component 0.798 s). The following single-stream turn encountered a real
provider rate limit and one unrecognized-opening TTS attempt; both bounded
retries succeeded, at 10.506 s to first PCM. This shows why warm TTS timings
are not an end-to-end latency guarantee. A separate warmed search cancellation
returned the service to idle 135 ms after HTTP disconnect (not spoken Stop
recognition latency). No physical microphone/room test is claimed.
