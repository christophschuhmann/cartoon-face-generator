"""Geometric and procedural-cue validation, clearly separate from human recognition."""
from itertools import combinations
from pathlib import Path
import hashlib,json,copy
import numpy as np
from PIL import Image,ImageDraw
from .reference import ROOT
from .model import points,topology,save_pose,landmark_arrays,validate_pose
from .renderer import render_svg,render_files,rasterize
from .dataset import audit_pose
from .geometry import cubic_segments,sample_cubics
from .emotion_library import catalog,emotion_pose40,mix_emotions,resolve_emotion,compatibility,RECOMMENDED_PAIRS
from .animation import interpolate,interpolate_pose


def geometric_features(p):
    """Measure actual exported anchor geometry, not merely recipe control flags."""
    u=points(p,'mouth_upper');l=points(p,'mouth_lower')
    result={'mouth_width_px':float(u[-1,0]-u[0,0]),'mouth_smile_px':float(u[2,1]-(u[0,1]+u[-1,1])/2),
      'mouth_asymmetry_px':float(u[0,1]-u[-1,1]),'mouth_open_center_px':float(l[1,1]-u[2,1])}
    for side in ('left','right'):
        brow=points(p,side+'_brow');up=points(p,side+'_eye_upper');lo=points(p,side+'_eye_lower')
        center_x=(up[2,0]+lo[1,0])/2
        def y_at(pts):
            q=sample_cubics(cubic_segments(pts),32)[0];ix=np.argsort(q[:,0]);return float(np.interp(center_x,q[ix,0],q[ix,1]))
        result[side+'_eye_gap_px']=y_at(lo)-y_at(up)
        result[side+'_brow_inner_drop_px']=float(brow[-1,1]-brow[0,1])
    return result


def cue_checks(p):
    """Check authored design cues; passing does NOT establish recognition accuracy."""
    f=geometric_features(p);emotion=p.get('emotion',{});slug=emotion.get('slug');a=p.get('recipe',{}).get('actions',{})
    failures=[]
    def need(condition,message):
        if not condition:failures.append(message)
    if not a:return {'passed':True,'kind':'mixture; pure-category cue rules not applied','failures':[],'features':f}
    opts=p['recipe']['options'];intensity=emotion.get('intensity',1)
    if intensity<.75:return {'passed':True,'kind':'low intensity; category cue rules not applied','failures':[],'features':f}
    if opts['mouth']=='closed':need(p['rig']['mouth_lower']['opacity']==0,'closed mouth unexpectedly opened')
    if a['smile']>.3 and opts['mouth'] not in ('round','pucker'):need(f['mouth_smile_px']>10,'positive smile curve lost')
    if a['smile']<-.3 and opts['mouth'] not in ('round','pucker'):need(f['mouth_smile_px']<-10,'downturned mouth curve lost')
    if opts['highlight']=='heart':need(all(p['rig'][s+'_highlight']['heart_opacity']>.9 for s in ('left','right')),'heart cue lost')
    if slug in ('pain','pleasure_ecstasy'):need(all(p['rig'][s+'_pupil']['openness']<.08 for s in ('left','right')),'closed-eye cue lost')
    if slug=='teasing':need(p['rig']['left_pupil']['openness']<.08 and p['rig']['right_pupil']['openness']>.8,'wink cue lost')
    if slug in ('anger','malice'):need(all(f[s+'_brow_inner_drop_px']>30 for s in ('left','right')),'angry inward brow slope lost')
    if slug=='sadness':need(all(f[s+'_brow_inner_drop_px']<-20 for s in ('left','right')),'sad inward brow lift lost')
    if slug in ('fear','surprise'):need(all(f[s+'_eye_gap_px']>120 for s in ('left','right')),'wide-eye cue lost')
    if slug=='contempt':need(f['mouth_asymmetry_px']>28,'unilateral mouth lift lost')
    if slug in ('disgust','sourness'):need(a['nose_lift']>.65,'nose lift cue lost')
    return {'passed':not failures,'kind':'procedural cue checks, not perceptual class recognition','failures':failures,'features':f}


def _sheet(items,path,cols=5,cell=(320,191)):
    rows=(len(items)+cols-1)//cols;board=Image.new('RGB',(cols*cell[0],rows*cell[1]),'#e5e7eb');draw=ImageDraw.Draw(board)
    for i,(label,image_path) in enumerate(items):
        im=Image.open(image_path).convert('RGB');im.thumbnail((cell[0],cell[1]-23));x=i%cols*cell[0];y=i//cols*cell[1]
        board.paste(im,(x,y+23));draw.text((x+7,y+5),label,fill='black')
    board.save(path)


def generate_emotions(variations=8,seed=42,out=None):
    """40 archetypes plus N independently seeded, emotion-preserving variations each."""
    if variations<1:raise ValueError('At least one variation per emotion is required')
    out=Path(out or ROOT/'output/emonet');out.mkdir(parents=True,exist_ok=True)
    archetypes=out/'archetypes';archetypes.mkdir(exist_ok=True);variation_dir=out/'variations';variation_dir.mkdir(exist_ok=True)
    rows=[];all_archetypes=[];family_items={};class_features={}
    for profile in catalog()['profiles']:
        slug=profile['slug'];i=profile['id'];prefix=archetypes/f'{i:02}_{slug}'
        p=emotion_pose40(slug);save_pose(p,prefix.with_suffix('.json'));svg=render_files(p,prefix.with_suffix('.svg'),prefix.with_suffix('.png'))
        checks=cue_checks(p);audit=audit_pose(p,svg);checks['geometry_valid']=audit['valid']
        row={'id':i,'slug':slug,'label':profile['label'],'label_de':profile['label_de'],'archetype':str(prefix.relative_to(out)),
          'archetype_checks':checks,'semantic_recognition':'unmeasured; authored cartoon hypothesis','samples':[]}
        all_archetypes.append((f'{i:02} {slug}',prefix.with_suffix('.png')))
        dest=variation_dir/slug;dest.mkdir(exist_ok=True);items=[];features=[]
        for j in range(variations):
            sample_seed=seed+i*100000+j
            p=emotion_pose40(slug,sample_seed,.85);pre=dest/f'{j:04}_seed{sample_seed}'
            save_pose(p,pre.with_suffix('.json'));svg=render_files(p,pre.with_suffix('.svg'),pre.with_suffix('.png'))
            im=Image.open(pre.with_suffix('.png')).convert('L');foreground=float(np.mean(np.asarray(im)<128))
            audit=audit_pose(p,svg);cue=cue_checks(p)
            valid=audit['valid'] and cue['passed'] and .02<foreground<.18
            row['samples'].append({'seed':sample_seed,'pose':str(pre.with_suffix('.json').relative_to(out)),'svg':str(pre.with_suffix('.svg').relative_to(out)),
              'png':str(pre.with_suffix('.png').relative_to(out)),'valid':bool(valid),'foreground_fraction':foreground,'checks':cue,
              'svg_sha256':hashlib.sha256(svg.encode()).hexdigest()})
            items.append((f'{slug} / {j+1}',pre.with_suffix('.png')));features.append(landmark_arrays(p)[0].ravel())
        _sheet(items,dest/'contact_sheet.png',cols=min(4,variations))
        family_items.setdefault(profile['family'],[]).extend([(f'{i:02} {slug}',prefix.with_suffix('.png'))]+items[:4])
        class_features[slug]={'unique_svg_count':len(set(s['svg_sha256'] for s in row['samples'])),
          'mean_coordinate_std_normalized':float(np.array(features).std(axis=0).mean())}
        rows.append(row)
    _sheet(all_archetypes,archetypes/'contact_sheet.png')
    for family,items in family_items.items():_sheet(items,variation_dir/f'family_{family}.png')
    report={'taxonomy_id':catalog()['taxonomy_id'],'source':catalog()['source'],'recipe_version':catalog()['recipe_version'],
      'category_count':40,'variations_per_category':variations,'variation_count':40*variations,'seed':seed,
      'all_valid':all(r['archetype_checks']['passed'] and r['archetype_checks']['geometry_valid'] and all(s['valid'] for s in r['samples']) for r in rows),
      'semantic_evaluation':{'human_accuracy':None,'expert_labels':False,'status':'authored cues and agent visual review; not measured recognition accuracy'},
      'diversity':class_features,'categories':rows}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return report


def validate_mix_space(out=None,frames=32):
    """Audit all 780 pairs numerically; actually render representative transitions."""
    if frames<30:raise ValueError('Use at least 30 frames for transition validation')
    out=Path(out or ROOT/'output/emonet');out.mkdir(parents=True,exist_ok=True)
    profiles=catalog()['profiles'];poses={p['slug']:emotion_pose40(p['slug']) for p in profiles};rows=[]
    for aa,bb in combinations(profiles,2):
        a,b=aa['slug'],bb['slug'];valid=True
        for t in (.25,.5,.75):
            p=interpolate_pose(poses[a],poses[b],t);validate_pose(p)
            valid &= np.isfinite(landmark_arrays(p)[0]).all() and len(p['keypoints'])==101
            valid &= all(p['rig'][s+'_eye_upper']['opacity']==1 and p['rig'][s+'_moustache']['opacity']==1 for s in ('left','right'))
        rows.append({'a':a,'b':b,'policy':compatibility(a,b)['kind'],'geometry_valid':bool(valid),'perceptual_compatibility':'not measured'})
    # Closely related, contrasting and ambivalent cases are all included.
    selected=[('amusement','teasing'),('awe','surprise'),('fear','distress'),('gratitude','affection'),('triumph','pride'),
      ('embarrassment','shame'),('sadness','helplessness'),('doubt','confusion'),('disgust','sourness'),
      ('contentment','relief'),('anger','elation'),('pain','pleasure_ecstasy')]
    sequences={};mixitems=[]
    for a,b in selected:
        dest=out/'mixtures'/f'{a}_{b}';sequences[a+'_'+b]=interpolate(poses[a],poses[b],frames,dest)
        mixture=mix_emotions(a,b,.5);save_pose(mixture,dest/'mixture.json');render_files(mixture,dest/'mixture.svg',dest/'mixture.png')
        sequences[a+'_'+b]['policy']=compatibility(a,b)['kind'];mixitems.append((a+' + '+b,dest/'mixture.png'))
    _sheet(mixitems,out/'mixtures/contact_sheet.png',cols=4)
    report={'pair_count':len(rows),'tested_weights':[.25,.5,.75],'all_geometry_valid':all(r['geometry_valid'] for r in rows),
      'rendered_sequences':sequences,'semantic_compatibility':'explicit authoring policy; numerical validity does not prove emotional recognizability','pairs':rows}
    (out/'mixture_validation.json').write_text(json.dumps(report,indent=2)+'\n');return report
