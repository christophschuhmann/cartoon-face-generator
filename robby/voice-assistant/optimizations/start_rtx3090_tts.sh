#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a
source ./rtx3090-speed.env
set +a
exec "${ROBBY_TTS_PYTHON:-python}" -m uvicorn small_app:app --host 127.0.0.1 --port 8792 --timeout-graceful-shutdown 5
