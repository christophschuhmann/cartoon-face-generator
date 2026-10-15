"""Pinned CPU models for optional Babble/SigLIP mouth experiments."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import urllib.request

ROOT = Path(__file__).parent / 'models/mouth'
BABBLE_REV = '17d07c2f903e50d7a556d28d648039f183f9612c'
SIGLIP_REV = 'ba1f3b0843f24bc5417d38e19c37b287d719b2f4'
HF = f'https://huggingface.co/onnx-community/siglip2-base-patch16-224-ONNX/resolve/{SIGLIP_REV}/'
ASSETS = {
    'babble.onnx': (f'https://raw.githubusercontent.com/Project-Babble/ProjectBabble/{BABBLE_REV}/BabbleApp/Models/EFFB0E11BS128V7.5/onnx/model.onnx', None),
    'Babble_LICENSE.md': (f'https://raw.githubusercontent.com/Project-Babble/ProjectBabble/{BABBLE_REV}/LICENSE.md', None),
    'vision_model_q4.onnx': (HF+'onnx/vision_model_q4.onnx', '03e61be280fb24114facd87a1e1e6b2b654aad49845686da2f930c72740914aa'),
    'text_model_int8.onnx': (HF+'onnx/text_model_int8.onnx', '3a0603d3a00c05a80a6ded4743c16aaac7b1e62cdcc7e362e7ce418659b96400'),
    **{name:(HF+name,None) for name in ('tokenizer.json','tokenizer_config.json','config.json','preprocessor_config.json')},
}

def download(item):
    name, (url, expected) = item
    path = ROOT / name
    if path.exists() and (expected is None or hashlib.sha256(path.read_bytes()).hexdigest()==expected):
        return {'file':name,'url':url,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    partial = path.with_suffix(path.suffix+'.part')
    with urllib.request.urlopen(url, timeout=40) as source, partial.open('wb') as dest:
        while chunk:=source.read(1024*1024): dest.write(chunk)
    digest = hashlib.sha256(partial.read_bytes()).hexdigest()
    if expected and digest != expected: raise ValueError('Checksum mismatch: '+name)
    partial.replace(path)
    print(name, path.stat().st_size, flush=True)
    return {'file':name,'url':url,'sha256':digest}

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        records=list(pool.map(download,ASSETS.items()))
    (ROOT/'sources.json').write_text(json.dumps(records,indent=2)+'\n')

if __name__=='__main__': main()
