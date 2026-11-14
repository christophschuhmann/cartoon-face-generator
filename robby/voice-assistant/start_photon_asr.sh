#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export CUDA_VISIBLE_DEVICES="${ROBO_PHOTON_GPU:-1}"
export OMP_NUM_THREADS=4 HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1
exec "${ROBO_PHOTON_PYTHON:-$HOME/.cache/robby-photon/venv/bin/python}" -m uvicorn photon_asr_worker:app --host 127.0.0.1 --port 8822 --no-access-log
