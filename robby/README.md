# Robby: an independent browser SVG robot

Robby is a cream-white, hand-authored vector robot with glossy eyes, subtle blush,
a warm heart light and a decorative cross. It was rebuilt for the Humaneness Voice
Playground from the user's visual brief. The source image is not embedded or traced.
This folder is a separate additive display rig: it does not change the existing
Python generator, 101-keypoint contract, forty-category taxonomy, webcam package,
detector or original saved poses. The expressions are authored animation cues,
not measured human-emotion classifications. No recognition-accuracy claim is made.

## Open the self-contained browser showcase

From the repository root:

```bash
python -m http.server 8767 --bind 127.0.0.1
```

Open <http://127.0.0.1:8767/robby/>. No npm build, Python dependencies or GPU is
needed. Sliders work offline after the page and SVG are loaded. Camera access
requires localhost or HTTPS and an explicit click. The optional camera tracker
runs entirely in the browser; no camera pixels or face landmarks are uploaded.
It is a visual mirror, not a detector trained on this robot.

Tracking downloads `@mediapipe/tasks-vision@0.10.21` JavaScript/WASM from jsDelivr
and Google's float16 Face Landmarker model. External hosts receive ordinary
download requests. MediaPipe software is Apache-2.0; separately review the
[upstream model terms](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)
before redistribution. No third-party model weights are included here.
The existing [CPU mapper](../webcam_mapper/README.md) remains unchanged.

## Embed in a voice application

Use `robby.svg` directly as an image, or fetch this trusted local SVG into a DOM
container and pass its `<svg>` element to the dependency-free ES module:

```js
import {createRobbyRig, controlsFromFace} from './robby/rig.js';
const rig = createRobbyRig(document.querySelector('#robot svg'));
// Call once per animation frame; normalized RMS from actual playback drives audioLevel.
rig.update({smile: 0.3, audioLevel: 0.2, roll: 8}, 16.7, performance.now());
// Or use a MediaPipe FaceLandmarker result: rig.update(controlsFromFace(result), dt, now).
```

The module clamps finite controls and smooths them using elapsed time, rather than
depending on screen refresh rate. `x`/`y` are bounded gaze/head offsets [-1,1],
`roll` is [-35,35] degrees, and `smile`, `jaw`, `blinkLeft`, `blinkRight` and
`audioLevel` are [0,1]. Invalid numeric input becomes zero. Here left/right mean
**image space**. MediaPipe's anatomical blink categories are explicitly swapped
for the mirrored display. These IDs do not belong to the original 101-keypoint
topology and must not be mixed with it.

Stable SVG IDs: `body`, `head`, `eye-left`, `eye-right`, `brow-left`, `brow-right`,
`smile`, `mouth-open`, `heart`, `heart-halo`. Add one SVG per DOM scope to avoid
colliding internal gradient IDs. This is an energy-driven mouth animation, not
phoneme alignment or lip-sync accuracy. Audio capture, Luna, Humaneness TTS,
TYGER, speaker identity and playback synchronization belong to the host app;
the standalone showcase neither records audio nor calls a hosted LLM.

## Verification and license

The robot geometry was rendered and visually checked alongside the supplied
brief. Repository tests check its finite geometry, unique IDs, absence of embedded
raster assets/scripts and preservation of the original rig. Browser checks cover
sliders, reset, finite bounded controls, mirror mapping and missing-ID errors.
Actual physical-camera tracking depends on browser/device availability; a fake
camera is not proof of a real-world facial-tracking accuracy measurement.

The new SVG, JavaScript and HTML are original project contributions under the
repository's [MIT license](../LICENSE). No private microphone recordings,
speaker voiceprints, access tokens, TTS weights or face-model weights are included.
