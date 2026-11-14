#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export CUDA_VISIBLE_DEVICES="${ROBO_SPEAKER_GPU:-1}"
export OMP_NUM_THREADS=2 HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1
exec "${ROBO_PYTHON:-python}" -m uvicorn ecapa_gpu_worker:app --host 127.0.0.1 --port 8823 --no-access-log
