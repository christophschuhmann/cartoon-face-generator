# Matching TTS runtime source snapshot

Text-only sources from the deployed TTS service, 14 November 2026.
`humaneness-small/` includes Small/Large serving, the legacy chunk search, CUDA
optimizations and experiment scripts. Parent modules preserve relative imports.

Robby uses [Small 1.1 Alpha RL r128](https://huggingface.co/laion/Humaneness-Voice-Small-1.1-Alpha-RL-r128-v1).
[Large1.7](https://huggingface.co/laion/Humaneness-Voice-Large-1.7) is optional if
VRAM permits. acting_models.py/settings.py/checkpoint loaders pin revisions and
validate weights. [Base model](https://huggingface.co/laion/Humaneness-Voice-Small)
contains upstream model/inference dependencies. Existing third-party and model
licenses apply; this snapshot grants no new rights to weights or reference data.

Follow the parent Robby setup/optimization guides, preserve this parent/child
layout, install dependencies in a separate environment, configure asset/cache
paths and run `uvicorn small_app:app` in humaneness-small/ on loopback8792.
The workstation run.sh and optimization environment contain absolute machine
paths and are examples, not portable installers. Do not run deployment or
benchmark helpers blindly on a shared host.

No weights, private settings, runtime state, recordings or credentials are
included. Historical experiment scripts may need separately documented datasets.
This is a source snapshot, not a claim that every historical experiment or
optional model is currently deployed or reproduced from a clean machine.

## Causal candidate streaming

The matching `search_asr` endpoint, batched codec graph implementation, test code
and benchmark guide are included in this snapshot. See
[ASR_CANDIDATE_STREAMING.md](../ASR_CANDIDATE_STREAMING.md) for exact flags, model
revision, metrics and limitations. `SMALL_WARM_CONTINUOUS=1` opts into eagerly
warming the optional quick-reaction batcher; otherwise it initializes on use.
Normal streaming still warms before readiness. Candidate GPU shapes need an
additional prewarm request before a live demonstration.
