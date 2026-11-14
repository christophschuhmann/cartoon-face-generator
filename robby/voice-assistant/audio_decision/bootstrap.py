"""Install only the isolated d1 dependencies and download the pinned public model."""
import os,subprocess,sys
from pathlib import Path
from .engine import ASSETS,MODEL,REVISION
ASSETS.mkdir(parents=True,exist_ok=True)
uv=os.getenv('UV_BIN',str(Path.home()/'.local/bin/uv'))
subprocess.run([uv,'pip','install','--python',sys.executable,'--target',str(ASSETS/'env'),'--no-deps','transformers==5.19.0'],check=True)
subprocess.run([uv,'pip','install','--python',sys.executable,'--target',str(ASSETS/'env'),'--upgrade','huggingface-hub==2.4.0','tokenizers==0.23.3'],check=True)
from huggingface_hub import snapshot_download
path=snapshot_download(MODEL,revision=REVISION,cache_dir=str(ASSETS/'cache'),token=False)
(ASSETS/'model-path.txt').write_text(path)
print('Pinned public model prepared. Start with: python audio_decision/manage.py start')
