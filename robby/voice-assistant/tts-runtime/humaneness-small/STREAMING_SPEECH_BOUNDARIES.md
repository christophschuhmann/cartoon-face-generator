# ASR-confirmed streaming speech boundaries

Robby's Small RL streaming paths use the existing resident Parakeet v3 model to
check generated audio before publishing PCM. The fast-start switch no longer
bypasses this check. This applies both to `/api/turn` and the internal
`/api/live-speech` continuous batching transport when `align: true` (Robby's
normal speech and reaction defaults).

## Behavior

* Buffer the beginning until Parakeet recognizes the first two intended words,
  or the sole word of a one-word utterance. Unrelated recognized words cannot
  open the gate. Unicode/case/punctuation normalization is shared with WER.
* Physically remove preceding audio. Keep up to 100 ms before the recognized
  onset for a 100-ms fade-in; the first word is not intentionally faded away.
* Hold a 400-ms trailing buffer. Do not release samples past the latest
  sufficiently matched target word. Once the last target words are confirmed,
  retain 60 ms of air and fade out over 100 ms. Stop decoding early when that
  boundary is available. Explicit requested edge bursts remain protected.
* At EOS, check the final PCM. If the ending is uncertain, fade at the last
  verified target word and report an incomplete target. Never use a forced
  transcript as proof that the words were actually spoken. If the opening
  cannot be verified within six seconds, suppress it and return a visible
  generation error rather than playing the raw buffer.
* Cancellation discards held samples. `align: false` explicitly bypasses the
  filter, for comparisons or deliberate nonverbal output. Pure nonverbal
  scripts without target words cannot be checked by this word gate.

## Efficiency and measurements

ASR starts after at least 600 ms of generated audio, then checks at most once per
400 ms of new audio until the opening is confirmed, then every 800 ms
(configurable through `SMALL_BOUNDARY_HOP_S`, bounded to 0.4–1.2 seconds).
Simultaneously due continuous streams share a single ASR
batch, with the existing ASR lock. No new ASR model, network round trip, temporary
WAV or repeated model load is needed. Checks run on the CUDA owner thread, not
the WebSocket event loop. A final EOS check handles very short utterances.

Reports contain `start_verified`, `end_verified`, removed lead/cut positions,
`asr_calls`, `asr_ms`, `asr_batch_size`, and the number of emitted samples.
`first_audio_ms` measures the first **released**, not merely decoded, PCM chunk.
Raw sample coordinates and cropped output length are tracked separately.

The older offline Qwen forced aligner remains available. On this machine it is
placed on CPU using `SMALL_ALIGN_DEVICE=cpu` in `gpu-layout.local.env`, reserving
VRAM for the real-time Parakeet checks and Robby's ASR. Verified live streams do
not run that extra forced-alignment pass. The Podcast worker/GPU is unchanged.

## Verification

Run from `humaneness-small` with the deployment Python environment:

```sh
PYTHONPATH=. python -m pytest tests/test_streaming_boundaries.py tests/test_alignment.py test_live_batch.py -q
```

Unit tests cover wrong openings, a missing second word, actual leading crop,
fade sample coordinates, repeated ending phrases, one-word utterances,
uncertain endings, silence, malformed timestamps, cancelled audio, protected
intentional bursts, and batching two ASR checks. Test fixtures are synthetic
unit inputs; these do not substitute for the separate real-model smoke test.

`../robo-integration/verify_streaming_boundaries.py` exercises the actual TTS and
resident ASR over the continuous WebSocket and classic streaming endpoint,
including German/English and an explicit bypass comparison. Its measured JSON
reports and synthetic WAVs are under `../robo-integration/logs/streaming-boundaries/`.
`../robo-integration/verify_gpu_split.py` additionally exercises actual browser
capture, the conversation, and playback through the public HTTPS demo.

## Limitations

ASR can misrecognize names, numbers, code-switching, very short words and highly
emotional speech. Strict initial word confirmation trades some startup latency
and occasional rejected takes for suppressing unverified audio. These timestamps
are acoustic estimates, not phoneme-accurate ground truth. The gate checks
boundaries/progress, not every interior phoneme; it cannot guarantee that all
within-sentence pronunciation errors are removed. The six-second bound concerns
generated audio, not wall-clock time. No claim of zero-latency filtering is made.

## Deployment measurements — 2026-11-10, RTX 3090

Single smoke runs on the shared machine, not a statistical latency benchmark:

| Route / language | Gate | First released PCM | Total request | Output duration |
|---|---|---:|---:|---:|
| continuous / de | off | 1.06 s | 7.41 s | 4.80 s |
| continuous / de | on | 4.06 s | 8.94 s | 4.18 s |
| continuous / en | off | 0.50 s | 6.00 s | 5.12 s |
| continuous / en | on | 2.31 s | 9.02 s | 4.58 s |
| classic / de | on | 1.17 s | 2.42 s | 2.56 s |

The ordinary Robby single-stream path (classic endpoint) generated its test
sentence in 2.33 s including the gate, with 0.68 s measured TTS device time and
1.50 s total ASR check time across three calls. First playable PCM was 1.17 s
including loopback request handling. Device-only TTS RTF was 0.24; the whole
filtered request took 2.43 s for 2.56 s of output. Do not confuse these metrics.

The continuous scheduler is slower on this host; its readings above include
ASR and scheduler work. Moving sustained checks from 400 to 800 ms reduced
checks from nine to six for these examples (raw reports for the initial
configuration remain in `initial-400ms/`). First-use ASR kernel initialization
also affects the first gated case. Warm standalone GPU ASR checks measured
269/352/370 ms for 1/2/3-second audio. Startup/model warm-up itself took about ten
minutes on this shared host and is not included in per-request figures.

39 focused unit/regression tests passed. Real German and English TTS passed
with and without the gate, plus the classic streaming path. An actual Parakeet
check on synthetic TTS with inserted unrelated speech removed 1.26 s of lead,
retained the target sentence, and stopped at original time 4.08 s, before the
appended unrelated speech. Its CPU execution was a correctness check only.

Public Chromium checks: the typed two-sentence reply produced 11 audible PCM
chunks without browser errors; a separate synthetic-microphone run captured
761 blocks and completed ASR, LLM, gated TTS and playback. The initial combined
microphone run hit `audio_too_fast` during ASR switching; a fresh browser with
five seconds of authored leading silence passed. Physical microphone, webcam
and room echo are not covered by these checks. All receipts are in
`robo-integration/logs/streaming-boundaries/verification.json` and adjacent files.

Model-switch admission was also tested against the running service: insufficient
VRAM returns HTTP 409 before unloading Small. The normal Robby/TTS services are
ready; Podcast was not restarted and continued processing jobs on GPU 1.
