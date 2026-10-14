"""Foreground and contour metrics, fixed per-region scores, and honest visual comparisons."""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageOps
from skimage.metrics import structural_similarity
from .reference import ROOT,NAMES
from .model import load_pose,points
from .renderer import render_files

REGIONS={'right_brow':(195,0,710,315),'left_brow':(720,0,1230,265),'right_eye':(210,190,670,560),'left_eye':(800,130,1250,495),'nose':(655,415,805,530),'right_moustache':(340,465,720,675),'left_moustache':(745,435,1130,610),'mouth':(570,530,920,750)}

def metrics(reference,generated):
    a=np.asarray(reference.convert('L'));b=np.asarray(generated.convert('L'));ma=a<128;mb=b<128
    overlap=np.sum(ma&mb);union=np.sum(ma|mb);total=np.sum(ma)+np.sum(mb)
    ea=ma&~cv2.erode(ma.astype('uint8'),np.ones((3,3),np.uint8)).astype(bool)
    eb=mb&~cv2.erode(mb.astype('uint8'),np.ones((3,3),np.uint8)).astype(bool)
    da=cv2.distanceTransform((~ea).astype('uint8'),cv2.DIST_L2,cv2.DIST_MASK_PRECISE);db=cv2.distanceTransform((~eb).astype('uint8'),cv2.DIST_L2,cv2.DIST_MASK_PRECISE)
    distances=np.concatenate([da[eb],db[ea]]) if ea.any() and eb.any() else np.array([np.hypot(*a.shape)])
    return {'foreground_iou':float(overlap/max(union,1)),'dice':float(2*overlap/max(total,1)),
      'contour_chamfer_px':float(distances.mean()),'contour_p95_px':float(np.percentile(distances,95)),
      'ssim':float(structural_similarity(a,b,data_range=255)),'reference_foreground_pixels':int(ma.sum()),'generated_foreground_pixels':int(mb.sum())}

def compare(ref,gen,out,name):
    a=np.asarray(ref);b=np.asarray(gen);ma=a.mean(axis=2)<128;mb=b.mean(axis=2)<128
    overlay=np.full_like(a,255);overlay[ma]=[220,50,65];overlay[mb]=[40,110,235];overlay[ma&mb]=[25,25,25]
    diff=np.full_like(a,255);diff[ma&~mb]=[220,50,65];diff[mb&~ma]=[40,110,235]
    Image.fromarray(overlay).save(out/f'{name}_overlay.png');Image.fromarray(diff).save(out/f'{name}_difference.png')
    board=Image.new('RGB',(4*600,340),'#e5e7eb');dr=ImageDraw.Draw(board)
    for i,(label,im) in enumerate(zip(['Original','SVG reconstruction','Overlay: red reference / blue generated','Difference'],[ref,gen,Image.fromarray(overlay),Image.fromarray(diff)])):
        thumb=ImageOps.contain(im,(600,310));board.paste(thumb,(i*600,30));dr.text((i*600+5,9),label,fill='black')
    board.save(out/f'{name}_comparison.png');return board

def evaluate():
    out=ROOT/'output/reconstructions';out.mkdir(exist_ok=True);comp=ROOT/'output/comparisons';comp.mkdir(exist_ok=True)
    results={};boards=[]
    for name in NAMES:
        p=load_pose(ROOT/f'poses/{name}.json');render_files(p,out/f'{name}.svg',out/f'{name}.png')
        ref=Image.open(ROOT/f'output/references/{name}.png').convert('RGB');gen=Image.open(out/f'{name}.png').convert('RGB')
        ref.save(out/f'{name}_original.png');(out/f'{name}.json').write_text(json.dumps(p,indent=2))
        m=metrics(ref,gen);m['regions']={n:metrics(ref.crop(box),gen.crop(box)) for n,box in REGIONS.items()};results[name]=m
        boards.append(compare(ref,gen,comp,name));(out/f'{name}_metrics.json').write_text(json.dumps(m,indent=2))
    board=Image.new('RGB',(2400,340*len(boards)))
    for i,b in enumerate(boards):board.paste(b,(0,340*i))
    board.save(comp/'all_references.png')
    report={'schema_version':'1.0','threshold':128,'contour_units':'canonical pixels (1450x750)','regions':REGIONS,'poses':results,
      'mean':{k:float(np.mean([m[k] for m in results.values()])) for k in ('foreground_iou','dice','contour_chamfer_px','ssim')}}
    (ROOT/'output/evaluation.json').write_text(json.dumps(report,indent=2));diagnose(report);return report


def diagnose(report=None):
    """Localize residuals without pretending that pixel statistics identify their cause."""
    report=report or json.loads((ROOT/'output/evaluation.json').read_text());result={}
    for name,m in report['poses'].items():
        a=np.asarray(Image.open(ROOT/f'output/references/{name}.png').convert('L'))<128
        b=np.asarray(Image.open(ROOT/f'output/reconstructions/{name}.png').convert('L'))<128;rows=[]
        for region,(x0,y0,x1,y1) in REGIONS.items():
            aa=a[y0:y1,x0:x1];bb=b[y0:y1,x0:x1];ca=np.column_stack(np.where(aa));cb=np.column_stack(np.where(bb))
            d=(cb.mean(0)-ca.mean(0))[::-1] if len(ca) and len(cb) else np.array([0,0])
            rows.append({'region':region,'iou':m['regions'][region]['foreground_iou'],'centroid_shift_xy_px':d.tolist(),
              'missing_foreground_pixels':int(np.sum(aa&~bb)),'extra_foreground_pixels':int(np.sum(bb&~aa)),
              'contour_p95_px':m['regions'][region]['contour_p95_px']})
        result[name]=sorted(rows,key=lambda v:v['iou'])
    (ROOT/'output/diagnostics.json').write_text(json.dumps(result,indent=2));return result
