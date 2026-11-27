"""Fetch the pinned browser or legacy server Buddy models and verify SHA-256."""
import argparse,hashlib,urllib.request
from pathlib import Path

base=Path(__file__).resolve().parent
hf='https://huggingface.co/laion/bud-e_wakeword-models_livekit-wakeword/resolve/86020dab86d481b1cba9f4d0fd73a911ab87fc3a/'
gh='https://raw.githubusercontent.com/livekit/livekit-wakeword/69324baa933e/src/livekit/wakeword/resources/'
files={
 'embedding_model.onnx':(gh+'embedding_model.onnx','70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f'),
 'melspectrogram.onnx':(gh+'melspectrogram.onnx','ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f'),
}
browser_models={
 'hey_buddy_en_tiny.onnx':(hf+'en_tiny/hey_buddy_en_tiny.onnx','7e614d79fb7a5adc9ba0660c57a2a09f992e9867b903af4360dd991eab55080a'),
 'go_buddy_en_medium.onnx':(hf+'go_buddy_en_medium/go_buddy_en_medium.onnx','e0d971a4967c482aa932bcf247a9db4d902b8b87071a3d0844ac3ab808b518ea'),
 'stop_buddy_en_medium.onnx':(hf+'stop_buddy_en_medium/stop_buddy_en_medium.onnx','013298a07aa2f517b372cae5e7491767edb64ab5e747a113cb143f3cc126cb8a'),
}
legacy_models={
 'hey_buddy_en_large_v2.onnx':(hf+'en_large_v2/hey_buddy_en_large_v2.onnx','5aec97ad3a3c90da85e76cf86732520ed8eaff1286ed545345660a8a9e06c512'),
 'hey_buddy_en_large_v3.onnx':(hf+'en_large_v3/hey_buddy_en_large_v3.onnx','b3d00e50c329c9f2749b521cc3638d12aa2675d421ff98b3f3f2fe277fe84ee2'),
 'go_buddy_en_large_v2.onnx':(hf+'go_buddy_en_large_v2/go_buddy_en_large_v2.onnx','f1059b82340b03e2643adb07175ef741a62c3383cfe879d71f0b5460e4b25265'),
 'go_buddy_en_large_v3.onnx':(hf+'go_buddy_en_large_v3/go_buddy_en_large_v3.onnx','e36a07d02437d2c766fc1c8b8a47d7d36f8106d597808ce5cd21c9cc0ab63d91'),
 'stop_buddy_en_large_v2.onnx':(hf+'stop_buddy_en_large_v2/stop_buddy_en_large_v2.onnx','be2df0f602469b3558323d88490f707e8ea4efbb63de6ecede3f32c69ee92258'),
 'stop_buddy_en_large_v3.onnx':(hf+'stop_buddy_en_large_v3/stop_buddy_en_large_v3.onnx','06920db4c51205c5527721e574e28b48fd257809232b9aaaa67db855354fe450'),
}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--browser',action='store_true',help='Prepare only the five ONNX files served to browsers')
args=parser.parse_args()
files.update(browser_models if args.browser else legacy_models)
root=base/('static/wake-models' if args.browser else 'models/buddy-wakeword')
root.mkdir(parents=True,exist_ok=True)
for name,(url,expected) in files.items():
    target=root/name
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==expected:continue
    with urllib.request.urlopen(url,timeout=90) as response:content=response.read(6*1024*1024)
    if hashlib.sha256(content).hexdigest()!=expected:raise RuntimeError('Checksum mismatch: '+name)
    temp=target.with_suffix('.partial');temp.write_bytes(content);temp.replace(target)
print('Buddy ONNX assets verified:',len(files))
