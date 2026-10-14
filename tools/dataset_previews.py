"""Inspect real SVG samples, extreme OOD states and label-aware augmentations."""
from pathlib import Path
import json
from PIL import Image
from cartoon_face.reference import ROOT
from cartoon_face.large_dataset import categories
from cartoon_face.emotion_library import emotion_pose40
from cartoon_face.social_expressions import social_pose
from cartoon_face.renderer import render_files
from cartoon_face.augmentation import augment_raster,draw_annotation
from cartoon_face.emotion_validation import _sheet
import sys
sys.path.insert(0,str(ROOT))
from training.prepare import shard_records

out=ROOT/'output/dataset_previews';out.mkdir(parents=True,exist_ok=True);dataset=ROOT/'datasets/cartoon_landmarks_v2'
items=[]
for category in categories():
    stamp=f"{category['kind']}_{category['id']:02}_{category['slug']}";pre=dataset/'preview'/stamp/(stamp+'-000000.png')
    if pre.exists():items.append((stamp,pre))
_sheet(items,out/'all_100_dataset_examples.png',cols=5)
ood_items=[];chosen={0,1,10,18,25,31,39,40,48,61,84,99}
for i,(key,svg,p) in enumerate(shard_records(dataset/'train/ood_01_independent_xy_jitter.tar.gz')):
    if i in chosen:
        target=p['provenance']['source_target'];seed=p['dataset']['source_seed']
        before=emotion_pose40(target['slug'],seed,.95) if 'taxonomy_id' in target else social_pose(target['slug'],seed,.95)
        before['canvas']={'width':768,'height':400}
        pre=out/(key+'_source');render_files(before,pre.with_suffix('.svg'),pre.with_suffix('.png'))
        post=out/key;post.with_suffix('.svg').write_text(svg);post.with_suffix('.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
        image,ann=augment_raster(p,42,768,400,False,svg);image.save(post.with_suffix('.png'));draw_annotation(image,ann).save(out/(key+'_points.png'))
        ood_items.extend([(target['slug']+' / source',pre.with_suffix('.png')),('independent 5-10% XY',post.with_suffix('.png')),('same 101 IDs',out/(key+'_points.png'))])
    if i>=99:break
_sheet(ood_items,out/'ood_examples.png',cols=3,cell=(400,231))
augmentation=[]
for i,slug in enumerate(['amusement','anger','fear','sadness','affection','teasing','mock_monster','offended','cross_eyed_goof','supportive_concern','tiny_o_big_eyes','playful_reconciliation']):
    p=emotion_pose40(slug,42+i,.95) if i<6 else social_pose(slug,42+i,.95)
    p['canvas']={'width':768,'height':400};size=(384,384) if i%3==0 else (512,320) if i%3==1 else (768,400)
    for variant in ('clean','augmented'):
        image,ann=augment_raster(p,84+i,*size,variant=='augmented');pre=out/f'{slug}_{variant}.png';image.save(pre)
        (out/f'{slug}_{variant}.json').write_text(json.dumps(ann,ensure_ascii=False,indent=2)+'\n');augmentation.append((slug+' / '+variant,pre))
        if variant=='augmented':
            marked=out/f'{slug}_augmented_points.png';draw_annotation(image,ann).save(marked);augmentation.append(('transformed labels',marked))
_sheet(augmentation,out/'augmentation_examples.png',cols=3,cell=(400,260))
print('Dataset, OOD and augmentation contact sheets created from the real renderer')
