"""Reproducible Small/Large timing and comparison with seven published HF examples.

These are model-output reproduction checks, not a human-emotion accuracy study.
The downloaded HTML is parsed only; it is never executed.
"""
import base64
import html
import io
import json
import re
import time
from pathlib import Path
import numpy as np
from PIL import Image
from threadpoolctl import threadpool_limits
from .empathic import EmpathicModel, HeadBank, MODEL_DIR, ALIASES, EXTRA_HEADS

OUT=Path(__file__).parent/'output/verification'


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--encoder',choices=('cpu_int8','q4'),default='cpu_int8')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    document=(MODEL_DIR/'small/EmoNet-Face-Small.html').read_text(encoding='utf8')
    model=EmpathicModel('small',MODEL_DIR/('vision_'+args.encoder+'.onnx'))
    report={'hardware':'Intel i5-7200U, CPU only, one encoder thread',
            'encoder':'SigLIP2 SO400M patch16 384, '+args.encoder+' ONNX',
            'reference':'https://huggingface.co/laion/Empathic-Insight-Face-Small/blob/main/EmoNet-Face-Small.html',
            'limit':'Seven published examples, rounded source scores, JPEG thumbnails, quantized encoder; not an accuracy benchmark.',
            'examples':[]}
    embedding=None
    for index,block in enumerate(document.split('<div class="sample">')[1:]):
        data=re.search(r'src="data:image/[^;]+;base64,([^"]+)"',block).group(1)
        rgb=np.asarray(Image.open(io.BytesIO(base64.b64decode(data))).convert('RGB'))
        reference={}
        for key,raw in re.findall(r'class="dimension-name">([^<]+)</span>.*?class="raw-score">\(([-.0-9]+)\)',block,re.S):
            name=html.unescape(key).removeprefix('model_').removesuffix('_best')
            if name not in EXTRA_HEADS:reference[ALIASES.get(name,name)]=float(raw)
        if len(reference)!=40:raise ValueError('Incomplete published scores')
        result=model.infer(rgb)
        embedding=np.asarray(result.pop('embedding'),dtype=np.float32)
        expected={s:reference[s]-model.bank.heads[s][1] for s in reference}
        expected_order=sorted(expected,key=expected.get,reverse=True)
        actual_order=sorted(result['scores'],key=lambda s:result['scores'][s]['adjusted'],reverse=True)
        errors=[abs(result['scores'][s]['raw']-reference[s]) for s in reference]
        result.update(example=index+1,reference_top3=expected_order[:3],actual_top3=actual_order[:3],
                      top3_overlap=len(set(expected_order[:3])&set(actual_order[:3])),
                      mean_absolute_raw_difference=float(np.mean(errors)),max_absolute_raw_difference=max(errors))
        report['examples'].append(result)
        print('Example',index+1,'ms',result['inference_ms'],'top3',actual_order[:3],
              'published',expected_order[:3],'MAE',round(float(np.mean(errors)),3),flush=True)
        (OUT/('empathic_small_'+args.encoder+'_comparison.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
    del model
    report['heads']={}
    with threadpool_limits(limits=1):
        for variant in ('small','large'):
            bank=HeadBank(variant)
            bank.infer(embedding)
            times=[]
            for _ in range(20):
                start=time.perf_counter();scores=bank.infer(embedding);times.append((time.perf_counter()-start)*1000)
            root=MODEL_DIR/'small' if variant=='small' else MODEL_DIR
            size=sum(p.stat().st_size for p in (root/'heads').glob('*.pth') if p.stem.removeprefix('model_').removesuffix('_best') not in EXTRA_HEADS)
            report['heads'][variant]={'median_ms':float(np.median(times)),'p95_ms':float(np.percentile(times,95)),'bytes':size,'categories':len(scores)}
            print(variant,report['heads'][variant],flush=True)
    (OUT/('empathic_small_'+args.encoder+'_comparison.json')).write_text(json.dumps(report,indent=2),encoding='utf8')


if __name__=='__main__':main()

