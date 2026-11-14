# Robby: tools, expressions and verification controls

Updated 2026-11-14. Live page: https://diane-asylum-understood-invoice.trycloudflare.com/desk-robot/ . Scroll below **all settings** for three SVG diagrams and an expandable capability catalogue. The existing tunnel and TTS/podcast processes are reused.

## Why some requests were only acknowledged

The fast streaming director and the JSON tool director did not expose the same capabilities. Keyword-only routing missed implicit research requests, some facial synonyms and wake-addressed commands. `ernst/serious` had no authored-pose alias. A provider could emit introductory text before a function call; a router which considered only pre-text calls lost that action. These are distinct failures from GPU generation or rendering.

`tool_capabilities.py` now supplies both prompts with the same capability description. `avatar_commands.py` handles clear requests immediately through the existing bounded validator, including Robbie/Robby/Robbi addresses, serious faces, puppy eyes, cheek puffing, blinks, whole-body flips and repeated commands. The first action ID is retained so later reply metadata cannot replay it. Indirect wishes such as wanting to see an eye movement also reach the command/tool path. Eye movement is explicitly distinguished from head rotation. A new tiny `use_tools` function in the streaming director can request the existing real tool director for paraphrases not covered by fast rules. It executes nothing itself. The director resolves arguments from the current request and recent conversation, validates them, and returns tool results before presenting facts or performing choreography. An empty or cue-only streamed answer receives one bounded full-director recovery instead of silently completing the turn. This extra model round trip is needed only for that fallback, not ordinary conversation or recognized direct actions.

Animations are screen effects. Physical motors, purchases, account actions, shell execution and arbitrary browser control are not available. Negated, quoted and hypothetical requests do not trigger the direct-command parser. Client action-disable/reduced-motion preferences remain authoritative.

## Capability inventory

The generated `/static/tool-catalogue.json` includes actual schemas, all 13 animation kinds, all 40 emotion IDs, 8 grimace variants and example requests. `render_system_guide.py` builds it from the validators rather than inventing a separate list.

- `perform_avatar`: emotion, nod, shake, spin (head/body), somersault (forward/backward), carousel, afterglow, puppy, pet, eye_roll, grimace, wink, curious. Maximum six steps and 24 seconds per sequence. Whole-body stunts include the platform. Serious/ernst means the existing concentration pose; it is not a new 41st emotion.
- `search_wikipedia`: short German/English encyclopedia extracts with actual links.
- `search_news`: publisher RSS feeds (Tagesschau, BBC, DW, Deutschlandfunk, Guardian). Generic “latest/current headlines” is not treated as a topical keyword filter. An empty query selects current headlines; topic filtering is not exhaustive search.
- `get_weather`: Open-Meteo forecast for a supplied city, with ambiguity checks. Not a measured local weather sensor.
- `search_web`: bounded public search through the existing encrypted OpenRouter credential and the documented Exa web plugin. Only a short topical query is sent; no microphone data, voiceprints or full dialogue. Return provider URL annotations/extracts, not an uncited generated answer. Maximum three search results. This incurs search and model charges on the configured account, including when the main conversation model is local. User-supplied OpenRouter credentials are respected when the main transport is remote.
- `set_interruption_rule`, `set_semantic_interruption_rule`, `clear_interruption_rules`: explicitly requested session rules, enforced by the existing authorization and decision controllers. The director may select the literal or semantic schema; it no longer forces every condition into literal keywords. Ordinary “Stop / Halt / Warte bitte” still uses the independent live interruption path.

Speaker enrollment, permissions, persistent wiki memory, voice isolation, camera/gaze and idle play use their existing session APIs. They are not fictitious LLM tools. Large requests and poems retain the existing complete-answer/continuation logic.

### Web retrieval implementation and limits

Public search-page probes returned bot challenges or irrelevant results on this host. Those were **not** accepted as verified facts and no challenge was bypassed. The implemented route uses [OpenRouter's documented web plugin](https://openrouter.ai/docs/guides/features/plugins/web-search). The old [Bing Search API was retired](https://learn.microsoft.com/lifecycle/announcements/bing-search-api-retirement); this demo does not claim to use that API or an unrestricted headless browser.

The search plugin supplies its own system context. An additional system message made Cerebras reject some searches with “System message must be at the beginning.” The retrieval request therefore uses a single bounded user message. Tool results remain untrusted source data. External links must be public HTTPS URLs; the application does not fetch arbitrary destination URLs. Search failure, missing source annotations and empty extracts remain explicit limitations. A URL alone is not evidence for facts absent from its extract. Source links are displayed, not read aloud. This small retrieval call adds network and model latency; it is not on every turn.

## Speed & verification controls

The new section is below the existing settings. Choices persist in this browser and are sent on each WebSocket connection. The server validates booleans and snapshots output options for the next turn.

| Control | Default | What runs | Trade-off when disabled |
|---|---|---|---|
| Selected second ASR after speech pause | On | The chosen Parakeet/other recognizer refines the utterance; unchanged speculative work is reused | Native Nemotron remains the final transcript pass. Potentially less recognizer work, possibly weaker German transcription, including the wake phrase. This is **not** raw unfinished-preview submission. |
| Check generated speech before playback | On | Parallel ASR verifies opening words, follows ordered target words and cuts/fades the end | Earlier raw PCM, but wrong words, gibberish lead-in and trailing sounds may become audible |
| Older serial output check | Off | Serial checker, for comparison with the normal sentence stream | Parallel mode usually starts earlier; this switch is not a second additional checker |

Changing the input recognizer-check option invalidates pending old recognizer work without discarding the collected utterance. The neural speech-pause guard, fresh-audio/backlog tests, wake window, speaker identity/permission checks, echo handling and stop path stay active. This does not disable security, authentication or network safeguards.

The optional two-stream quick-reply engine obeys the output-check on/off choice but retains its own checker; the serial-comparison option does not change that batch engine. Pre-generated brief interruption acknowledgments keep their existing cache/verification behavior. Existing voice-caption/isolation/speaker/quick-reply controls remain available and explained separately.

## Diagrams and timing interpretation

`system-conversation.svg`: audio, identity, pause, ASR, LLM, TTS and playback; independent interrupt path.

`system-tools.svg`: direct command path versus model interpretation and validated real tool execution.

`system-latency.svg`: latency dependencies and the raw/parallel/serial trade-off. Illustrative flow, **not a measured timeline**. Historical RTX 3090 medians are explicitly dated Nov 13; current browser receipts must be consulted for this update. First server PCM is not the same as audible end-to-end response. Provider/network time, generated phrase, speaker matching and browser buffering vary. A faster raw stream does not establish equal quality.

Native SVGs add no model or rendering library. They are accessible images in horizontally scrollable containers on small screens. The catalogue and diagrams live outside the conversation layout at the bottom; controls retain their existing event handlers.

## Reproducing the checks

From `robo-integration`, using the existing production Python:

```bash
/home/c4r33u19/moss15v2/.venv/bin/python -m pytest -q test_tool_capabilities.py test_avatar_actions.py test_avatar_commands.py test_bolt.py test_speech_retry.py test_llm_backends.py test_knowledge_tools.py test_conversation_prompt.py test_sentence_reliability.py test_pause_endpoint.py
/home/c4r33u19/moss15v2/.venv/bin/python validate_tools_live.py
/home/c4r33u19/moss15v2/.venv/bin/python validate_tool_followups_live.py
/home/c4r33u19/.local/bin/uv run --no-project --with playwright --python /home/c4r33u19/moss15v2/.venv/bin/python browser_tools_audit.py
/home/c4r33u19/.local/bin/uv run --no-project --with playwright --python /home/c4r33u19/moss15v2/.venv/bin/python browser_tools_microphone.py
```

The unit tier contains explicit mocks for contract testing only. The live tier uses actual Qwen/Cerebras and real public source calls, with TTS disabled to isolate routing. The HTTPS browser tier uses actual generated PCM, validates rendered poses/body angles, all 40 authored pose controls, 8 grimaces, tool sources, verification switches, persistence and mobile diagrams. Microphone-tier fixtures are authored synthetic speech, not private recordings. Do not call any of these a real-room multi-person evaluation.

Receipts: `logs/tools-audit-unit-final.log`, `logs/tools-live-20261114.json`, `logs/tools-browser-20261114.json`, `logs/tools-guide-mobile-20261114.png`. Failed first attempts remain in the live test logs; they motivated corrections, including the generic headline query bug and the search-plugin format issue. API rate limits are a separate service failure, not a successful test. Run live model tests sequentially, not simultaneously with another API stress test.

## Services and restart

Main app: `server.py`, `127.0.0.1:8793`; existing tunnel serves `/desk-robot/` and `/static/…`. TTS remains on 8792; podcast on 8816. Check `.runtime/server.json` and `manage.py status` before stopping anything. Restart only the owned Robby process, preserving its deployed environment; `.runtime/restart-robby-preserving-env.py` is a local operator helper, not a portable deployment recipe. Warm-up takes about 80 seconds on this host. Do not kill the TTS, podcast, ASR sidecars or tunnel to deploy prompt/UI changes. Credentials remain encrypted outside the source tree. No API keys belong in reports or public artefacts.

Observed negative control: with the second recognizer disabled, native Nemotron transcribed one authored German “Hey Robby” fixture as “Hey Hobby”; the unchanged wake gate correctly ignored it. This failure is retained in `logs/tools-microphone-native-wake-failure.json`. Do not claim that disabling the recognizer preserves German wake-word reliability or always reduces latency. The default second recognizer remains enabled.

The native English microphone probe also exposed the split transcription “somer salt”. That phrase now maps to the existing somersault action, so it cannot merely receive a verbal promise. The failed pre-fix receipt is retained in `logs/tools-microphone-native-split-word-failure.json`. The final microphone tier uses a German grimace request with Parakeet and an English somersault request with native Nemotron.

## Final deployment results, November 14

- 131 regression checks passed (one existing pytest warning about a test returning a value).
- The 18-case real-model tier passed 17 cases; the final case hit provider HTTP 429. That case subsequently passed in the separate five-case follow-up tier, alongside actual literal/semantic rule installation and clearing. The failed receipt remains intact.
- Ten real HTTPS typed turns passed with generated PCM, actual animation frames or source links. The same browser run checked all 40 authored emotion patterns, eight grimaces, three verification modes, persistence and the mobile diagrams.
- Both final synthetic-microphone cases passed on the deployed process: German grimace via Parakeet, English somersault via native Nemotron. The second case confirms the split-word ASR fix and a complete visible flip. This does not establish German reliability with the second recognizer disabled.
- The original TTS, podcast and Cloudflare tunnel were preserved. Robby and TTS reported ready; the podcast health endpoint reported healthy. No GitHub publication was performed in this update.

An additional literal-speech regression is reproducible with `browser_tools_final_smoke.py`. It checks that “Sag genau: Ich warte auf die Freigabe.” produces spoken PCM, without an animation or text suppression by a tool-preamble heuristic. Its receipt is `logs/tools-final-smoke-20261114.json`.

That additional browser attempt could not acquire the single conversation slot while a live conversation was active (first attempt timed out; the improved test captures the busy connection immediately). It is **incomplete**, not a passing end-to-end result, and the active conversation was left running. A separate actual Qwen/pipeline call with TTS disabled passed the literal-text regression, recorded in `logs/tools-literal-model-20261114.json`. The ten-turn browser suite and final two microphone cases above had already completed successfully.

### Main changed files

`tool_capabilities.py`, `avatar_commands.py`, `avatar_actions.py`, `conversation_prompt.py`, `conversation_director.py`, `bolt_director.py` and `bolt_pipeline.py` contain capability alignment and routing. `knowledge_tools.py` and new `web_lookup.py` contain retrieval. `verification_settings.py`, `sentence_session.py`, `server.py`, `tts_bridge.py` and `live_speech.py` propagate the optional checks. Browser controls and diagrams are in `static/verification-controls.js`, `static/asr-controls.js`, `static/ui.js`, `static/system-guide.js`, `static/style.css` and the three generated SVGs. `render_system_guide.py`, `render_tools_audit.py`, `tool_audit_worklog.py` and `build_worklog.py` maintain the catalogue and reports. The test commands above identify the added verification scripts.
