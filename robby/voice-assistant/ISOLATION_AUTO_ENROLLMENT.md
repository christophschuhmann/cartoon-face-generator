# Automatic wake enrollment and a bank of known input voices

This extends [the optional CUDA microphone filters](INPUT_ISOLATION_UI.md).
Select VoxLock or Scicom in the existing Robby settings; Off remains the default.
There is no need to press **Learn my voice** for ordinary use.

## User-visible behavior

Say **Hey Robby** / **Hey Robbie** / **Hi Robby** and introduce yourself or ask
your question. The existing ECAPA speaker database matches the completed
utterance to a known person or creates a new session speaker. A name is optional.
Each person has their own four-second input reference. Short wake utterances
authorize enrollment; later confidently matched utterances complete that person's
four seconds. The same audio interval is never counted twice. Different speakers
never contribute to a single accumulated reference.

Once ready, a known person's reference is reused. Another wake introduction adds
another person; it does not replace the first. With isolation selected, matching
registered voices can continue without another wake phrase during this session,
including switching between known people. Unknown voices must start with the
wake phrase (or receive the existing explicit speaker invitation). Merely
mentioning Robby later in a sentence does not authorize enrollment.

The UI lists each registered person's name and progress toward four seconds.
**Reset learned filter voices** clears the filter bank, while the existing
speaker-management reset clears both identity and filter references. The **Manual reset & learn** button remains as a troubleshooting override; it
clears the previous filter bank and captures a fresh single reference. Voice recordings and
embeddings remain session RAM; existing text memory does not persist them.

## Why there is a raw wake path

A separator focused on Alice may remove Bob saying “Hey Robby”. Therefore the
existing raw microphone branch has a separate small CPU neural VAD. After a
one-second speech pause (or a longer configured pause), it can check a bounded utterance using the already selected ASR and
CPU ECAPA. Only an explicit wake, a registered voice or an explicit invitation
can re-enter the normal serialized turn pipeline. Ordinary unknown background
speech is not sent to the conversation LLM and cannot create a profile.

There is at most one recovery request in flight, no unbounded job queue, and a
12-second request timeout. Completed raw utterances longer than 24 seconds are
not sent through this extra path; give a shorter introduction. Playback-tagged
audio is excluded to avoid enrolling Robby's echo. Introduce a new voice after
Robby has finished speaking, ideally without overlapping TV or another speaker.
Continuous background speech can prevent the pause-final raw wake check; this
is not continuous keyword spotting in overlapping speech. The extra check is pause-final, not a 40-ms keyword
spotter: four seconds of reference collection, the pause, ASR and embedding add
latency before enrollment becomes available.

Strong known matches whose filtered signal has adequate energy skip duplicate
ASR. If a known voice was strongly attenuated, the raw path can recover its
sentence instead. Overlapping raw and normal results are deduplicated using
their original audio intervals. This is not a guarantee of perfect recovery in
overlap or noise; reference contamination and identity mistakes remain possible.

## Keeping several voices with single-target separators

The upstream [VoxLock](https://github.com/arbazsiddiqui/voxlock) and
[Scicom](https://huggingface.co/Scicom-intl/voice-isolator) are target-speaker
extractors, not native “all known people” classifiers. This integration retains
separate state and voice keys for each registered person, sharing model weights.
VoxLock replays its CUDA graph serially with per-person state. Scicom processes
the references as independent calls in one GPU batch.

For two or more voices, a causal maximum spectral mask against the original
mixture combines the estimates. It avoids summing duplicate estimates and uses
the original phase. This experimental union adds 24 ms of overlap/add delay;
the input/inference chunk remains 40 ms. One-voice operation bypasses this extra
stage. Original playback timestamps and exact sample counts are preserved.

The present memory budget supports **four filter references**. Beyond that,
the UI reports capacity and bypasses waveform isolation; identity admission
still applies. A known fifth person is never silently removed to make space.
This is a visible limitation, not a claim of unlimited realtime multi-speaker
separation. Source Scicom weights have a nonstandard license.

We collect and retain four seconds. VoxLock's pinned upstream interface selects
its loudest three seconds internally; Scicom receives the reference clip through
its own enrollment encoder. This is not a modification of their training or
native reference-length behavior.

## Measurements and limitations

RTX 3090 GPU 1, real weights, two enrolled synthetic German voices, one continuous
filter stream: A speaks, B speaks, then an unknown TV voice. 306,080 input samples
and 306,080 output samples after flushing, for both models.

| Model | Two-reference chunk time p50 / p95 (includes IPC) | A WER | B WER | Unknown TV attenuation |
| --- | ---: | ---: | ---: | ---: |
| VoxLock CUDA Graphs | 10.70 / 11.91 ms | 0 | 0 | 0.00 dB |
| Scicom Agent CUDA Graphs | 11.81 / 12.98 ms | 0 | 0.167 | 4.36 dB |

The negative result matters: both models left intelligible unknown TV in this
particular synthetic test. Scicom attenuated B by 42.72 dB and lost the first
word. Thus waveform isolation alone does **not** implement reliable admission.
The separate speaker-database gate is required before any conversational reply.
That gate and live interruption verification now use **original aligned audio**,
not the filtered waveform: a failed browser test showed that conditioned output
could make an unknown TV voice match a known person. A name without a usable
speaker embedding cannot enroll an automatic filter reference. Deleted/expired
speaker IDs are removed from the filter bank as well.
The recovery path addresses attenuation of a registered voice, subject to the
accuracy and latency of ASR/ECAPA. No physical-room accuracy claim is made.

The first browser test exposed a 420-ms pause between “Hey Robby” and the
speaker's name. The extra raw recovery now waits one second, without changing
the primary reply/Stop pause setting. It also exposed duplicate final ASR:
TYGER waited for a Nemotron final before the selected Parakeet final. Sessions
using a separate final recognizer now defer that final transcription to the
existing sentence pipeline; native previews and TYGER state still run. The
Nemotron-only path retains its original final decoder. No audio is dropped or
fabricated to catch up. Initial failure receipt is retained as
`logs/isolation-enrollment-browser-voxlock-before.json`.

Public Chrome regressions with **both VoxLock and Scicom: passed** after the corrections. Two people
were automatically enrolled with independent 4.0-s references, the first person
returned without a wake phrase, and unknown TV produced neither a conversational
turn nor a new profile. Real ASR, CUDA isolation, ECAPA, LLM and TTS were used;
no JavaScript/server error was reported. The raw recovery handled two utterances with VoxLock and one with Scicom.
This is a synthetic microphone test, not a physical-room/multi-person accuracy
study. The raw identity regression is retained separately as a failing receipt.

The previous bot-echo/Stop stress test also failed with isolation Off. This work
does not claim to fix that independent downstream ASR backlog limitation.

Four-reference capacity check (two references duplicated, not four independent
identities): VoxLock p50/p95 18.58/20.51 ms, Scicom 11.93/12.70 ms per 40-ms block,
including IPC. Both retained exactly 64,000 samples after flush. Receipt:
`logs/isolation-four-reference-capacity.json`.

Targeted automated regression total: **141 tests passed** across the isolation,
sentence reliability, pause, wake, focus, speaker management/names/teacher,
Stop-feedback and GPU scheduling suites. These are behavior regressions, not
141 independently measured human speakers.

## Reproduce

Use the pinned environment and model-cache bootstrap from INPUT_ISOLATION_UI.md.

```sh
python -m unittest test_input_isolation test_isolation_enrollment test_sentence_reliability test_stop_commands test_stop_feedback
python test_isolation_bank_cuda.py
uv run --no-project --with playwright --python /path/to/robby/python browser_isolation_enrollment.py
ROBBY_FILTER_MODEL=scicom uv run --no-project --with playwright --python /path/to/robby/python browser_isolation_enrollment.py
```

The browser test uses real HTTPS, AudioWorklet, CUDA, ASR, ECAPA and replies, with
authored synthetic microphone audio. It checks two wake introductions without
the learn button, return of the first voice without wake, and rejection of an
unknown non-wake TV clip. Read the receipts for actual pass/fail status:
`logs/isolation-known-bank-cuda.json`, `logs/isolation-enrollment-browser-*.json`.
Unit tests deliberately simulate worker failures and identity vectors; GPU and
browser tests do not mock model outputs.

Core additions: `input_isolation_wake.py`, `input_isolation_union.py`; reference
bank and routing in `input_isolation.py`; multi-state GPU adapters in
`input_isolation_models.py` / `input_isolation_worker.py`. Normal conversation
admission and deduplication are wired in `sentence_session.py`. The existing
worker, microphone controls, server and Cloudflare tunnel are reused.
