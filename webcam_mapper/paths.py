"""Resolve shared source in the checkout and the standalone laptop bundle."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))
DEFAULT_MODEL = ROOT / "webcam_mapper" / "models" / "face_landmarker.task"
