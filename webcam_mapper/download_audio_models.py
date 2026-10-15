"""Download pinned LAION Ears Base and Moondream Redux weights onto E/project."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import urllib.request

ROOT = Path(__file__).parent / 'models'
SOURCES = {
 'ears': ('laion/humaneness-ears-base-medium','818506970d93c809a3295a0a02c40dee8ff2bfc3', {
  'base/model.safetensors':'c4d9e05295020cd0fab4e44ee10aae3bdf934b0a7700fea05bb271ffa2e410b4',
  **{f:None for f in ('README.md','LICENSE','NOTICE.md','model.py','inference.py','classes.json','training_normalization.json','display_normalization.json','base/config.json','base/preprocessor_config.json')}}),
 'parakeet-redux': ('moondream/parakeet-redux','2bf128600aac4b16946f7ed8372e56117fe5e23b', {
  'model.safetensors':'78ec25733ee0d0c1586d1346fc86db9d0c2e436e3a8ab1d32a82d1bb8f848d21',
  **{f:None for f in ('README.md','config.json','ternary.json','tokenizer.json')}}),
}

def fetch(item):
    folder,repo,revision,name,expected=item
    p=ROOT/folder/name; p.parent.mkdir(parents=True,exist_ok=True)
    if not p.is_file() or (expected and hashlib.sha256(p.read_bytes()).hexdigest()!=expected):
        url=f'https://huggingface.co/{repo}/'+('resolve' if expected else 'raw')+f'/{revision}/{name}'
        tmp=p.with_suffix(p.suffix+'.part')
        with urllib.request.urlopen(url,timeout=60) as src,tmp.open('wb') as dst:
            while block:=src.read(256*1024):dst.write(block)
        if expected and hashlib.sha256(tmp.read_bytes()).hexdigest()!=expected:raise ValueError('Checksum: '+name)
        tmp.replace(p)
    print(folder+'/'+name,p.stat().st_size,flush=True)
    return {'file':folder+'/'+name,'repo':repo,'revision':revision,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def main():
    jobs=[(folder,repo,rev,name,digest) for folder,(repo,rev,files) in SOURCES.items() for name,digest in files.items()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(fetch,jobs))
    (ROOT/'audio_sources.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
