# Speech recovery and synchronized stunts

Robby keeps generated answers when voice synthesis cannot finish. The normal path still streams audio. Recovery is bounded and does not disable word verification.

## November 18: German speech and premature cutoffs

For the logged 09:00 hour, 3 of 10 completed response records were marked speech-incomplete. Eleven per-attempt `unverified_speech` and three `incomplete_verified_speech` failures were logged; all ten corresponding turn-done records said `barged=False`. The counts do not prove the cause of unlogged playback or every interruption. No transcripts or recordings are kept in this diagnostic.

An authored local one-attempt test of eight ordinary German sentences produced eight complete results. A harder set of ten sentences had five complete, two rejected openings and three incomplete results. On separately regenerated unverified synthetic audio, the ASR returned “2020” for the requested “2026”, omitted an initial hesitation, reduced “einen” to “ein” in a phrase, and rendered an abbreviation/currency phrase differently. These are real model/ASR differences; the gate was right to withhold an incorrect year rather than guessing. The tests used synthetic authored text, fixed seeds, a fixed reference and local API; they do not establish real-world accuracy.

For German TTS, unambiguous standalone cardinal numbers up to 9999 and `z. B.` are written out in the spoken script while the displayed original is retained. Dates, decimal numbers, ranges, signs, leading-zero values and IDs are excluded. The boundary matcher canonicalizes exact German number spellings and supports the `ein`/`einen` variant only with two preceding and one following exact anchors. Negations, skipped words, different numbers and an unmatched final word do not pass that rule. On an unheard retry only, a leading nonlexical “Hm,”-type hesitation may be removed; content words are not discarded. Partial audio is still resumed only at a verified word boundary. This does not guarantee success when the TTS omits or changes content.

After the change, the same ten synthetic challenging cases and fixed seeds produced eight complete results with one attempt, versus five before. A separate post-change run allowing the normal bounded retries completed 10/10; two cases required a second attempt (one retry synthesized a verified suffix). The before run did not include a comparable three-attempt measurement, and the small set is not a statistical quality or intelligibility study. Generated speech with an incorrect year remains rejected. A filler omitted on an unheard retry is a deliberate exception to literal speech and does not alter the displayed answer.

To reproduce against an idle local TTS server, from the voice-assistant directory run `PYTHONPATH=vendor/tyger-s2s:. python experiments/tts_boundary_reliability.py --attempts 1`, then repeat with `--attempts 3`. The script submits ten short authored German sentences and prints anonymized case indices, verification metadata and timing, without saving the generated audio. It uses the fixed `emolia_c1699` reference and competes for the shared TTS worker, so do not run it during a user's generation. The first-attempt comparison used the same scripts and seeds before and after the update; the old source revision is required to repeat the before measurement.

After the services were restarted, two authored HTTPS browser turns each completed with seven received audio chunks and `speech_complete=true`; first PCM reached the conversation server after 1,912 ms and 2,787 ms, respectively. The second required an unheard-sentence retry and a verified-suffix continuation. These were typed inputs, not physical microphone tests. The 62 conversation/TTS Python tests, 37 TTS boundary/parallel tests and 19 stop/interruption tests (plus 21 subtests) passed. These checks do not prove interruption handling in every real acoustic environment.

## Somersault request audit, November 16, 2026

Robby's logs do not retain user transcripts or browser-rendered motion; they cannot prove what happened in a particular private request. An authored HTTPS browser test of “Mach bitte einen Salto” did dispatch a validated `somersault` and measured a 360-degree body flip, although a later sentence failed TTS verification. A separate parser audit found that “Ich will, dass du einen Salto machst”, “Du sollst einen Salto machen” and “Salto!” were not recognized as direct actions, leaving execution to the language model. These explicit variants are now recognized without allowing negated, quoted or conditional requests. After deployment, an HTTPS browser test of “Ich will, dass du einen Salto machst” observed the validated action, 360-degree body flip and five audio chunks with complete speech. This uses typed test input, not a physical microphone. Validated action types and direct/tool route are logged without text or speaker data; this reports server scheduling, not proof of browser rendering. Browser reduced-motion and the expressive-actions setting can still suppress movement. TTS verification may separately fail.

## What failed on November 14, 2026

The private operational logs distinguished three failures that previously looked alike in the interface:

- The selected language-model endpoint returned HTTP 429 before any answer could be spoken (11:53:56 and 11:57:12 UTC). These were planning failures, not TTS OOMs.
- The word checker rejected short generated openings. At 11:54:17 a new speech attempt recovered successfully. No GPU OOM was recorded for those incidents.
- At 11:58:07 the microphone queue reached its five-second bound and the conversation closed. This is an input-overload failure, separate from speech synthesis. This update does not claim to eliminate microphone overload under all GPU contention.

A code audit also found that a verified *prefix* with an unverified ending was returned as a successful complete sentence. After exhausted recovery, the producer task could be cancelled before the rest of the language-model answer reached the screen. Error messages were also assigned to the current agent text before their error type was checked.

The old action scheduler had a four-second fallback: if audio was delayed by retries or API limits, the whole spin or somersault could finish before speech began.

## Current recovery policy

1. Each sentence has at most three automatic speech attempts. New attempts use different seeds, with progressively simpler delivery instructions while preserving the spoken words. As of November 16, automatic retries remain single-stream by default to avoid a cold Best-of-3 graph capture taking over a minute. Set `ROBO_TTS_RETRY_SEARCH=1` to use ASR-guided Best-of-3 on the final eligible Small RL retry. The independently selectable Best-of-3 UI mode is unchanged. An OOM uses the smaller single-stream fallback, not a larger batch.
2. A transient transport failure can retry only if that attempt published no audio. Closing the old stream requests cancellation; admission waits until the shared worker is ready and idle. No other session is cancelled to make space.
3. A clean terminal result containing an incomplete, strictly verified prefix is not treated as complete. If the checker supplies an exact remaining suffix at an original written-word boundary, only that suffix is synthesized again. Negations remain in the suffix. A boundary inside a contraction is ambiguous and cannot authorize automatic continuation. The overall three-attempt limit still applies.
4. If audio was published but its continuation point is unknown, automatic replay stops. A disconnect or explicit user cancellation never triggers a replay of already published audio.
5. When recovery is exhausted, the LLM producer continues. The complete generated response stays on screen. Pending sentence specifications remain in session RAM and the UI marks speech incomplete.
6. **Read remaining reply** retries the retained speech with new seeds, without another LLM call, another user message, or repeated tools. If one interrupted sentence might repeat, the button states that explicitly. A new conversational turn replaces this pending retry; it is not saved as a public artifact.

The retry path does not guarantee correct pronunciation, perfect transcription or zero repetitions. ASR is fallible. It preserves conservative word checks and exposes failures instead of claiming silent success.

## Provider recovery

The selected OpenRouter endpoint is used first and retried up to twice after a bounded `Retry-After` (1–8 seconds per wait). Progress is visible in the UI. By default the selected provider is pinned, including on rate limiting; Nebius FP4 is the selected Qwen default. An operator can explicitly set `ROBO_LLM_PROVIDER_RECOVERY=1` to retry the same Qwen model through another registered endpoint after a second HTTP 429. There is no automatic switch to a different language model. Actual provider metadata remains visible. Authentication failures do not trigger failover. Retrying cannot guarantee provider availability.

This uses the official [OpenRouter provider-routing interface](https://openrouter.ai/docs/guides/routing/provider-selection), restricted to known endpoint tags. Backup providers may have different latency and pricing. Local LLM requests do not use this route.

## Speech and motion

The browser starts a requested trick when the matching reply reaches audio playback. If speech stalls, it starts the trick on the first visible animation frame after four seconds. A terminal speech failure releases a pending trick immediately. Late audio cannot replay a completed stunt. Stop cancels a pending or running action, and the browser respects reduced motion and the expressive-actions switch.

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
- The browser test checks matching and unrelated playback IDs, a four-second audio stall, late audio and cancellation. It also sends real LLM/TTS requests for a spin, a somersault and a four-sentence explanation, and records playback and motion overlap.

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
