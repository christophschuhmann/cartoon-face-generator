# Speech recovery and synchronized stunts

Robby keeps generated answers when voice synthesis cannot finish. The normal path still streams audio. Recovery is bounded and does not disable word verification.

## What failed on November 14, 2026

The private operational logs distinguished three failures that previously looked alike in the interface:

- The selected language-model endpoint returned HTTP 429 before any answer could be spoken (11:53:56 and 11:57:12 UTC). These were planning failures, not TTS OOMs.
- The word checker rejected short generated openings. At 11:54:17 a new speech attempt recovered successfully. No GPU OOM was recorded for those incidents.
- At 11:58:07 the microphone queue reached its five-second bound and the conversation closed. This is an input-overload failure, separate from speech synthesis. This update does not claim to eliminate microphone overload under all GPU contention.

A code audit also found that a verified *prefix* with an unverified ending was returned as a successful complete sentence. After exhausted recovery, the producer task could be cancelled before the rest of the language-model answer reached the screen. Error messages were also assigned to the current agent text before their error type was checked.

The old action scheduler had a four-second fallback: if audio was delayed by retries or API limits, the whole spin or somersault could finish before speech began.

## Current recovery policy

1. Each sentence has at most three automatic speech attempts. New attempts use different seeds, with progressively simpler delivery instructions while preserving the spoken words. The final eligible Small RL attempt uses ASR-guided Best-of-3 with 960 ms chunks. An OOM uses the smaller single-stream fallback, not a larger batch.
2. A transient transport failure can retry only if that attempt published no audio. Closing the old stream requests cancellation; admission waits until the shared worker is ready and idle. No other session is cancelled to make space.
3. A clean terminal result containing an incomplete, strictly verified prefix is not treated as complete. If the checker supplies an exact remaining suffix at an original written-word boundary, only that suffix is synthesized again. Negations remain in the suffix. A boundary inside a contraction is ambiguous and cannot authorize automatic continuation. The overall three-attempt limit still applies.
4. If audio was published but its continuation point is unknown, automatic replay stops. A disconnect or explicit user cancellation never triggers a replay of already published audio.
5. When recovery is exhausted, the LLM producer continues. The complete generated response stays on screen. Pending sentence specifications remain in session RAM and the UI marks speech incomplete.
6. **Read remaining reply** retries the retained speech with new seeds, without another LLM call, another user message, or repeated tools. If one interrupted sentence might repeat, the button states that explicitly. A new conversational turn replaces this pending retry; it is not saved as a public artifact.

The retry path does not guarantee correct pronunciation, perfect transcription or zero repetitions. ASR is fallible. It preserves conservative word checks and exposes failures instead of claiming silent success.

## Provider recovery

The selected OpenRouter endpoint is used first and retried after a bounded `Retry-After`. After a second HTTP 429, the same Qwen model may be retried through other endpoints in the fetched model catalogue. There is no automatic switch to a different language model. Actual provider metadata remains visible. Authentication failures do not trigger failover. Set `ROBO_LLM_PROVIDER_RECOVERY=0` to strictly pin the selected endpoint.

This uses the official [OpenRouter provider-routing interface](https://openrouter.ai/docs/guides/routing/provider-selection), restricted to known endpoint tags. Backup providers may have different latency and pricing. Local LLM requests do not use this route.

## Speech and motion

Spins, somersaults and other spoken direct actions now wait for their reply's actual browser playback position. Network arrival and a four-second wall-clock deadline do not start the animation. TTS retries therefore do not consume the animation before audio starts. A terminal no-audio result can still perform the requested visual action silently; explicitly silent requests start immediately. Cancellation, reduced motion and the expressive-actions switch retain their behavior.

## Reproduction

Use the same Python environment as the main voice assistant. From this directory:

```bash
PYTHONPATH=vendor/tyger-s2s python -m pytest -q \
  test_speech_retry.py test_llm_backends.py test_bridge.py \
  test_audio_input.py test_conversation_director.py
python check_speech_recovery_live.py
python check_verified_suffix_live.py
python browser_speech_recovery_check.py
python render_system_guide.py
```

The browser runner requires Playwright and Chrome. It uses the existing public HTTPS demo; edit its imported `URL` for another deployment. Do not occupy the single conversation slot while another visitor is using it. The live TTS script uses port 8792 and existing model/reference configuration. Let startup and CUDA graph capture complete first.

From `tts-runtime/humaneness-small/` (or the runtime `humaneness-small` directory):

```bash
python -m pytest -q tests/test_parallel_boundaries.py \
  tests/test_streaming_boundaries.py test_asr_chunk_search.py
```

Test layers are intentionally distinct:

- Unit tests inject synthetic SSE, timestamps and failures to check bounded retries, cancellation, exact negation-preserving suffixes, unknown-position refusal, seven-sentence text retention, error separation and saved-speech replay.
- A test-only client injects one connection failure *before* admission, then forwards subsequent requests to the real live TTS and ASR. No fault endpoint is installed in production and no synthetic waveform is presented as model audio.
- The browser test checks a twelve-second delayed-playback contract, then sends real Qwen/TTS requests for a spin, a somersault, and a four-sentence explanation. It records actual playback/motion overlap and checks the four diagrams on desktop and mobile.

Live test receipts are in `logs/speech-recovery-live.json` and `logs/speech-recovery-browser.json`; these are authored tests, not visitor recordings. The public report summarizes results without uploading private session logs. This is not a physical microphone/room test.

## Measured verification on November 14

All 52 selected Robby unit tests and 48 selected TTS tests passed. Four real TTS requests completed, including a deliberately injected client-side connection failure before admission and a naturally occurring rejected opening. Three real HTTPS browser turns completed without page errors. The four-sentence request produced all four spoken sentences, recovering after one rejected opening. Desktop and mobile layout checks passed.

| Real browser request | Request → first PCM, including LLM | Motion and actual playback overlapped | Spoken completion |
| --- | ---: | ---: | --- |
| Spin and speak | 1,651 ms | 2,692 ms | Yes |
| Somersault and speak | 1,284 ms | 3,931 ms | Yes |
| Explain rainbows in four sentences | 4,018 ms | Not applicable | All four sentences; one TTS retry |

These are individual measurements, not a latency percentile or an acoustic-room guarantee. Audio overlap uses the browser playback clock and rendered body pose; the short spin sentence does not fill the entire six-second motion. Hardware remains two RTX 3090 cards, with Small RL TTS on GPU 0 and Photon/Parakeet verification on GPU 1. Quick replies were disabled; the normal single-stream TTS path was selected.

The exact previously truncated English prompt at seed 778 also exercised **real suffix recovery**: the first output verified only “Hello, it is lovely to see you.” The second attempt generated only “We can discover something new together today.” The combined waveform contained both sentences, including the final word. First PCM was 1,031 ms; total generated audio was 5.30 s. The 6,992 ms test wall time includes an additional final ASR evaluation, so it is not production generation latency. That transcript contained an extra “and”; this is a recovered reply, not perfect word accuracy. The verifier and final evaluator share the same ASR family.

One earlier browser run exposed an undefined pending-action dereference. It was fixed before the final passing run; the failed receipt remains locally in `logs/speech-recovery-browser-before-null-guard.json`. Forced terminal-failure retention, the manual retry control and speech-only replay were verified with isolated browser/unit contracts, not a forced production outage. No public failure-injection endpoint was installed.

See the [public English report](static/speech-recovery.html) and [reviewed measurement summary](static/speech-recovery-results.json). Regenerate the report after the live checks with `python render_speech_recovery_report.py`. Only authored test results are exported; private conversations and recordings are excluded.

## Performance and restart

The recovery logic adds no new model pass on a fully verified successful sentence. Retrying costs additional generation time; repeated provider throttling and cold CUDA graph setup can still take much longer. Prior warm Best-of-3 figures (867 ms median first PCM, RTF 0.56) are documented in [ASR_CANDIDATE_STREAMING.md](ASR_CANDIDATE_STREAMING.md); they are not a fresh guarantee for every recovery case.

The worker remains single-admission and bounded. Robby, TTS and the podcast server keep their existing ports and Cloudflare tunnel. Follow the main deployment guide for startup; on this machine private `.runtime/restart-*-preserving-env.py` helpers preserve credentials in process memory without writing them into the repository. Never publish those runtime files or environment values.

Updated diagrams: `static/system-conversation.svg`, `static/system-latency.svg`, and new `static/system-recovery.svg`, generated from `render_system_guide.py`. The tool diagram remains available alongside them at `/desk-robot/#system-guide`.
