"""Fetch and integrity-check browser wakeword models and ONNX Runtime Web."""
import hashlib,subprocess,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(root/'download_buddy_models.py'),'--browser'],check=True)
ort=root/'static/vendor/onnxruntime';ort.mkdir(parents=True,exist_ok=True)
files={
 'ort.min.js':('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort.min.js','be6e560b64c03c99252eedc0e1989e9e51e44d9f191e7655c9bf011bf9f576c8'),
 'ort-wasm-simd-threaded.mjs':('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort-wasm-simd-threaded.mjs','745eb7c0ce6f18a6aa521971b2877babc7ffb27eecb58ab3bc6e5ef4692672e8'),
 'ort-wasm-simd-threaded.wasm':('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/ort-wasm-simd-threaded.wasm','207d02be4591c156b0a98f024f3d58005b5b04c92274d759fb390338c63559ea'),
 'LICENSE':('https://cdn.jsdelivr.net/gh/microsoft/onnxruntime@v1.20.1/LICENSE','2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c')}
for name,(url,digest) in files.items():
 p=ort/name
 if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==digest:continue
 with urllib.request.urlopen(url,timeout=120) as f:content=f.read(20*1024*1024)
 if hashlib.sha256(content).hexdigest()!=digest:raise RuntimeError('Checksum mismatch: '+name)
 temp=p.with_suffix(p.suffix+'.partial');temp.write_bytes(content);temp.replace(p)
print('Prepared browser wakeword models and ONNX Runtime Web 1.20.1')
