# Whole-body tricks and spoken reactions — 13 November 2026

The desk robot supports a full body turn and one forward/backward somersault.
These are browser animations. Mechanical gaze tracking still has its existing
pan/tilt limits, and no hardware commands are sent.

## Requests and tool contract

| Request | Validated action |
|---|---|
| Dreh dich mal im Kreis. | `spin`, `scope: body`, `direction: clockwise` |
| Dreh dich gegen den Uhrzeigersinn. | `spin`, `scope: body`, `direction: counterclockwise` |
| Dreh deinen Kopf. | `spin`, `scope: head` |
| Mach mal einen Salto. | `somersault`, `direction: forward` |
| Mach einen Salto rückwärts. / Do a backflip. | `somersault`, `direction: backward` |

`perform_avatar` exposes the same allowlisted actions to the LLM. Direct commands
are also recognized deterministically and dispatched once before LLM generation.
This prevents a prose promise from replacing an actual action. The action ID
deduplicates subsequent reply metadata. Quoted examples, negated commands and
conditional instructions do not execute through the direct-command path.
For spoken turns, the client starts the trick at actual first audio playback,
with a four-second maximum wait if speech is unavailable. Silent requests and
UI previews start immediately. A planning/speech error does not cancel a valid
pending trick; explicit Stop, interruption and reduced-motion settings still do.
Sequences remain bounded to six actions and 24 seconds. Normal full-body turns
last six seconds; a somersault lasts 4.8 seconds. Explicit head-only requests and
existing unscoped/idle head motions retain their prior behaviour.

## Rendering

The existing CPU software renderer receives a shared outer transform after head
articulation. Platform, neck, head, face texture, surface normals and visibility
tests all use it. This is not a CSS rotation of the page or a head-only tilt.
Somersault phases are crouch, airborne 360-degree flip and soft landing, with
bounded squash and a small automatic camera pullback. The normal camera/view
settings return after the trick. Head gaze follows its original controller.
Temporary petting expressions retain the requested body movement.

The renderer's body cache includes every stunt transform and framing parameter.
During a whole-body stunt, the raster's longest edge is capped at 360 pixels to
bound CPU pixel work. CSS display size is unchanged and normal resolution returns
afterward. The original SVG avatar has a flat whole-body cartoon fallback; only
the desk view performs the real virtual 3-D yaw/flip transformation.
Snapshots expose `bodySpin`, `bodyFlip`, `bodyLift`, `bodySquash`, `baseCenter`
and `baseFront` for actual geometry assertions. These are virtual scene units,
not a physical robot dynamics model. Reduced-motion settings suppress rotations
and jumps. The explicit-actions checkbox and Stop animation remain effective.

## Reproduced failure and speech fix

The initial live request “Dreh dich mal im Kreis” did emit a spin action and
rotate the head almost 360 degrees. It did **not** move the platform. The model
then returned only a Markdown stage direction, `*Robby dreht sich ...*`, rather
than a spoken response; speech verification rejected it on all three attempts.
The negative receipt is `logs/stunts-before-20261113.json`.

For explicitly requested actions, sentence framing now holds incomplete marked
spans across token boundaries and discards recognized third-person stage
directions. Ordinary emphasized speech stays intact. Narrative output outside
action requests is unchanged. An entirely nonverbal response reaches the
existing one-retry LLM path, with a clear request for actual spoken words; the
animation is not duplicated. The prompt explicitly asks for first-person spoken
reactions during tricks. The TTS word-verification requirement is not relaxed.

Two later live passes exposed a second case: laughter-only output (`Haha!`) and
two consecutive nonverbal completions. Preserve
`stunts-body-browser-20261113-initial.json` and
`stunts-body-browser-20261113-nonverbal.json` as negative receipts. Generic
laughter/whoops alone now trigger the same bounded retry before any TTS request.
One/two-word fragments such as `ACH!` are also held out of standalone TTS jobs
for direct visual requests: a following complete phrase is used, otherwise the
same bounded repair runs. This avoids spending three speech retries on a grunt.
After two unusable completions, an explicit local acknowledgment prevents a
silent planning failure; its use is recorded as
`visual_acknowledgment_fallback=true`. This fallback is limited to direct visual
requests. Optional petting/idle dialogue keeps its existing LLM-generated path.
Explicit requests to say/shout particular words are not filtered as generic
interjections. A successful screen action does not establish completion of an
additional requested poem or other verbal task.

HTTP provider failures now retain their status in a sanitized `HTTPStatusError`,
so the existing bounded retry recognizes transient failures. Previously they
became a generic `RuntimeError` and bypassed that retry. An unspoken direct
visual request can use the same acknowledgment after exhausted transient
provider retries; partial spoken answers are never replayed. Authentication and
other nonretryable errors remain errors. Test doubles cover 503 recovery and
ensure provider error bodies do not leak. The old untyped live failure is
retained without claiming a recoverable HTTP status that was not recorded.

## Reproduction

Final validation: **69 unit tests passed**, including the updated provider-error
transport checks. All **six typed public-browser requests** and **two authored
microphone requests** passed with real LLM/TTS and ASR where applicable. Every
request had audible playback during its visible animation. The final typed run
used LLM-generated reactions for all six requests; the local fallback was
tested deterministically rather than forced into production measurements.
Receipts: `logs/stunts-body-browser-20261113.json` and
`logs/stunts-body-spoken-20261113.json`; summary and limitations are available at
`/static/whole-body-stunts.html` on the existing tunnel.

On this headless, CPU-rendered test host, median render calls during the four
body tricks were approximately 124–138 ms. This is a material browser-side
cost, not a 30/60-fps claim. The initial uncapped runs were about 146–182 ms,
but those were separate request runs rather than a matched rendering benchmark.
No physical microphone or room-echo evaluation is implied by these tests.

Run from `robo-integration` with the production Python environment:

```bash
python -m pytest -q test_avatar_actions.py test_avatar_commands.py test_bolt.py test_speech_retry.py
uv run --no-project --with playwright --python /home/c4r33u19/moss15v2/.venv/bin/python browser_whole_body_stunts.py
uv run --no-project --with playwright --python /home/c4r33u19/moss15v2/.venv/bin/python browser_whole_body_spoken.py
```

The browser test uses the public HTTPS desk-robot page, real Qwen/Cerebras and
verified streamed TTS. It tests both spin directions, forward/backward flips,
anger and grimaces, including speech during the action. Independent renderer
assertions verify that the platform rotates, the body crouches and lands, and
reduced-motion/cancellation controls work. It uses authored requests, not private
microphone recordings. Only one browser conversation test may run at a time.

Files: `avatar_actions.py`, `avatar_commands.py`, `bolt_text.py`,
`bolt_director.py`, `bolt_pipeline.py`, `llm_backends.py`,
`static/avatar-actions.js`, `static/desk-robot3d.js`, `static/rig.js`,
`static/avatar-action-controls.js`, `static/ui.js`, `static/avatar-manual.html`.
Restart only Robby after Python changes; keep TTS, ASR sidecars, podcast and the
existing tunnel running. Reload the browser page to load the updated modules.
