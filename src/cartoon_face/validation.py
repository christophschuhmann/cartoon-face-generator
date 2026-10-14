"""Run A/B/C and archive evidence, rather than declaring an unverified prototype complete."""
import json
from PIL import Image,ImageDraw
from .reference import ROOT
from .evaluation import evaluate
from .model import load_pose,save_pose
from .renderer import render_files
from .expressions import emotion_pose,EMOTIONS
from .animation import interpolate
from .dataset import generate_dataset


def validate_all(frames=32,count=100,seed=42):
    if frames<30 or count<100:raise ValueError('Phase 1 requires >=30 frames and >=100 samples')
    a=evaluate();out=ROOT/'output/emotions';out.mkdir(exist_ok=True);emotion_poses={}
    board=Image.new('RGB',(4*362,4*213),'#e5e7eb')
    for i,n in enumerate(EMOTIONS):
        p=emotion_pose(n);save_pose(p,out/f'{n}.json');render_files(p,out/f'{n}.svg',out/f'{n}.png');emotion_poses[n]=p
        im=Image.open(out/f'{n}.png');im.thumbnail((362,188));board.paste(im,(i%4*362,i//4*213+22));ImageDraw.Draw(board).text((i%4*362+10,i//4*213+4),n,fill='black')
    board.save(out/'contact_sheet.png')
    pairs=[('smile','cheeky'),('cheeky','love'),('smile','tongue'),('cheeky','skeptical'),('tense','love'),('neutral','surprised'),('neutral','sleepy')]
    b={}
    for left,right in pairs:
        pp=lambda n:emotion_poses[n] if n in emotion_poses and n not in ('love','tongue') else load_pose(ROOT/f'poses/{n}.json')
        b[left+'_'+right]=interpolate(pp(left),pp(right),frames,ROOT/f'output/interpolations/{left}_{right}')
    c=generate_dataset(count,seed,ROOT/'output/synthetic_samples')
    report={'reference_mean':a['mean'],'interpolation_sequences':b,'synthetic_count':count,'synthetic_seed':seed,'synthetic_all_valid':c['all_valid'],'landmark_count':c['landmark_count'],'emotion_count':len(EMOTIONS)}
    (ROOT/'output/validation.json').write_text(json.dumps(report,indent=2));return report
