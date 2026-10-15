"""Install CPU audio runtime wheels locally; GPU kernel bundles are not needed."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from .resumable_download import download

ROOT=Path(__file__).resolve().parents[1]
VERSIONS={'moondream':'2.6.1','kestrel':'0.9.1','kestrel-native':'0.1.8','kestrel-kernels':'0.7.4',
          'torch-c-dlpack-ext':'0.1.5','transformers':'5.19.0','huggingface-hub':'1.31.0',
          'safetensors':'0.8.0','tokenizers':'0.23.3','regex':'2026.9.29','click':'8.5.0'}

def main():
    folder=ROOT/'webcam_mapper/models/audio_wheels';folder.mkdir(exist_ok=True)
    paths=[];manifest=[]
    for name,version in VERSIONS.items():
        metadata=folder/(name+'.json')
        if metadata.is_file():d=json.loads(metadata.read_text())
        else:
            for attempt in range(6):
                try:
                    address=f'https://pypi.org/pypi/{name}/{version}/json'
                    data=subprocess.check_output(['curl.exe','-sS','-L','--fail','--connect-timeout','10','--max-time','30',address])
                    d=json.loads(data);metadata.write_text(json.dumps(d));break
                except Exception:
                    if attempt==5:raise
                    time.sleep(.5)
        wheels=[x for x in d['urls'] if x['filename'].endswith('py3-none-any.whl') or 'win_amd64.whl' in x['filename'] and ('cp312-cp312' in x['filename'] or 'cp310-abi3' in x['filename'])]
        x=wheels[0];path=folder/x['filename'];paths.append(str(path))
        row=dict(url=x['url'],size=x['size'],sha256=x['digests']['sha256'],path=str(path),workers=4)
        manifest.append(row);download(**row)
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2))
    subprocess.run([str(ROOT/'.venv-audio/Scripts/python.exe'),'-m','pip','install','--no-deps','--no-index','--no-compile',*paths],check=True)

if __name__=='__main__':main()
