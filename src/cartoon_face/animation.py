"""Continuous fixed-topology interpolation with explicit fades for discrete components."""
import copy
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from .model import validate_pose,refresh_states,save_pose
from .renderer import render_files

def blend(a,b,t):
    if isinstance(a,dict):return {k:blend(a[k],b.get(k,a[k]),t) for k in a}
    if isinstance(a,list) and isinstance(b,list) and len(a)==len(b):return [blend(x,y,t) for x,y in zip(a,b)]
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return (1-t)*a+t*b
    return copy.deepcopy(a if t<.5 else b)

def interpolate_pose(a,b,t):
    validate_pose(a);validate_pose(b);t=float(np.clip(t,0,1));p=copy.deepcopy(a)
    for name,k in p['keypoints'].items():k['xy']=blend(a['keypoints'][name]['xy'],b['keypoints'][name]['xy'],t)
    p['rig']=blend(a['rig'],b['rig'],t)
    if 'geometry' in a or 'geometry' in b:
        default={'version':'smooth_v1','ribbon_smoothing':0.,'mouth_rounding':0.}
        p['geometry']=blend(a.get('geometry',default),b.get('geometry',default),t)
        if t==0:p['geometry']=copy.deepcopy(a.get('geometry',default))
        elif t==1:p['geometry']=copy.deepcopy(b.get('geometry',default))
        elif any(x.get('geometry',{}).get('under_eye_transition')=='stroke_bank_v1' for x in (a,b)):
            p['geometry']['under_eye_transition']='stroke_bank_v1'
        if p['geometry'].get('under_eye_transition')=='stroke_bank_v1':
            for side in ('left','right'):
                def bank(endpoint):
                    h=endpoint['rig'][side+'_hatching'];phase=h.get('foldness',float(h['opacity']>0))
                    if 'slot_weights' in h:weights=h['slot_weights']
                    else:
                        weights=np.zeros(8);count=int(np.clip(round(h['count']),0,8))
                        if count:weights[np.rint(np.linspace(0,7,count)).astype(int)]=1
                    return phase,np.asarray(weights)
                phase_a,slots_a=bank(a);phase_b,slots_b=bank(b)
                p['rig'][side+'_hatching']['foldness']=(1-t)*phase_a+t*phase_b
                p['rig'][side+'_hatching']['slot_weights']=((1-t)*slots_a+t*slots_b).tolist()
    def smoothstep(start,end,v):
        u=float(np.clip((v-start)/(end-start),0,1));return u*u*(3-2*u)
    # Optional shapes move while invisible and appear close to their meaningful endpoint.
    for c in ('tongue','tongue_crease','chin','mouth_lower'):
        aa=a['rig'][c]['opacity'];bb=b['rig'][c]['opacity']
        if aa==0 and bb>0:p['rig'][c]['opacity']=bb*smoothstep(.55,.95,t)
        elif bb==0 and aa>0:p['rig'][c]['opacity']=aa*(1-smoothstep(.05,.45,t))
    p['variants']=copy.deepcopy(a['variants'] if t<.5 else b['variants'])
    # Different black/white interiors fade through zero; no color-pop at the mode switch.
    if a['variants']['mouth_interior']!=b['variants']['mouth_interior']:
        p['rig']['mouth_upper']['fill_opacity']=a['rig']['mouth_upper']['fill_opacity']*max(0,1-2*t)+b['rig']['mouth_upper']['fill_opacity']*max(0,2*t-1)
    for side in ('left','right'):
        if a['variants'][side+'_under_eye']!=b['variants'][side+'_under_eye'] and 0<t<1:p['variants'][side+'_under_eye']='mixed'
    p['name']=f"{a.get('name','a')} → {b.get('name','b')} {t:.3f}"
    p['provenance']={'kind':'interpolation','from':a.get('name'),'to':b.get('name'),'t':t}
    for field in ('controls','emotion','expression','recipe','dataset'):p.pop(field,None)
    ea=a.get('emotion',{});eb=b.get('emotion',{})
    if ea.get('taxonomy_id')==eb.get('taxonomy_id')=='emonet_face_40_v1':
        weights=(1-t)*np.array(ea['weights'])+t*np.array(eb['weights'])
        p['emotion']={'taxonomy_id':ea['taxonomy_id'],'category_id':ea.get('category_id') if ea.get('category_id')==eb.get('category_id') else None,
          'weights':weights.tolist(),'label_kind':'intended_procedural_mixture','human_validated':False,
          'mixture':[{'slug':ea.get('slug'),'weight':float(1-t)},{'slug':eb.get('slug'),'weight':float(t)}]}
        p['recipe']={'kind':'interpolation','from':a.get('recipe',{}),'to':b.get('recipe',{}),'weight':t}
    # Authored social performances retain their own sixty-dimensional label space.
    # A cross-catalog transition has two partial target vectors, never a fake
    # hundred-category EmoNet label. These weights are authoring intent only.
    sa=a.get('expression',{});sb=b.get('expression',{})
    if sa.get('catalog_id')=='cartoon_social_60_v1' or sb.get('catalog_id')=='cartoon_social_60_v1':
        weights=(1-t)*np.array(sa.get('weights',[0.]*60))+t*np.array(sb.get('weights',[0.]*60))
        p['expression']={'catalog_id':'cartoon_social_60_v1','category_id':sa.get('category_id') if sa.get('category_id')==sb.get('category_id') else None,
          'weights':weights.tolist(),'label_kind':'intended_social_mixture','human_validated':False,
          'mixture':[{'slug':s['slug'],'weight':float(w)} for s,w in ((sa,1-t),(sb,t)) if s.get('slug')]}
        if bool(ea)!=bool(eb):
            weights=(1-t)*np.array(ea.get('weights',[0.]*40))+t*np.array(eb.get('weights',[0.]*40))
            p['emotion']={'taxonomy_id':'emonet_face_40_v1','category_id':None,'weights':weights.tolist(),
              'label_kind':'intended_cross_catalog_transition','human_validated':False,
              'mixture':[{'slug':e['slug'],'weight':float(w)} for e,w in ((ea,1-t),(eb,t)) if e.get('slug')]}
        p['recipe']={'kind':'interpolation','from':a.get('recipe',{}),'to':b.get('recipe',{}),'weight':t}
    refresh_states(p);validate_pose(p);return p

def interpolate(a,b,frames,out):
    if frames<30:raise ValueError('Validation sequences need at least 30 frames')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);thumbs=[];last=None;max_jump=0
    for i,t in enumerate(np.linspace(0,1,frames)):
        p=interpolate_pose(a,b,t);save_pose(p,out/f'{i:04}.json');render_files(p,out/f'{i:04}.svg',out/f'{i:04}.png')
        arr=np.array([k['xy'] for k in p['keypoints'].values()])
        if last is not None:max_jump=max(max_jump,float(np.linalg.norm(arr-last,axis=1).max()))
        last=arr;im=Image.open(out/f'{i:04}.png');im.thumbnail((362,188));thumbs.append(im)
    indexes=np.linspace(0,frames-1,12,dtype=int);board=Image.new('RGB',(4*362,3*212),'#e5e7eb')
    for j,i in enumerate(indexes):board.paste(thumbs[i],(j%4*362,j//4*212+20));ImageDraw.Draw(board).text((j%4*362+8,j//4*212+4),f't = {i/(frames-1):.2f}',fill='black')
    board.save(out/'contact_sheet.png')
    thumbs[0].save(out/'preview.gif',save_all=True,append_images=thumbs[1:],duration=70,loop=0)
    import json
    report={'frames':frames,'max_landmark_step_normalized':max_jump,'landmark_count':len(a['keypoints']),'method':'linear landmarks, positive widths, smooth optional-shape fades; continuous hatch count'}
    (out/'validation.json').write_text(json.dumps(report,indent=2));return report


def mix_targets(a,b,weight=.5,seed=None,variation=.85):
    """Public authoring helper for separate EmoNet/social label spaces."""
    if not np.isfinite(weight) or not 0<=weight<=1:raise ValueError('Mixture weight must be in [0,1]')
    from .emotion_library import emotion_pose40,mix_emotions
    from .social_expressions import social_pose
    a=a.removeprefix('emonet:');b=b.removeprefix('emonet:')
    if not a.startswith('social:') and not b.startswith('social:'):return mix_emotions(a,b,weight,seed,variation)
    def generate(name,which_seed):
        return social_pose(name[7:],which_seed,variation) if name.startswith('social:') else emotion_pose40(name,which_seed,variation)
    return interpolate_pose(generate(a,seed),generate(b,None if seed is None else seed+1),weight)
