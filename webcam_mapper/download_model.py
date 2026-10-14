"""Download the pinned official Google model, without any account/token."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
from .paths import DEFAULT_MODEL

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
DOCUMENTATION_URL = "https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker"


def download(destination=DEFAULT_MODEL):
    destination = Path(destination)
    if destination.exists():
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        if MODEL_SHA256 and digest == MODEL_SHA256:
            return destination
        if MODEL_SHA256:
            raise ValueError(f"Existing model checksum mismatch: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response, temporary.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if MODEL_SHA256 and digest != MODEL_SHA256:
            raise ValueError("Downloaded official model failed SHA-256 verification")
        temporary.replace(destination)
        destination.with_suffix(".source.json").write_text(json.dumps({
            "url": MODEL_URL, "sha256": digest, "bytes": destination.stat().st_size,
            "documentation": DOCUMENTATION_URL,
            "license_note": "Official Google MediaPipe model bundle; consult the linked model cards and terms.",
        }, indent=2) + "\n")
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    path = download(args.output)
    print(f"Model ready: {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
