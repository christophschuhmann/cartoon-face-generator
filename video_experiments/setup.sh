#!/usr/bin/env bash
# Independent environment: leave the SVG editor and detector training untouched.
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
uv venv --python 3.12 video_experiments/.venv
mkdir -p video_experiments/vendor
if [ ! -d video_experiments/vendor/LTX-2/.git ]; then
  git clone https://github.com/Lightricks/LTX-2.git video_experiments/vendor/LTX-2
fi
git -C video_experiments/vendor/LTX-2 checkout be6d6d0a69d11a0a399c462ed92606692e5f8697
uv pip install --python video_experiments/.venv/bin/python --no-sources \
  -e video_experiments/vendor/LTX-2/packages/ltx-core \
  -e video_experiments/vendor/LTX-2/packages/ltx-pipelines \
  -e . -r video_experiments/requirements.txt
command -v ffmpeg >/dev/null || { echo 'Please install ffmpeg.' >&2; exit 1; }
