# Parallel verification of streamed TTS — 13 November 2026

Robby still sends each completed LLM sentence to TTS immediately. The TTS model
then generates **incremental PCM inside that sentence**. It does not first render
the whole sentence. The default Small 1.1 Alpha RL model, Mira reference,
temperature 0.8 and CFG 2 are unchanged. The requested 1.6-second maximum chunk
uses the existing 3 → 6 → 12 → 20 semantic-frame ramp (240/480/960/1,600 ms of
*audio*, not processing time).

## What changed

`ParallelBoundaryStream` separates generation from word verification. A single
producer owns TTS CUDA state on GPU 0 and appends PCM to a bounded RAM queue. A
single consumer sends the accumulated audio to the already resident Parakeet
Ultra on GPU 1. The producer does not wait for those ASR requests. There is only
one outstanding verification request per utterance; intermediate pending checks
are coalesced rather than queued indefinitely.

The first two target words must actually be recognized (one for a one-word
utterance). Forced alignment cannot manufacture evidence. Then matching proceeds
in target order, preserving negations and repeated phrases. Contractions,
numbers and punctuation use the existing normalization. One weak `-en` ending
inside a phrase can match its stem only with two exact words on either side;
opening and final words cannot use that exception. For example, ASR sometimes
writes `summ` for spoken `summen`. This is a deliberately narrow acoustic/ASR
tolerance, not an edit-distance permission to skip a missing middle word.

The first regular check waits for at least 1.0 s of **generated audio**. With the
current chunk ramp that normally means 1.68 s; generation itself is much faster
than playback. This avoids a frequently unsuccessful 720-ms ASR call that has
only heard the first target word. Short utterances are checked immediately when
the producer finishes. The API can compare `verification_start_seconds: 0.6`
against `1.0`; accepted range is 0.4–1.8. Subsequent checks use at least 800 ms of
new generated audio, and coalesce when ASR is slower than the producer.

Each check sees at most 12 s of audio, retaining overlap before the last confirmed
word and merging timestamps in the original sample coordinate system. Window
boundaries use an exact two/three-word overlap inside the previously confirmed
prefix, with an absolute-time consistency check. Timestamp-only concatenation
proved insufficient: a cropped word could disappear between decodes. The overlap
anchor retains already verified words but cannot skip an unverified middle. No gap in
unverified middle speech may be skipped to catch up. Only audio supported by the
recognized target prefix is released. A 100-ms fade-in removes unwanted leading
speech; after the confirmed final word, 60 ms of margin and a 100-ms fade-out are
retained. Unknown trailing audio is withheld. The consumer can stop further TTS
production, although already generated extra frames cannot be undone.

The producer/consumer queue is limited to 70 s of PCM, and cancellation discards
pending/late results. Audio/transcripts remain in request RAM. HTTP errors fail
closed; resident Parakeet v3 may retry only after generation has stopped, avoiding
a second GPU-0 model launch during a possible TTS CUDA graph capture. Silence is
not affirmative evidence. If no opening is confirmed, no raw fallback is played;
Robby's existing bounded regeneration policy remains available. If only a prefix
is confirmed, the final report explicitly marks incomplete verification and the
unsupported tail is withheld. ASR is fallible, so this can also reject valid speech.

## Additional speed work and rejected candidate

The codec's **existing reset operations** are now captured as a CUDA graph. This
removes per-request Python/kernel-launch overhead without rewriting the reset
semantics. An isolated real-codec check over two deterministic token sequences,
repeated after different prior states, found bit-identical PCM in all eight runs.
Warm reset time was about 89 → 4.5 ms. Compilation/capture occurs during warmup.
The test used synthetic token arrays solely to test state equivalence, not to
claim intelligible speech or perceptual quality.

Profiling also found about 193–200 ms in eager semantic prefilling. Only about
20 ms was actual GPU kernel execution; roughly 2,079 kernel launches and Python
work explain much of the remaining time. A bounded padded-prefill CUDA-graph
experiment reduced warm prefill to 17–35 ms. However, left-padding changes BF16
rounding and sampled tokens. Across nine authored German/English utterances per
arm, mean Ultra WER was 0% eager versus 2.02% graphed, with two one-word deviations
in the latter. This tiny test does not establish a general quality difference,
but it is insufficient to enable the change as a transparent speedup.
**`HVS_PREFILL_GRAPH=0` stays the production default.** Experimental implementation
and measurement code are retained for future evaluation. No driver/Torch upgrade,
reference shortening, speaker-threshold relaxation or playback acceleration was used.

An initial isolated codec-loader experiment ran out of VRAM after using the
incorrect generic dtype option. It terminated without restarting any live
service. The corrected test uses the codec's documented-in-code
`codec_weight_dtype='bf16'`, bounds its allocator to 23% of GPU 1, and checks free
memory. Retain the negative log. The podcast worker may occupy GPU 1 and must not
be stopped to improve benchmark numbers.

## Measurements and tests

Controlled warm medians (three seeds per condition) in the same warmed TTS
process, before the final overlap-only correction:

| Current authored German prompt | First PCM | Full request |
|---|---:|---:|
| Serial ASR + accelerated reset, same process | 877 ms | 1,898 ms |
| Parallel ASR, first scan after >=1.0 s generated | **684 ms** | **1,414 ms** |
| Parallel ASR, first scan after >=0.6 s generated | 775 ms | 1,196 ms |
| Unverified diagnostic | 275 ms | 779 ms |

The second/original prompt measured 864 → 675 ms first verified PCM and
1,909 → 1,395 ms full request for serial versus parallel in the same process.
All six default-parallel runs confirmed the complete target and had zero
simulated playback gaps. The 0.6-s variant finished sooner in this run but
started later; the 1.0-s default prioritizes audible response latency. Active
podcast jobs on GPU1 changed ASR timings during the experiment; this is a small
shared-host test, not a clean universal throughput guarantee. Previous serial
measurements before the restart were 870/855 ms first PCM for the two prompts.

After deploying the final overlap correction, all six short runs again passed:
current/original prompt medians were **689/634 ms first verified PCM** and
**1,241/1,152 ms full request**, with zero simulated gaps. This separate
post-restart validation is not a same-process speed comparison against serial.
The 45-word English case passed with all 45 words confirmed: 15.6 s of output,
744 ms first PCM, 2,911 ms full request, six real ASR calls and five overlap
anchors. Its request-wall/audio ratio is 0.187; this includes concurrent ASR and
HTTP, and is **not** a pure device RTF. It is one long-form test case.

The final raw first block is still ~259–275 ms, not the historical ~78 ms.
Most of that remaining cost is eager semantic prefilling. Its padded-graph
prototype is deliberately not enabled as an invisible arithmetic change.

44 targeted unit tests passed. All five real-ASR edge fixtures passed, including
weak-ending recovery. A real verified streaming request was canceled after its
first audio: the TTS ownership lock was released in **271 ms** in the final
deployment (213 ms in the earlier run). Retain the earlier
first-pass receipt: one original-prompt run truncated at `summ` before the
context-supported ending fix; its old `passed` flag tested audio delivery only.
The benchmark now separately requires `complete_target_verified`.

The readable public report is `static/parallel-tts-verification.html`. Raw local
receipts are under `logs/isolation-latency/`. Read first-PCM latency separately
from full synthesis time, device RTF, and speech-end-to-browser-output latency.
CUDA event spans include GPU idle gaps between Python launches. Parallel ASR time
and TTS time overlap and must not be summed.

The historical November 3 result around 78–101 ms allowed early output before
strict opening-word confirmation. Its request still had `align: true`; it was
not an entirely alignment-free pipeline. The reference was already about 10 s.
Today's strict gate adds a real recognition dependency. A raw PCM timing must
not be presented as verified speech latency, and longer references alone do not
explain the regression.

Tests include blocked ASR while the producer advances, cancellation during ASR,
wrong opening speech, missing negation, repeated phrases, bounded errors/audio,
weak-ending limits, and overlapping windows over a 28-s utterance. Scripted
readers exist only in unit tests. The real injected-audio probe uses actual Ultra
recognition with unrelated lead/tail speech, wrong-only speech and silence;
its producer cadence is simulated and is not a TTS throughput benchmark.

The optimized path applies to ordinary single-take streaming `/api/turn`, used
by Robby with the default quick-reply setting off. The optional continuous
multi-utterance bridge scheduler and candidate search retain their separate
existing batched/serial verification paths. Offline best-of-N is unchanged.

## Reproduce

Run GPU benchmarks sequentially. Use only authored test fixtures, never private
microphone recordings. The production Python is
`/home/c4r33u19/moss15v2/.venv/bin/python`. From `robo-integration`:

```bash
python parallel_verification_benchmark.py --label my-run
python parallel_verification_benchmark.py --label early-scan --modes parallel --first-scan 0.6
SMALL_BOUNDARY_ASR_URL=http://127.0.0.1:8822 python verify_parallel_boundary_audio.py
BENCH_LABEL=parallel ROBBY_FILTER_MODEL=voxlock uv run --no-project --with playwright --python "$VIRTUAL_ENV/bin/python" browser_isolation_latency.py
```

From sibling `humaneness-small`:

```bash
python -m pytest -q tests/test_parallel_boundaries.py tests/test_streaming_boundaries.py
```

`profile_parallel_prefill.py`, `compare_prefill_graph.py`,
`verify_prefill_quality.py`, and `verify_codec_reset_graph.py` reproduce the
isolated experiments. They require free GPU-1 capacity; do not run them during
another measurement. Their temporary authored WAVs are under
`/tmp/robby-prefill-graph`; measured receipts are retained in the project.

## Configuration and restart

- Keep the existing Cloudflare tunnel and Robby server on 8793.
- TTS 8792: start from `humaneness-small` with `start_rtx3090_tts.sh` and the
  prepared production Python (`ROBBY_TTS_PYTHON`). Check `.runtime/tts.json`
  against the actual process before stopping anything; never launch a duplicate.
- The script reads `rtx3090-speed.env` and the private GPU layout file. Flags:
  `HVS_CODEC_RESET_GRAPH=1`, `HVS_PREFILL_GRAPH=0`,
  `SMALL_BOUNDARY_ASR_URL=http://127.0.0.1:8822`.
- Wait for `/api/state` to report ready before a speech test. Warmup can take
  several minutes and prepares both normal 512/1024 semantic banks.
- Private Photon/ECAPA restart instructions are in `PHOTON_ASR.md`. Keep
  Photon on its separate Torch environment and loopback-only port 8822.
- API rollback for a diagnostic comparison: `speech_verification: "serial"`.
  `align: false` is an unverified diagnostic, not the production default.
- To disable only the reset optimization, set `HVS_CODEC_RESET_GRAPH=0` and
  restart the idle TTS worker. No weights or stored reference profiles change.

Main runtime files: `humaneness-small/parallel_boundaries.py`,
`streaming_boundaries.py`, `small_app.py`, `codec_reset_graph.py`,
`performance_core.py`, `engine.py`, `rtx3090-speed.env`. The optional prefill
experiment adds `prefill_graph.py` and a guarded hook in `semantic_graph.py`.


### Final validation and retained failures

The final public two-turn latency probe with VoxLock passed: TTS first PCM
694/909 ms, ASR final 188/193 ms, foreground speaker wait 6/5 ms,
reply-request to PCM 1,261/1,279 ms, browser scheduling reserve 195 ms.
Receipt: `browser-deployed-final-voxlock.json`. The earlier two-turn run had
TTS first PCM 722/757 ms. These different generated replies are not fixed-output
benchmarks. The probe checks full introduction playback and the first streamed
follow-up chunk; it does not establish full completion of an arbitrarily long
conversation. The introduction's intended transcript was finalized before the
fixture file ended. Its file-end delta is therefore **not a valid claim of
near-zero speech-end-to-audio latency**; only the directly measured component
latencies are reported here. These are synthetic microphone fixtures, not a
physical room test.

The subsequent full two-person regression retained both voice profiles and
recognized a returning user. However, it admitted an unrelated TV voice as Selma:
`logs/isolation-enrollment-browser-voxlock-parallel-final.json` is a **failed**
background-rejection test. No input identity threshold or microphone admission
policy was modified in this output-verification task. This remains an open
input-speaker issue, not evidence of universal conversational reliability.

A deliberately long 45-word English request exposed the timestamp-only overlap
bug: `parallel-long.json` ends early and must not be counted as a successful
complete target. `debug_parallel_windows.py` reproduces it with saved authored
PCM; after the word-overlap fix it confirmed all 45 words and a 15.6-s output.
Unit tests now also drop one/two words at an ASR window's left edge, requiring
recovery from already verified overlapping words. The final live receipt is
`parallel-long-fixed.json`, which passed on the running deployment; retain the
earlier failure and debug traces. The English report also passed public HTTPS
Chrome layout checks at desktop and 390-pixel mobile width, without page errors.
