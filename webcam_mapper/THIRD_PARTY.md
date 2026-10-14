# Sources and redistribution

The application and bundled `cartoon_face` renderer source use the repository's MIT license, included at the bundle root as `LICENSE`.

MediaPipe is installed from PyPI as `mediapipe==0.10.35`. Its code is distributed under Apache 2.0. The task model is the pinned version-1 official Google Face Landmarker bundle, not a model trained by this project. The download script checks its SHA-256 and writes a provenance sidecar. Model cards and usage information are linked from the official [Face Landmarker overview](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker). The model card terms govern the model; the repository's MIT license does not relicense it.

- Model URL: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
- SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`
- Size: 3,758,596 bytes.
- [MediaPipe Python task guide](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python) documents the Tasks API, CPU delegate, timestamps, face mesh and subject-side blendshape names.
- [MediaPipe code license](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE).

The verification photograph is NASA's astronaut Eileen Collins image, obtained through `skimage.data.astronaut()`. The [scikit-image documentation](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut) identifies it as public domain with no known copyright restrictions. The photograph is used only for reproducible local verification. One photograph and its crops/repeated frames are one human subject. The laptop source ZIP does not include this photograph or recorded camera input.

Other runtime dependencies retain their upstream licenses: NumPy, SciPy, Pillow, CairoSVG, Flask, and MediaPipe's transitive dependencies including OpenCV. They are installed by pip; their third-party source is not vendored into the ZIP. The native Cairo runtime is required by the existing renderer. See [CairoSVG installation documentation](https://cairosvg.org/documentation/).
