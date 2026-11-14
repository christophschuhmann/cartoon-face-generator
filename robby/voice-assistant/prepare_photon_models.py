"""Fetch only the two pinned public inference checkpoints on the home drive."""
from pathlib import Path
from huggingface_hub import snapshot_download
from photon_asr_worker import SPECS

if __name__=='__main__':
 for s in SPECS.values():
  path=snapshot_download('moondream/parakeet-'+s['name'],revision=s['revision'],
      cache_dir=str(Path.home()/'.cache/robby-photon/models'),token=False,max_workers=2,
      allow_patterns=['*.json','*.safetensors','README.md'])
  print(s['name'],path)
