"""Real SVG before/after boards, geometric join measurements and pose compatibility.

The baseline is the saved recipe-1.0 artifact set, not a generatively redrawn
reference. The new side always comes from the same parametric Python renderer.
"""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from cartoon_face.emotion_library import catalog,emotion_pose40
from cartoon_face.emotion_validation import cue_checks
from cartoon_face.model import load_pose,save_pose,landmark_arrays,points,topology
from cartoon_face.renderer import render_files,render_svg
from cartoon_face.geometry import outline_cubics

ROOT=Path('output/refinement');BEFORE=ROOT/'before';AFTER=ROOT/'after'
font_path=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
font=ImageFont.truetype(str(font_path),16) if font_path.exists() else ImageFont.load_default()


def angles(segments):
    a=segments[:,3]-segments[:,2];b=np.roll(segments[:,1]-segments[:,0],-1,axis=0)
    na=np.linalg.norm(a,axis=1);nb=np.linalg.norm(b,axis=1);valid=(na>1e-5)&(nb>1e-5)
    return np.rad2deg(np.arccos(np.clip((a*b).sum(axis=1)/np.maximum(na*nb,1e-10),-1,1)))[valid]


def compare(old,new,dest,label,scale=.42,crop=None):
    left=Image.open(old).convert('RGB');right=Image.open(new).convert('RGB')
    if crop:left=left.crop(crop);right=right.crop(crop)
    size=tuple(round(v*scale) for v in left.size)
    left=left.resize(size,Image.Resampling.LANCZOS);right=right.resize(size,Image.Resampling.LANCZOS)
    board=Image.new('RGB',(size[0]*2,size[1]+32),'#e7edf4');draw=ImageDraw.Draw(board)
    draw.text((10,6),label+' · vorher',font=font,fill='#263750')
    draw.text((size[0]+10,6),label+' · nachher',font=font,fill='#263750')
    board.paste(left,(0,32));board.paste(right,(size[0],32));board.save(dest)
    return board


def stacked(boards,dest):
    board=Image.new('RGB',(max(b.width for b in boards),sum(b.height for b in boards)),'#e7edf4')
    y=0
    for row in boards:board.paste(row,(0,y));y+=row.height
    board.save(dest)


def main():
    AFTER.mkdir(parents=True,exist_ok=True);dest=ROOT/'comparisons';dest.mkdir(exist_ok=True)
    rows=[];families={};selected=[];compatible=0;variant_count=0
    for profile in catalog()['profiles']:
        slug=profile['slug'];filename=f'{profile["id"]:02}_{slug}'
        old=load_pose(BEFORE/(filename+'.json'));new=emotion_pose40(slug)
        assert render_svg(old)==(BEFORE/(filename+'.svg')).read_text();compatible+=1
        save_pose(new,AFTER/(filename+'.json'));render_files(new,AFTER/(filename+'.svg'),AFTER/(filename+'.png'))
        delta=np.linalg.norm((landmark_arrays(new)[0]-landmark_arrays(old)[0])*[1450,750],axis=1)
        old_angles=[];new_angles=[]
        for name,c in topology()['components'].items():
            if c['kind']!='ribbon':continue
            for pose,target,smooth in ((old,old_angles,0),(new,new_angles,1)):
                r=pose['rig'][name]
                target.extend(angles(outline_cubics(points(pose,name),r['widths'],r['tangent_scales'],smooth)))
        row={'slug':slug,'mean_landmark_change_px':float(delta.mean()),'max_landmark_change_px':float(delta.max()),
            'largest_changed_landmark':topology()['keypoints'][int(delta.argmax())]['name'],
            'maximum_band_join_angle_before_deg':float(max(old_angles)),
            'maximum_band_join_angle_after_deg':float(max(new_angles)),
            'authored_cues_preserved':cue_checks(new)['passed'],
            'before_svg_sha256':hashlib.sha256((BEFORE/(filename+'.svg')).read_bytes()).hexdigest(),
            'after_svg_sha256':hashlib.sha256((AFTER/(filename+'.svg')).read_bytes()).hexdigest()}
        rows.append(row)
        board=compare(BEFORE/(filename+'.png'),AFTER/(filename+'.png'),dest/(filename+'.png'),profile['label_de'])
        families.setdefault(profile['family'],[]).append(board)
        if slug in ('anger','fear','sadness','surprise','disgust','teasing','amusement','contentment'):selected.append(board)
        # Reuse the same saved seeds for a fair variation comparison.
        for path in sorted((BEFORE/'variations'/slug).glob('*.json')):
            original=load_pose(path);assert render_svg(original)==path.with_suffix('.svg').read_text();compatible+=1
            p=emotion_pose40(slug,original['recipe']['seed'],original['recipe']['variation'])
            newpath=AFTER/'variations'/slug/path.name;save_pose(p,newpath);render_files(p,newpath.with_suffix('.svg'),newpath.with_suffix('.png'))
            variant_count+=1
    for family,boards in families.items():stacked(boards,dest/f'family_{family}.png')
    stacked(selected,dest/'selected_emotions.png')
    compare(BEFORE/'32_anger.png',AFTER/'32_anger.png',dest/'anger_eye_detail.png','Wut: Blick / Striche',1.5,(795,135,1230,435))
    compare(BEFORE/'13_surprise.png',AFTER/'13_surprise.png',dest/'round_mouth_detail.png','Überraschung: Mund',3.,(630,550,825,700))
    compare(BEFORE/'18_teasing.png',AFTER/'18_teasing.png',dest/'wink_detail.png','Necken: geschlossenes Auge',1.7,(790,230,1220,430))
    report={'old_recipe_version':'1.0','new_recipe_version':catalog()['recipe_version'],
        'unchanged_landmark_count':101,'compared_archetypes':40,'same_seed_variation_comparisons':variant_count,
        'old_poses_rerendered_byte_identically':compatible,'all_authored_cues_preserved':all(r['authored_cues_preserved'] for r in rows),
        'mean_landmark_change_px':float(np.mean([r['mean_landmark_change_px'] for r in rows])),
        'maximum_band_join_angle_before_deg':max(r['maximum_band_join_angle_before_deg'] for r in rows),
        'maximum_band_join_angle_after_deg':max(r['maximum_band_join_angle_after_deg'] for r in rows),
        'metric_scope':'Curve join tangency and pose changes; no psychological recognition or friendliness score',
        'categories':rows}
    (ROOT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='categories'},indent=2))


if __name__=='__main__':main()
