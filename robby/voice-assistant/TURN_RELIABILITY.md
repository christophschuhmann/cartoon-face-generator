# Speech pause and TTS recovery repair — 2026-11-11

## Observed failures

Seven previous sessions on November 11 (16:11–18:24 UTC) contained six
`UnverifiedSpeechError` failures, two planning-stage `ValueError` failures and
one microphone backlog closure. No CUDA OOM or HTTP transport exception was
recorded for those six speech failures. This is a bounded log review, not a
claim that networking or memory can never fail.

Two endpoint fallbacks incorrectly treated a low relative microphone level or
1.6 seconds without word-count growth as a speech pause. They could override
active Silero VAD, and the level-based end crop could remove quieter words.
An asynchronous final ASR could also lack the latest microphone samples when
the GPU hop loop lagged behind the independent microphone/VAD clock.

## Current behavior

- A normal conversational turn requires the selected neural speech pause
  (default 300 ms, existing 200–2000 ms slider). Punctuation, unchanged words,
  quieter syllables and uncertain speaker identity cannot substitute for it.
- The final ASR buffer must include the latest detected speech plus 80 ms.
  Speech resuming while ASR runs invalidates the pending transcript, even if
  the user subsequently pauses again. Quiet opening and ending words are kept.
- Native ASR still supplies previews. Additional whole-utterance probes while
  listening are limited to one per 1.28 seconds; playback stop probes retain
  their faster cadence. This reduces GPU contention, but cannot guarantee
  freedom from backlog under arbitrary concurrent workloads.
- Every actual submission logs its VAD score, quiet duration, required pause,
  buffer backlog, word count and epoch. No user text, microphone recordings or
  voiceprints are added to these logs.
- The output boundary guard still withholds unconfirmed speech and applies
  100-ms fades. It normalizes explicit contraction/number spellings. A minor
  long-word spelling mismatch in the opening requires three exact adjacent
  words. Missing negations, unrelated speech and a single matching word in a
  multiword sentence cannot open the gate. These heuristics are not a
  calibrated intelligibility or semantic-correctness test.
- If an entire sentence was withheld, the client makes at most two additional
  attempts, using different seeds and the same text. Already published
  sentences are not regenerated. A partially published sentence is never
  replayed automatically. Cancellation stops recovery immediately.
- On the standard Small RL HTTP path, a failed opening also shortens GENERAL
  on the next attempt while preserving inline acting cues. The final attempt
  uses a natural initial cue. Spoken words, internal cues, references and
  language stay unchanged. This deliberately trades acting intensity for
  intelligibility only after failed takes; other checkpoints are unchanged.
- Explicit pre-audio OOM permits only one retry after worker cleanup; a
  persistent capacity problem remains an error. Ambiguous network failures
  are not blindly replayed. Existing 409/503 admission waits remain bounded.
- The optional multiplexed bridge path retries a withheld job in place with
  fresh generation state, preserving other jobs and spoken order.
- An ordinary malformed LLM completion may be retried once if it has not
  yielded any sentence. This does not restart a partially spoken answer.
- A transient provider/transport failure in the read-only sentence director
  is also retried once before its first sentence. It stays on the selected
  provider, excludes authentication/validation failures, and cannot replay
  tools or previously spoken sentences. The separate tool director is not
  automatically replayed.

## Real-model diagnosis and validation

The first public regression run is retained as
`logs/turn-reliability/first-run-report.json`. Two of three paired TTS tests
passed. A German sentence failed with three seeds; standalone, non-published
raw diagnostic generations confirmed an unintelligible transcript or no words
from independent Parakeet v3. Thus relaxing the output gate would have exposed
bad audio. Three shorter-directive variants produced recognized speech instead
(`concise-retry-diagnostic.json`); this is a tiny failure-specific probe, not a
general quality benchmark. A second browser case also exposed a provider SSE
error before the first sentence, which motivated the bounded provider retry.

The repeated real-model test is in `logs/turn-reliability/report.json`. Read
its explicit `passed` fields; do not substitute unit tests for live results.
The focused CPU suites contain 91 Robby tests and 43 TTS boundary/alignment
tests. Failed first runs are intentionally retained for reproducibility.

**Trade-off:** continuous background speech that Silero considers speech can
delay submission. Low amplitude alone no longer labels it as background. This
fix prioritizes not cutting off an ongoing user; it does not solve source
separation or make unknown overlapping speakers perfectly distinguishable.
Existing wake-word admission, speaker identity and explicit interruption
decisions remain independent of this endpoint rule.

## Reproduction

In the existing Robby Python environment:

```sh
cd robo-integration
python -m unittest test_pause_endpoint test_sentence_reliability test_speech_retry test_shared_turn test_bolt test_two_stage -q
cd ../humaneness-small
python -m pytest -q tests/test_streaming_boundaries.py tests/test_alignment.py tests/test_speaker_reward.py test_live_batch.py
cd ../robo-integration
uv run --no-project --with playwright --python /path/to/robby/python verify_turn_reliability.py
```

The browser test uses existing authored synthetic fixtures under
`logs/speech-pause/first.npy` and `second.npy`, created by
`validate_speech_pause.py`. It tests a softer second phrase, an internal pause
shorter than the selected setting, added noise, actual public HTTPS capture,
ASR, LLM, speech generation and playback. It also checks German and English
sentence TTS. Results are written to `logs/turn-reliability/`; they distinguish
real-model/browser tests from synthetic SSE failure injection in the unit
tests. Physical microphone acoustics and arbitrary televisions are not covered.

The podcast process and tunnel do not need restarting. Restart only the owned
Robby and TTS workers with their existing deployment environments after code
changes. Service restart ownership/receipt is in
`logs/reliability-restart.json`; operational logs are
`logs/robby-reliability-20261111.log` and `logs/tts-reliability-20261111.log`.
Never copy process environments or credentials into documentation.
