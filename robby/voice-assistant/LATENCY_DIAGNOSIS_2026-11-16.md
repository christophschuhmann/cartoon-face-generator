# Robby response latency — 16 November 2026

## Current default: Nebius

Following repeated Cerebras shared-pool HTTP 429 responses, Qwen 3.8 27B now defaults to the explicitly pinned `nebius/fp4` OpenRouter endpoint. A one-time browser migration changes an existing saved Cerebras selection to Nebius; after migration the user can still select and persist any endpoint, including Cerebras. Conversation text is sent to the newly selected provider. FP4 quantization can affect quality. No parallel/duplicate requests or automatic fallback were introduced.

On this host, a small sequence of real, short synthetic prompts measured Nebius first token at 375, 395 and 808 ms; a forced tool-call request returned its first tool delta in 367 ms. For context, the first text/tool trials were 817/507 ms for CoreWeave FP8, 563/1,035 ms for DeepInfra BF16, 2,071/1,829 ms for Chutes FP8 and 3,936/8,947 ms for Near AI FP8. CoreWeave's additional text trials were 666 and 769 ms; DeepInfra's were 556 and 658 ms. This is not a distribution or a quality benchmark, and subsequent load may change the ordering. TTS, ASR and browser playback are excluded. Provider pricing and quantization differ; check OpenRouter's current endpoint details.

After deployment, an authored HTTPS browser turn reached Nebius in the actual Robby pipeline: LLM first token 1,027 ms, first PCM 1,817 ms after response start, with 10 audio chunks received and verified full speech completion. One later sentence required one TTS retry. These timings exclude microphone ASR and actual physical playback latency and are a single example rather than a reliability guarantee. A separate browser test verified the one-time saved-Cerebras-to-Nebius migration without JavaScript errors.

The investigation below originally used the Qwen 3.8 27B OpenRouter **Cerebras FP16** endpoint. The selected endpoint is pinned by default, including rate-limit handling. Set `ROBO_LLM_PROVIDER_RECOVERY=1` explicitly to restore the optional same-model alternate-provider retry; such a request sends conversation text to that provider. No duplicate/hedged requests are enabled.

## Measurements

Historical server logs recorded 22.47 s, 20.97 s and 20.80 s from response-start to the first PCM received by the conversation server. They did not retain an individual LLM/TTS breakdown, so their exact cause cannot be reconstructed. An `incomplete_verified_speech` warning in the 22.47-second case occurred **after** first audio and is not evidence for the initial delay.

A new three-turn typed-input HTTPS browser test under shared-GPU load measured:

| Case | Qwen first sentence | TTS admission | First PCM after admission | Reply start to first PCM | Completion |
|---|---:|---:|---:|---:|---|
| 1 | 932 ms tool director; first sentence ready at 1,607 ms | 37 ms | 664 ms after the successful second attempt | 3,275 ms | Complete; one opening retry |
| 2 | 8,817 ms; first token 8,747 ms | 29 ms | 671 ms | 9,526 ms | Complete |
| 3 | 8,853 ms; first token 8,804 ms | 30 ms | 747 ms | 9,637 ms | Incomplete after TTS retries |

The first and third rows demonstrate that speech verification/retries are a separate reliability issue. The 8.8 s measurements are LLM-side wall time, including request preparation and any provider retry; they are not pure device inference time. These three tests do not establish p95 or prove the cause of the older 22.47 s case. Browser playback buffering and input ASR are not part of first-PCM time. GPU 1 was shared with podcast and input isolation. Neither the original nor the new tests measure physical microphone/loudspeaker latency.

A separate eight-request alternating Cerebras test reproduced HTTP 429: one request took about 8.86 s after a bounded rate-limit retry and another ended in HTTP error after about 8.58 s. Other tested first tokens were roughly 0.35–0.68 s without tools and 0.40–0.43 s with tools in this small sample. This demonstrates that an endpoint limit can cause the observed pattern; it does not prove every slow call was rate-limited. Earlier probes also encountered HTTP 402 after the configured key budget was exhausted. After the user's top-up, an account check reported a positive remaining budget and a Cerebras probe succeeded; subsequent requests nevertheless sometimes returned 429. The precise source of those historical 429s is unknown because their response metadata was not retained. OpenRouter documents that provider-side limits may also produce 429 responses even with a paid account: https://openrouter.ai/blog/llm-api-rate-limits/. No billing details or credentials are logged.

## What changed

- `latency_sentence`, `latency_first_pcm`, and `latency_complete` log a random per-turn trace ID, model/provider, first token/sentence, TTS admission, successful-attempt first PCM, retries, verification counters and completion status. They intentionally exclude scripts, transcripts, audio, speaker identifiers, provider bodies and credentials. The browser timing details expose TTS admission versus post-admission first PCM and recorded rate-limit waits. Missing timings remain missing rather than zero.
- Rate-limit waits record actual **bounded configured sleep**; `llm_ttft_ms` includes these waits. The LLM request has at most three attempts and two bounded waits of 1–8 seconds each, before its answer or actions have been emitted. The UI displays retry progress and clears the old reply when a new turn starts. A new 429 may report an allowlisted `limit_source` in logs when the provider supplies it; otherwise it is marked unknown. No provider error body, transcript, or key is logged. A persistent limit can still fail and increase latency. The bounded wait is an operational cap; the provider may request a longer delay. 402 is shown as a key-limit/account issue, not as TTS failure.
- The third automatic speech retry now uses a single stream by default. Previously, cold ASR Best-of-3 graph capture cost ~90 seconds on this host. `ROBO_TTS_RETRY_SEARCH=1` opts back in. Explicit Best-of-3 selection in the UI is unchanged. The word verifier remains enabled; failures do not silently emit unverified speech. The change avoids one known expensive recovery path, but it does not eliminate 429 or fix all speech-verification failures.

## Reproduce

Run `PYTHONPATH=vendor/tyger-s2s python -m pytest -q test_shared_turn.py test_speech_retry.py test_bridge.py test_llm_backends.py test_conversation_director.py`. For genuine end-to-end measurement use an authored browser request, retain only reviewed non-content metrics, and inspect `logs/server.log` for the three `latency_*` records with the same trace ID. A real provider account, idle conversation slot and ready TTS are needed. Run only a limited number of provider probes because they consume the real key's allowance. The loopback TTS and Podcast workers are single/shared resources; do not stop unrelated jobs to run benchmarks.

## Post-change checks

The modified direct TTS path was exercised with a real selected Small RL stream and the parallel word verifier: admission 29.96 ms, first PCM 740.91 ms after admission, 838.60 ms from pipeline start, three PCM chunks, full verified completion. This is a single authored text-only test; no remote LLM or physical microphone was involved. An HTTPS browser check used explicitly synthetic UI messages and confirmed that the rate-limit wait, TTS admission timing and HTTP 402 key-limit guidance render without page errors. The expanded suite passed 65 tests including mocked 429 recovery and quick-reply paths; one existing pytest warning remains.

At the time of this test the selected default was Qwen/Cerebras with `provider_recovery=false`. The retry policy cannot increase upstream provider capacity or account limits. Do not report that endpoint-side rate limiting has been fixed. Separate TTS verification failures were also observed and remain a possible source of incomplete speech.

After the restart, an authored HTTPS browser test exercised two real HTTP 429 responses. Their metadata identified `upstream_provider_shared_pool`; two 8-second waits were followed by a successful Cerebras response. First LLM token arrived at 17.23 s and first PCM at 18.31 s; TTS first PCM after admission took 0.92 s. Eleven PCM chunks were received, but a later sentence failed the parallel verifier after three speech attempts, so this was **not** a complete spoken end-to-end success. The test shows successful 429 recovery and a remaining independent TTS reliability problem, not a general latency or quality guarantee. A separate browser test injected synthetic UI status events to verify retry progress, clearing stale answers and the final 429 message. Podcast jobs continued and were not interrupted.
