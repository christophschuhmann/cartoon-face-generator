# Train the 101-point cartoon detector

[Repository overview](../README.md) · [Documentation index](../docs/README.md) · [Measured results](../docs/detector_results.md)

## Use the trained checkpoint first

Download [cartoon_landmarks_robust.pt](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.1.0/cartoon_landmarks_robust.pt) and save it as `output/detector_v3/best.pt`. Alternatively, save [cartoon_landmarks_precise.pt](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.1.0/cartoon_landmarks_precise.pt) as `output/detector_v3/best_normal.pt` for the lowest normal synthetic error. The weights are separate release assets; a source-code ZIP does not contain them. CPU installation and a complete first-prediction example are in [getting started](../docs/getting_started.md).

The robust model reaches **0.330 px normal / 10.291 px extreme OOD**, the precise model **0.209 / 11.901 px**, on the unchanged 320×192 test set. The original [15-epoch baseline](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.0.0/cartoon_landmarks_best.pt) remains available. See the [measured comparison](../docs/detector_results.md) for tradeoffs and limits.

| File | Responsibility |
|---|---|
| [model.py](model.py) | compact 101-heatmap network and visibility head |
| [prepare.py](prepare.py) | raster cache, disjoint source splits, clean/augmented holdouts |
| [train.py](train.py) | on-the-fly augmentations, training, checkpoint selection and test evaluation |
| [predict.py](predict.py) | CPU/GPU inference and original-image coordinates |
| [visualize.py](visualize.py) | Ground Truth versus predicted landmark comparison boards |
| [evaluate_references.py](evaluate_references.py) | separate evaluation of the six original illustration crops |
| [extra_variants.py](extra_variants.py) | 32,000 extra training poses; immutable old holdouts |
| [augmentation.py](augmentation.py) | stronger image/label transformations, training only |
| [search.py](search.py) | four longer-training profiles, validation selection and complete histories |
| [compare_search.py](compare_search.py) | lock selection before evaluating the unchanged test set |

The following sections describe the model and how to reproduce training. Dataset preparation is not required just to run inference.

This is the small supervised **cartoon-image** model. The separate [MediaPipe application](../webcam_mapper/README.md) maps a human webcam to the SVG avatar; it does not use this model.

`LandmarkNet` has 1,011,228 parameters. A compact convolutional encoder/decoder produces 101 heatmaps at one quarter of the input dimensions and 101 three-state visibility predictions. No human-face pretrained weights or expression classifier are required. Training uses spatial Gaussian distribution loss, an auxiliary coordinate loss and visibility classification. Visible landmarks have weight 1, occluded landmarks 0.35, absent/out-of-frame landmarks 0. Extreme OOD examples have weight 0.25 in the baseline; the extended search varies this weight explicitly.

## Reproduce the original baseline preparation and training

From the project root, generate the final v2 SVG dataset first. Install the ordinary project dependencies, then a separate PyTorch environment. The tested configuration is Python 3.12, PyTorch 2.6.0 + CUDA 12.4 on one NVIDIA A100. The [official PyTorch installation matrix](https://pytorch.org/get-started/previous-versions/) also provides CPU wheels. Core SVG/webcam generation does not depend on PyTorch.

```bash
uv venv .venv-training --python 3.12
uv pip install --python .venv-training/bin/python -e .
uv pip install --python .venv-training/bin/python torch==2.6.0 \
  --index-url https://download.pytorch.org/whl/cu124

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m training.prepare \
  --dataset datasets/cartoon_landmarks_v2 --output datasets/training_cache_v2 --workers 16

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-training/bin/python -m training.train \
  --cache datasets/training_cache_v2 --output output/detector \
  --epochs 15 --batch-size 128 --workers 12 --device cuda:0
```

Use `--device cpu` and a smaller batch/worker count for CPU-only training; no laptop training-time claim is made. `--resume output/detector/last.pt` resumes a matching dataset/architecture run. For the same 15-epoch schedule, pass the same epoch argument. Source/augmentation seeds are explicit. GPU arithmetic is not guaranteed bit-identical across different hardware or library versions.

The cache is grayscale storage at 320 × 192; every training read creates exactly one new RGB augmented image. A letterbox preserves proportions and leaves varying lower margins. Mild affine transforms, invertible sine shears, bilateral flip permutation, pastel background palettes, contrast changes, noise, slight blur/downsampling/JPEG and occasional small occluders are applied together with the exact label transform. Original source SVGs remain available.

## Extended search with more variants and stronger augmentation

The [complete search protocol](../docs/detector_search.md) documents 116,000 training source poses, four profiles with 40 additional epochs each, seeds, learning rates, OOD mixing, all measured results and frozen evaluation hashes. Training images change every epoch; evaluation images do not. Optimizers are restarted while the original baseline weights initialize each candidate. The model architecture and landmark topology remain unchanged.

## Holdouts and evaluation

Every expression reserves five unseen validation poses and five additional unseen test poses. Each has a clean and one fixed augmented image, giving 1,000 normal validation images and 1,000 normal test images. Each split also has 200 separately reported extreme OOD images. Training uses all 84,000 source poses from the train split. No held-out source ID, clean view or transformed view is used for training.

The original baseline selects checkpoints by normal validation normalized mean error. The new robust search uses a preregistered balanced normal/OOD validation score with a normal-error ceiling of 0.5 px; the precise alternative uses normal validation error. The test set is evaluated only after selection is locked. `output/detector/` retains the baseline and `output/detector_v3/` contains the new comparison. Training-run `last.pt` files additionally retain optimizer/scheduler/scaler state.

NME divides Euclidean landmark error by the full image diagonal. PCK@1/2/5% thresholds use that same diagonal. Absent and outside landmarks are excluded; occluded landmarks are included. Reports separate clean, augmented and OOD conditions, and include every category. These are synthetic-cartoon landmark metrics, not human emotion recognition or evidence of generalization to arbitrary cartoons or videos.

## Predict on another cartoon image

```bash
.venv-training/bin/python -m training.predict \
  --image path/to/cartoon.png --checkpoint output/detector_v3/best.pt \
  --device cpu --output output/prediction.json
```

Inference letterboxes RGB input, predicts all 101 positions, then maps them back into the original image's pixel space. Three visibility probabilities are returned per point. Preserve negative/outside coordinates and inspect confidence instead of silently clamping them. The output annotation is a prediction, not an independently reconstructed full SVG rig: widths, tangents and optional shape details are not uniquely determined by landmarks alone.

The [augmentation guide](../docs/dataset.md) documents schema and coordinate conventions. Tests cover Gaussian coordinate decode, output shapes, finite gradients, masking absent points, transformed label/image alignment, flip permutations and exact inverse warping.
