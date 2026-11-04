# Robby actions and emotional acting: fixes and tests (4 November 2026)

## Behavior

Direct commands now cover noun forms such as “Mach eine Drehung”, “Führe eine Drehung durch”, “Kannst du eine Drehung machen?” and “Ich möchte, dass du eine Drehung machst”. Both clockwise and counterclockwise virtual yaw turns are supported. The existing validated action channel starts the screen animation immediately, independently of whether the LLM merely announces the action. It controls the browser avatar, not a physical motor.

All forty canonical expression names have German noun/adjective aliases. Examples include “Zeig mir Wut”, “Du sollst mal wütend sein”, “Stell Enttäuschung dar”, “Zeig mir Ehrfurcht”, and “Show anger”. In ordinary German commands, “sauer” maps to anger; “säuerlich” or the canonical sourness label selects the separate sourness pose. Negated commands, quotations, explanations, and feelings mentioned in a requested poem/story continue to avoid accidental action dispatch.

For a single requested emotion, the same canonical cue now drives the face and the actual TTS sentence, overriding a neutral cue accidentally returned by the LLM. Quiet or restrained acting requests can use the softer delivery; whisper requests retain their delivery cue. Complex action sequences keep the existing tool/controller path and validation limits.

The streaming director can use all forty emotion names. It is prompted to perform a short complete line, rather than returning only an emotion label or announcing the exercise. The model can still choose its wording; requests for exact supplied text retain priority.

## Humaneness Small prompting

`emotion_recipes.py` contains forty authored recipes and bilingual aliases. Every GENERAL template includes the reference-identity instruction, the named emotion, and specific momentary performance directions (pacing, emphasis, breathing, hesitation, release). For example anger uses tense, firm articulation and decisive pauses; sadness uses subdued breath, slower fragile phrasing and falling contours. Stable speaker characteristics are left to the reference audio.

The previous generic “gentle, subtle” instruction could weaken strong emotions. Soft recipes now call for a contained but recognizable emotion, while intense recipes call for vivid acting and clear diction. A named emotion takes priority over generic warmth or softness when choosing a template. This refines prompting, not model weights; it does not guarantee an audible forty-way distinction on every sentence.

## Reproducible verification

- `test_avatar_commands.py`: German noun commands, positive and negative examples, all forty German emotion names, and face/TTS agreement even when a mocked LLM returns a neutral cue.
- `test_bolt.py`: all forty TTS recipes preserve reference identity and select the requested canonical template. The existing framing, continuation and local-prefix tests remain.
- `browser_stunts_emotions_check.py`: actual HTTPS typed requests through Qwen, TTS and the 3D renderer. It checks two directed turns, four emotional requests and a grimace, then renders all forty poses through the action controller. Renderer yaw spans were about −361° to 0° and −0.2° to +359.3°; small differences come from the base head pose. This is a full visible turn, not just an action-event assertion. The forty pose check covers rendering/dispatch, not human emotion-recognition accuracy.
- `browser_spoken_stunts_check.py`: authored TTS requests supplied to Chromium as a synthetic microphone. “Hey Robby, mach eine Drehung”, a request for anger, and a request for sadness pass through the live ASR/wake/LLM/TTS/browser route. It checks actual audio packets and rendered action state. It does not test a physical microphone or a real noisy room.
- `validate_emotion_recipes.py`: six German samples with identical words, fixed Mira reference, seed 777, temperature 0.8 and CFG 2. The final samples all had zero Parakeet WER. Listen in `static/stunts-emotions.html`. Humaneness Ears captions are displayed as uncertain impressions; they often disagree with the target and are not used to claim emotional accuracy or rank the recipes. The first recipe probe is retained separately as `static/stunts-emotions-audio-initial.json`.

Run the unit suite with the configured TYGER source path. Browser checks use the public URL defined at the top of each script, Google Chrome and Playwright; change the URL when the temporary tunnel changes. Run actual GPU/browser checks serially. Test recordings are newly authored synthetic speech. No private user recordings or face profiles are included.

The existing expression opt-out, reduced-motion preference and calibration mode are respected. If expressive actions are switched off, the UI shows a warning; a spoken promise alone is not proof of a rendered action. Screenshots of anger, sadness, surprise and a half-turn were visually inspected; geometry was not changed.
