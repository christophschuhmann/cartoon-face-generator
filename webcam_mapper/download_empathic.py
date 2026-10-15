"""Download pinned LAION heads and their matching, CPU-compatible SigLIP2 encoder."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import urllib.parse

ROOT = Path(__file__).parent / 'models/empathic'
HEADS = {
    'small': ('laion/Empathic-Insight-Face-Small','11563ec072a72fddf1be992b9abc0a1c675cf75a','EmoNet-Face-Small-average-scores-for-neutral-faces.json'),
    'large': ('laion/Empathic-Insight-Face-Large','1b2e950bbc35f11407de7e92bd5d70d6fd5067ee','neutral_stats_cache-_human-binary-big-mlps.json'),
}
VISION_REPO = 'onnx-community/siglip2-so400m-patch16-384-ONNX'
VISION_REV = '29f74e673c298fd07482d8e20138179282001eb7'
VISION_HASH = '7b015bfdf140d7d13d74c7fc4b00553b65747620c0a8f11d0f7cbd4cad772cc5'
Q4_HASH = '982742d76d38c6aea609eea68e2c9c74fbc67e85aaa0ade31744a27358a29cfd'


def sha256(path):
    with path.open('rb') as file: return hashlib.file_digest(file,'sha256').hexdigest()


def download(url, destination, checksum=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and (not checksum or sha256(destination)==checksum): return
    partial = destination.with_suffix(destination.suffix + '.part')
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=90) as response, partial.open('wb') as output:
        while chunk := response.read(1024*1024):
            output.write(chunk); digest.update(chunk)
    if checksum and digest.hexdigest() != checksum: raise ValueError('Checksum mismatch: ' + destination.name)
    partial.replace(destination)
    print('Verified', destination.name, destination.stat().st_size, flush=True)


def prepare_cpu_encoder():
    """Recode signed convolution weights as unsigned without changing w-zp."""
    import onnx
    import numpy as np
    from onnx import numpy_helper
    source,destination=ROOT/'vision_int8.onnx',ROOT/'vision_cpu_int8.onnx'
    manifest=ROOT/'cpu_encoder.source.json'
    if manifest.exists() and destination.exists():
        info=json.loads(manifest.read_text())
        if sha256(destination)==info['sha256']:return
    if sha256(source)!=VISION_HASH:raise ValueError('Unverified encoder input')
    model=onnx.load(source)
    tensors={x.name:x for x in model.graph.initializer}
    changed=[]
    for node in model.graph.node:
        if node.op_type!='ConvInteger':continue
        for name in (node.input[1],node.input[3]):
            data=numpy_helper.to_array(tensors[name])
            if data.dtype!=np.int8:raise ValueError('Expected signed ConvInteger weights/zero point')
            recoded=(data.astype(np.int16)+128).astype(np.uint8)
            np.testing.assert_array_equal(recoded.astype(np.int16)-128,data.astype(np.int16))
            tensors[name].CopyFrom(numpy_helper.from_array(recoded,name))
        changed.append(node.name)
    if len(changed)!=1:raise ValueError('Unexpected encoder graph')
    onnx.checker.check_model(model)
    onnx.save(model,destination)
    manifest.write_text(json.dumps({'repository':VISION_REPO,'revision':VISION_REV,
        'source_sha256':VISION_HASH,'sha256':sha256(destination),
        'transformation':'ConvInteger weights and weight zero point +128, int8 to uint8; same centered integers',
        'nodes':changed},indent=2),encoding='utf8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=tuple(HEADS),default='small')
    parser.add_argument('--encoder',choices=('q4','cpu_int8'),default='q4')
    args=parser.parse_args()
    repo,rev,stats=HEADS[args.variant]
    root=ROOT/'small' if args.variant=='small' else ROOT
    root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free<1_500_000_000:
        raise RuntimeError('At least 1.5 GB free space is required during setup')
    data=json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true',timeout=30))
    extras={'model_'+key+'_best.pth' for key in ('arousal','dominance','emotional_vulnerability','valence')}
    heads=[f for f in data['siblings'] if f['rfilename'].startswith('model_') and f['rfilename'].endswith('.pth') and f['rfilename'] not in extras]
    if len(heads)!=40:raise ValueError('Expected exactly forty emotion heads')
    quant='q4' if args.encoder=='q4' else 'int8'
    checksum=Q4_HASH if quant=='q4' else VISION_HASH
    jobs=[(f'https://huggingface.co/{VISION_REPO}/resolve/{VISION_REV}/onnx/vision_model_{quant}.onnx',ROOT/('vision_'+quant+'.onnx'),checksum)]
    jobs += [(f'https://huggingface.co/{repo}/resolve/{rev}/'+urllib.parse.quote(f['rfilename']),root/'heads'/f['rfilename'],f['lfs']['sha256']) for f in heads]
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda args:download(*args),jobs))
    download(f'https://huggingface.co/{repo}/resolve/{rev}/'+stats,root/'neutral_stats.json')
    download(f'https://huggingface.co/{repo}/resolve/{rev}/README.md',root/'LAION_MODEL_CARD.md')
    for name,target in [('preprocessor_config.json','preprocessor_config.json'),('README.md','VISION_MODEL_CARD.md')]:
        download(f'https://huggingface.co/{VISION_REPO}/resolve/{VISION_REV}/'+name,ROOT/target)
    manifest={'heads_repository':repo,'heads_revision':rev,'heads_license':'CC-BY-4.0',
        'vision_repository':VISION_REPO,'vision_revision':VISION_REV,'vision_sha256':checksum,
        'encoder':'google/siglip2-so400m-patch16-384','quantization':args.encoder,
        'embedding_dimension':1152,'heads':{f['rfilename']:f['lfs']['sha256'] for f in heads}}
    (root/'source.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    if args.encoder=='cpu_int8':prepare_cpu_encoder()
    print('Ready for python -m webcam_mapper.empathic --convert --variant '+args.variant,flush=True)


if __name__=='__main__':main()

