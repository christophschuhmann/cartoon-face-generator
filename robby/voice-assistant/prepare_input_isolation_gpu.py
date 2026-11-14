"""Download pinned public source/weights to the system disk, not the small NVMe.

Does not install packages or modify any running service. Read upstream licenses
before redistribution. Scicom weights declare license=other on their model card.
"""
import io
import json
from pathlib import Path
import tarfile
import urllib.request
from huggingface_hub import snapshot_download, hf_hub_download

ROOT = Path.home() / '.cache/robby-input-isolation'
ROOT.mkdir(parents=True, exist_ok=True)
VOX = '48b9a71e9b6ce853670c9a4dbc64ddb532638d53'
SCICOM = 'd41d6d8166a6566c9c2df7ca17e9ca38abcd35d6'
source = ROOT / 'voxlock-src'
source.mkdir(exist_ok=True)
url = f'https://api.github.com/repos/arbazsiddiqui/voxlock/tarball/{VOX}'
with urllib.request.urlopen(url, timeout=60) as r:
    archive = tarfile.open(fileobj=io.BytesIO(r.read()), mode='r:gz')
for member in archive.getmembers():
    relative = Path(*Path(member.name).parts[1:])
    if not member.isfile() or relative.is_absolute() or '..' in relative.parts:
        continue
    if relative.suffix not in {'.py', '.toml', '.txt', '.yaml'} and relative.name not in {'LICENSE', 'NOTICE'}:
        continue
    dest = source / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(archive.extractfile(member).read())
(source / 'SOURCE.json').write_text(json.dumps({'repository': 'arbazsiddiqui/voxlock', 'revision': VOX}, indent=2))
scicom = snapshot_download('Scicom-intl/voice-isolator', revision=SCICOM,
    cache_dir=str(ROOT / 'hub'), token=False, max_workers=2,
    allow_patterns=['config.json', 'model.safetensors', 'agent/config.json',
                    'agent/model.safetensors', 'requirements.txt', 'README.md', 'vi/*.py', 'vi/LICENSE*'])
(ROOT / 'locations.json').write_text(json.dumps({'voxlock_source': str(source),
    'scicom': scicom, 'scicom_revision': SCICOM}, indent=2))
print('Pinned sources and model files ready:', ROOT)

# Native CUDA-graph comparison uses the exact WeSpeaker revision required by VoxLock.
speaker_rev = '8f53b6485d9f88a207bd17e7f8dba899495ec794'
speaker_source = ROOT / 'wespeaker-src'
with urllib.request.urlopen(f'https://api.github.com/repos/wenet-e2e/wespeaker/tarball/{speaker_rev}', timeout=60) as r:
    archive = tarfile.open(fileobj=io.BytesIO(r.read()), mode='r:gz')
for member in archive.getmembers():
    relative = Path(*Path(member.name).parts[1:])
    if not member.isfile() or relative.is_absolute() or '..' in relative.parts:
        continue
    if relative.suffix != '.py' and relative.name != 'LICENSE':
        continue
    dest = speaker_source / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(archive.extractfile(member).read())
for name in ['config.yaml', 'model.safetensors']:
    hf_hub_download('arbazsiddiqui/voxlock', name, revision='2413b292bc2c337bfc19a9802aaf3e011e68e9c4',
                   cache_dir=str(ROOT/'hub'), token=False)
print('Native VoxLock/WeSpeaker sources ready. See the report for optional Python dependencies.')
