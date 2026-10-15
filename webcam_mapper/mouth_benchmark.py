"""Small public-photo diagnostic, not a webcam accuracy benchmark."""
import argparse
import json
import time
import numpy as np
from PIL import Image
from .paths import ROOT,DEFAULT_MODEL
from .landmarker import CpuFaceLandmarker
from .mouth_models import BabbleModel,SiglipMouthModel,mouth_crop,face_crop

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['babble','siglip'],required=True);args=parser.parse_args()
    folder=ROOT/'webcam_mapper/output/verification/mouth_research'
    figure=Image.open(folder/'tongue_examples.png').convert('RGB')
    # Six original input photographs in the published paper figure, excluding
    # all reconstruction/render columns. One has closed/pushed lips.
    scale=figure.width/2048
    boxes=[(23,y,211,y+189) for y in (15,229,444)]+[(1067,y,1255,y+189) for y in (15,229,444)]
    images=[(f'paper_{i}',i!=2,np.asarray(figure.crop(tuple(round(v*scale) for v in b)))) for i,b in enumerate(boxes)]
    images.append(('nasa_smile',False,np.asarray(Image.open(folder.parent/'astronaut.png').convert('RGB'))))
    model=BabbleModel() if args.mode=='babble' else SiglipMouthModel();rows=[]
    with CpuFaceLandmarker(DEFAULT_MODEL,video=False) as detector:
        for name,expected,rgb in images:
            obs=detector.detect(rgb)
            if obs is None:rows.append(dict(name=name,tracking=False));continue
            crop=(mouth_crop if args.mode=='babble' else face_crop)(rgb,obs)
            Image.fromarray(crop).save(folder/(name+'_'+args.mode+'_crop.png'))
            started=time.perf_counter();result=model.infer(crop)
            row=dict(name=name,expected_tongue=expected,tracking=True,ms=round((time.perf_counter()-started)*1000,1),
                geometry=obs.tongue_out,jaw=obs.blendshapes.get('jawOpen'),pucker=obs.blendshapes.get('mouthPucker'),result=result)
            rows.append(row);print(json.dumps(row),flush=True)
    report=dict(model=args.mode,source='https://github.com/steliosploumpis/tongue/blob/master/figures/qual_fig_new.png',
        note='6 low-resolution public input photos plus NASA smile; tiny convenience sample, no webcam validation.',rows=rows)
    (folder/(args.mode+'_report.json')).write_text(json.dumps(report,indent=2))

if __name__=='__main__':main()
