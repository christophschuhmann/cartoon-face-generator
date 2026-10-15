"""Build an allowlisted laptop ZIP with the actual shared renderer dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from .paths import ROOT, DEFAULT_MODEL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "webcam_mapper/output/cartoon_webcam_mapper.zip")
    parser.add_argument("--include-model", action="store_true", help="Include the verified 3.76 MB official model for offline startup")
    args = parser.parse_args()
    candidates = list((ROOT / "webcam_mapper").glob("*.py"))
    candidates += list((ROOT / "webcam_mapper").glob("requirements*.txt"))
    candidates += [ROOT / "webcam_mapper/README.md", ROOT / "webcam_mapper/THIRD_PARTY.md", ROOT / "LICENSE", ROOT / "poses/smile.json", ROOT / "tests/test_webcam_mapper.py"]
    candidates += list((ROOT / "webcam_mapper/static").rglob("*"))
    candidates += list((ROOT / 'tests').glob('test_*tracking.py'))
    candidates += [ROOT/'tests'/name for name in ('test_empathic.py','test_audio_performance.py',
                    'test_speech_assist.mjs','test_head_follow.mjs')]
    candidates += [ROOT/'webcam_mapper/models/ears'/name for name in (
        'training_normalization.json','display_normalization.json','LICENSE','NOTICE.md',
        'medium/speech_reference.json','medium/REFERENCE-LICENSE.md')]
    # Keep one renderer and its real helpers, not a second copy of vector code.
    module_names = ("__init__", "model", "geometry", "renderer", "emotion_library", "animation", "expressions", "reference", "under_eye", "projection", "social_expressions")
    candidates += [ROOT/'Start-Avatar.cmd',ROOT/'Start-Avatar.ps1',ROOT/'tests/test_expression_upgrade.py',ROOT/'tests/test_avatar_motion.mjs']
    candidates += [ROOT / f"src/cartoon_face/{name}.py" for name in module_names]
    candidates += list((ROOT / "src/cartoon_face/components").glob("*.py"))
    candidates += list((ROOT / "src/cartoon_face/topology").glob("*.json"))
    candidates += list((ROOT / "src/cartoon_face/emotions").glob("*.json"))
    if args.include_model:
        from .download_model import MODEL_SHA256
        if not DEFAULT_MODEL.exists() or hashlib.sha256(DEFAULT_MODEL.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("Verified official model unavailable; run python -m webcam_mapper.download_model")
        candidates += [DEFAULT_MODEL, DEFAULT_MODEL.with_suffix(".source.json")]
    files = sorted({p for p in candidates if p.is_file()})
    missing = [p for p in candidates if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Bundle dependency missing: {missing}")
    manifest = {p.relative_to(ROOT).as_posix(): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in files}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "cartoon_webcam_mapper/" + path.relative_to(ROOT).as_posix())
        archive.writestr("cartoon_webcam_mapper/BUNDLE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"zip": str(args.output), "bytes": args.output.stat().st_size, "source_files": len(files), "includes_model": args.include_model}, indent=2))


if __name__ == "__main__":
    main()
