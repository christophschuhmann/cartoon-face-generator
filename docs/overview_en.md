# English overview

[Documentation index](README.md) · [Repository map](repository_map.md)

This project provides one reusable, parametric SVG cartoon face with **101 stable semantic landmarks**, six fitted reference poses, **40 EmoNet-Face expression recipes** and **60 additional authored social/cartoon expressions**. Brows are raised, eyes blink, pupils move and the characteristic curled cheek lines deform through the same shared rig.

## Start the generator and editor

Tested on Linux with Python 3.12. CairoSVG needs the system Cairo library (`libcairo2` on Debian/Ubuntu).

```bash
git clone https://github.com/christophschuhmann/cartoon-face-generator.git
cd cartoon-face-generator
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/face render --pose poses/smile.json --output output/my_face.svg --png output/my_face.png
.venv/bin/face serve --port 8766
```

Open `http://127.0.0.1:8766`. The galleries are `/emotions` and `/social`. The browser calls the Python renderer; it does not implement another face model. See [getting started](getting_started.md) for Windows, macOS, installation alternatives and troubleshooting.

## Where to look

| Goal | Location |
|---|---|
| See every archetype | [40 EmoNet](../output/emonet/archetypes), [60 social](../output/social/archetypes) |
| Download all 660 preview states | [expression_previews.zip](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.0.0/expression_previews.zip) |
| Understand each of the 101 landmark IDs | [topology guide](topology.md), [numbered atlas](landmarks/overview.png) |
| Understand complete pose JSON | [data format](data_format.md), [real example](../poses/smile.json) |
| Generate, vary and mix expressions | [CLI cookbook](cli.md) |
| Use a human webcam to drive the avatar on CPU | [MediaPipe mapper](../webcam_mapper/README.md), [standalone ZIP](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.0.0/cartoon_webcam_mapper.zip) |
| Train or run the cartoon landmark detector | [training guide](../training/README.md), [checkpoint](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.0.0/cartoon_landmarks_best.pt) |
| Create the 105,000-pose dataset and exact-label augmentations | [dataset guide](dataset.md) |
| Modify the implementation | [architecture](architecture.md), [contributing](../CONTRIBUTING.md) |

## Essential conventions

Landmark IDs are 0–100. Left/right refer to the **character's** side. Coordinates are normalized `[u,v]`; rig lengths are canonical pixels in 1450 × 750 space. Invisible landmarks retain their identity and coordinates. A complete renderable pose contains coordinates **and** widths, tangents, variants, geometry and visibility; predicted points alone cannot recover all SVG geometry.

The generator, cartoon detector and human webcam mapper serve different purposes. The webcam mapper uses MediaPipe CPU signals to author a pose; it does not use the trained cartoon detector. Neither component claims emotion classification accuracy.

The 105,000 SVG/JSON pairs use about 7 GB compressed and are intentionally excluded from Git. The extended detector search adds 32,000 training poses and four runs with 40 additional epochs, preserving the same evaluation files. At 320 × 192 the robust model reaches **0.330 px normal / 10.291 px extreme OOD**; the precise alternative **0.209 / 11.901 px**. The original baseline was 0.231 / 15.620 px. The robust original-reference check reaches 1.700 px; synthetic variations of those rig-pose families now appear in training. Read [the measured results and scope](detector_results.md) and [search protocol](detector_search.md). The expression labels are intended designs without measured human recognition accuracy. Live laptop webcam performance has not been measured.

Separate [LTX-2.5 video experiments](../video_experiments/README.md) provide genuine speaking cartoon videos with first/last/intermediate SVG conditions, fast schedules, a real distilled LoRA comparison and measured runtimes. These raster videos do not supply exact landmarks for generated intermediate frames. External LTX code and weights have their own Community License.

Project code is [MIT licensed](../LICENSE); external model and test-image provenance are documented in [THIRD_PARTY.md](../webcam_mapper/THIRD_PARTY.md).
