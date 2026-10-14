"""Check repository-relative Markdown links, optionally against Git-tracked files.

Network links are deliberately not fetched. Generated files that happen to exist
locally cannot conceal a broken published link when --tracked-only is enabled.
Run from any directory: python tools/check_docs.py --root REPO --tracked-only.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit


def check(root, tracked_only=False):
    root = Path(root).resolve()
    if tracked_only:
        files = {
            (root / name).resolve()
            for name in subprocess.check_output(
                ["git", "ls-files", "-z"], cwd=root
            ).decode().split("\0") if name
        }
    else:
        folders = ("docs", "training", "webcam_mapper", "output", "poses", "viewer", "src")
        files = set(root.glob("*.md"))
        for folder in folders:
            files.update(p for p in (root / folder).rglob("*.md")
                         if not any(part.startswith(".venv") for part in p.parts))
    markdown = sorted(path for path in files if path.suffix == ".md")
    broken, count = [], 0
    for path in markdown:
        text = re.sub(r"^```.*?^```\s*$", "", path.read_text(), flags=re.M | re.S)
        for match in re.finditer(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", text):
            target = match.group(1).strip().split(' "', 1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            count += 1
            dest = (path.parent / unquote(parsed.path)).resolve()
            exists = dest.exists() if not tracked_only else (
                dest in files or any(dest in file.parents for file in files)
            )
            if not exists:
                broken.append({"file": str(path.relative_to(root)), "target": target})
    return {"markdown_files": len(markdown), "relative_links": count,
            "tracked_only": tracked_only, "broken_links": broken}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tracked-only", action="store_true")
    args = parser.parse_args()
    result = check(args.root, args.tracked_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["broken_links"]))
