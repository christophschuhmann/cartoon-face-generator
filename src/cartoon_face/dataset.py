"""Reproducible correlated sampling and artifact validation for Phase 1."""
import json,copy,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from .model import validate_pose,save_pose,points,topology
from .renderer import render_files,render_svg
from .expressions import emotion_pose,apply_controls,EMOTIONS


def generate_dataset(count=100,seed=42,out='output/synthetic_samples'):
    if count<1:raise ValueError('count must be positive')
    rng=np.random.default_rng(seed);out=Path(out);out.mkdir(parents=True,exist_ok=True);labels=[];thumbs=[]
    for i in range(count):
        # Stratified emotion coverage, then correlated low-amplitude variations.
        emotion=EMOTIONS[i%len(EMOTIONS)];p=emotion_pose(emotion)
        arousal=float(rng.uniform(.2,1));asym=float(rng.normal(0,.14));gaze=rng.normal(0,.35,2)
        controls={'gaze_x':float(np.clip(gaze[0],-.75,.75)),'gaze_y':float(np.clip(gaze[1],-.6,.6)),
          'left_brow_raise':float(.10*(arousal-.5)+asym),'right_brow_raise':float(.10*(arousal-.5)-asym),
          'left_moustache_curl':float(rng.normal(0,.14)),'right_moustache_curl':float(rng.normal(0,.14)),
          'left_moustache_width':float(rng.uniform(.94,1.06)),'right_moustache_width':float(rng.uniform(.94,1.06))}
        if emotion not in ('sleepy','wink'):controls.update({'left_eye_openness':float(rng.uniform(.82,1.13)),'right_eye_openness':float(rng.uniform(.82,1.13))})
        if emotion not in ('surprised','sleepy'):controls['smile']=float(rng.uniform(-.12,.16))
        p=apply_controls(p,controls);p['name']=f'{i:04}_{emotion}';p['provenance']={'kind':'synthetic','seed':seed,'sample_index':i,'emotion':emotion}
        for k in p['keypoints'].values():k['xy']=np.clip(k['xy'],.004,.996).tolist()
        validate_pose(p);prefix=out/f'{i:04}_{emotion}';save_pose(p,prefix.with_suffix('.json'));svg=render_files(p,prefix.with_suffix('.svg'),prefix.with_suffix('.png'))
        im=Image.open(prefix.with_suffix('.png'));im.thumbnail((250,130));thumbs.append(im)
        checks=audit_pose(p,svg)
        checks['foreground_fraction']=float(np.mean(np.asarray(Image.open(prefix.with_suffix('.png')).convert('L'))<128))
        if not .02<checks['foreground_fraction']<.18:checks['valid']=False;checks['issues'].append('unexpected foreground area')
        labels.append({'image':prefix.with_suffix('.png').name,'pose':prefix.with_suffix('.json').name,'svg':prefix.with_suffix('.svg').name,'emotion':emotion,'audit':checks,'sha256_svg':hashlib.sha256(svg.encode()).hexdigest()})
    cols=min(10,count);rows=(count+cols-1)//cols;board=Image.new('RGB',(cols*250,rows*151),'#e5e7eb')
    for i,(im,e) in enumerate(zip(thumbs,labels)):
        board.paste(im,(i%cols*250,i//cols*151+20));ImageDraw.Draw(board).text((i%cols*250+5,i//cols*151+3),f'{i:03} {e["emotion"]}',fill='black')
    board.save(out/'contact_sheet.png');report={'count':count,'seed':seed,'landmark_count':len(topology()['keypoints']),'emotions':list(EMOTIONS),'all_valid':all(e['audit']['valid'] for e in labels),'samples':labels}
    (out/'manifest.json').write_text(json.dumps(report,indent=2));return report


def audit_pose(p,svg=None):
    import xml.etree.ElementTree as ET
    validate_pose(p);svg=svg or render_svg(p);root=ET.fromstring(svg)
    issues=[]
    for path in root.findall('{http://www.w3.org/2000/svg}path'):
        if any(s in path.get('d','').lower() for s in ('nan','inf')):issues.append('nonfinite path')
    for side in ('left','right'):
        if p['rig'][side+'_eye_upper']['opacity']<.5:issues.append(side+' upper lid vanished')
        if p['rig'][side+'_moustache']['opacity']<.5:issues.append(side+' moustache vanished')
        if p['rig'][side+'_pupil']['rx']<=0 or p['rig'][side+'_pupil']['ry']<=0:issues.append('invalid pupil')
    return {'valid':not issues,'issues':issues,'landmark_count':len(p['keypoints'])}
