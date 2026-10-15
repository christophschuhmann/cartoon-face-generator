"""Forty procedural EmoNet-Face cartoon recipes above the unchanged 101-point rig.

Labels/order come from the pinned official taxonomy. Facial cues are authored
cartoon hypotheses, not measured human FACS codes or validated recognition labels.
Only this layer constructs poses; renderer.py remains the one vector renderer.
"""
from functools import lru_cache
from pathlib import Path
import copy
import json
import math
import numpy as np
from .model import WIDTH, HEIGHT, points, xy, set_xy, topology, load_pose, refresh_states, validate_pose
from .geometry import cubic_segments, sample_cubics
from .reference import ROOT
from .expressions import set_variant
from .animation import interpolate_pose

CATALOG_PATH = Path(__file__).parent / 'emotions/catalog.json'

@lru_cache(maxsize=1)
def catalog():
    return json.loads(CATALOG_PATH.read_text(encoding='utf-8'))


def resolve_emotion(name):
    """Accept a stable slug, official label, German label, or paper-era alias."""
    aliases={'hope/optimism':'hope','hope/enthusiasm/optimism':'hope','longing/yearning':'longing',
      'lighthearted fun/amusement':'amusement','thankfulness':'gratitude','thankfulness/gratitude':'gratitude',
      'astonishment':'surprise','astonishment/surprise':'surprise','fatigue/exhaustion':'fatigue',
      'intoxication/altered states':'intoxication','jealousy & envy':'envy','malevolence/malice':'malice',
      'happy':'elation','joy':'elation','sad':'sadness','angry':'anger','afraid':'fear'}
    key=str(name).strip().casefold();key=aliases.get(key,key)
    for profile in catalog()['profiles']:
        if key in (profile['slug'].casefold(),profile['label'].casefold(),profile['label_de'].casefold(),str(profile['id'])):
            return copy.deepcopy(profile)
    if key=='neutral':
        p=copy.deepcopy(catalog()['profiles'][37]);p.update(id=None,slug='neutral',label='Neutral (extra)',label_de='Neutral',family='extra')
        p['actions'].update(brow_raise=0,brow_arch=0,eye_open=1,pupil_scale=1,smile=.08)
        p['options'].update(mouth='closed',under_eye='continuous',tongue='none',highlight='round')
        return p
    raise ValueError(f'Unknown EmoNet emotion: {name}')


def _put(p,component,coords):
    for name,q in zip(topology()['components'][component]['anchors'],coords):
        set_xy(p,name,np.asarray(q,float))


def _translate(p,component,delta):
    _put(p,component,points(p,component)+delta)


def _within_canvas(coords,margin=7):
    """Translate a whole component if needed; never flatten its individual anchors."""
    q=np.asarray(coords,float);delta=np.zeros(2)
    for axis,limit in enumerate((WIDTH,HEIGHT)):
        low=float(q[:,axis].min());high=float(q[:,axis].max())
        if low<margin:delta[axis]=margin-low
        if high+delta[axis]>limit-margin:delta[axis]+=limit-margin-(high+delta[axis])
    return q+delta,delta


def sample_actions(profile,seed=None,variation=.65):
    """Correlated, bounded nuisance variation around one authored emotion signature.

    Opening and tension share activation; eyebrow/eye/mouth asymmetry share one
    lateral latent. Gaze and style have smaller separate latents. Closed mouths
    remain closed; the required wink/closed-eyes cues are explicitly preserved.
    """
    if not math.isfinite(variation) or not 0<=variation<=1:raise ValueError('variation must be in [0,1]')
    a=copy.deepcopy(profile['actions'])
    if seed is None or variation==0:return a,{}
    rng=np.random.default_rng(seed);z=np.clip(rng.normal(size=6),-1.65,1.65)
    v=profile['variation'];activation=z[0]*v['strength']*variation;lateral=z[1]*v['asymmetry']*variation
    gaze=z[2:4]*v['gaze']*variation;mouth=z[4]*v['mouth']*variation;style=z[5]*v['style']*variation
    a['brow_raise']+=activation*.75;a['eye_open']+=activation*.45
    a['brow_asym']+=lateral;a['eye_asym']+=lateral*.7;a['mouth_asym']+=lateral*.8
    a['gaze_x']+=gaze[0];a['gaze_y']+=gaze[1]
    a['mouth_width']*=1+activation*.15+mouth*.4
    a['smile']+=mouth*.6+activation*(.3 if profile['family']=='positive' else -.1)
    a['mouth_open']*=1+activation*.25+mouth*.3
    a['pupil_scale']*=1+activation*.1+style
    a['cheek_lift']+=activation*.3;a['curl']+=style*3
    a['warmth']=float(np.clip(a.get('warmth',.35)+style*.6,0,1))
    # Vary expressive intensity visibly, while preserving the signed mouth cue.
    # A neutral line receives very little curvature; wider nuisance variation
    # instead comes from gaze, width, asymmetry, and local pupil size.
    base=profile['actions'];smile=base['smile']
    if abs(smile)<=.15:a['smile']=float(np.clip(a['smile'],smile-.07,smile+.07))
    elif smile>.3:a['smile']=float(np.clip(a['smile'],max(.33,smile-.22),smile+.22))
    elif smile<-.3:a['smile']=float(np.clip(a['smile'],smile-.22,min(-.32,smile+.22)))
    if profile['slug']=='contempt':a['mouth_asym']=max(.8,a['mouth_asym'])
    if profile['slug'] in ('fear','surprise'):
        a['eye_open']=max(1.26,a['eye_open']);a['eye_asym']=float(np.clip(a['eye_asym'],-.08,.08))
    elif profile['slug'] not in ('pleasure_ecstasy','pain','teasing','sourness'):
        a['eye_open']=max(.19,a['eye_open'])
        a['eye_asym']=float(np.clip(a['eye_asym'],-2*(a['eye_open']-.14),2*(a['eye_open']-.14)))
    if profile['slug'] in ('pleasure_ecstasy','pain'):
        a['eye_open']=float(np.clip(a['eye_open'],.035,.075));a['eye_asym']=0
    if profile['slug']=='teasing':
        left=.05;right=float(np.clip(a['eye_open']-a['eye_asym']/2,.9,1.15))
        a['eye_open']=(left+right)/2;a['eye_asym']=left-right
    a['eye_open']=float(np.clip(a['eye_open'],.035,1.5));a['pupil_scale']=float(np.clip(a['pupil_scale'],.6,1.25))
    a['mouth_open']=float(np.clip(a['mouth_open'],0,.9));a['mouth_width']=float(np.clip(a['mouth_width'],.3,1.5))
    a['gaze_x']=float(np.clip(a['gaze_x'],-1,1));a['gaze_y']=float(np.clip(a['gaze_y'],-1,1))
    latents={'activation':float(activation),'lateral':float(lateral),'gaze':gaze.tolist(),'mouth':float(mouth),'style':float(style)}
    return a,latents


def _brows(p,side,a):
    if 'brow_raise_'+side in a:
        a=dict(a)
        for key in ('brow_raise','brow_inner','brow_outer','frown'):a[key]=a.get(key+'_'+side,a[key])
        a['brow_asym']=0.
    old=points(p,side+'_brow');q=old.copy();t=np.linspace(0,1,5)
    lateral=a['brow_asym']*(1 if side=='left' else -1)
    # A neutral arch preserves fitted x spacing and width, but removes the
    # original smile's baked-in brow slope before authoring fear/anger/sadness.
    eye_y=points(p,side+'_eye_upper')[2,1]
    q[:,1]=eye_y-100+np.array([5,-24,-38,-18,7])-27*(a['brow_raise']+lateral)
    q[:,1]-=40*a['brow_inner']*t**1.4+24*a['brow_outer']*(1-t)**1.4+38*a['brow_arch']*np.sin(np.pi*t)
    # Inner raising and contraction may coexist (worry); do not accidentally
    # turn every contracted brow into an angry lowered inner endpoint.
    inner_drop=60*a['frown']*(1-np.clip(a['brow_inner'],0,1))*(1-.07*a.get('warmth',0))
    q[:,1]+=inner_drop*t**1.5-a['frown']*20*(1-t)
    q[:,0]+=(-1 if side=='left' else 1)*a['frown']*12*t
    q,_=_within_canvas(q,margin=25)
    _put(p,side+'_brow',q);_translate(p,side+'_brow_accent',q[-1]-old[-1])
    p['rig'][side+'_brow']['widths']=[w*(1+.06*a['frown']) for w in p['rig'][side+'_brow']['widths']]


def _eyes(p,side,a,options):
    old_u=points(p,side+'_eye_upper');old_l=points(p,side+'_eye_lower');u=old_u.copy();l=old_l.copy()
    v=float(np.clip(a['eye_open']+(a['eye_asym']/2 if side=='left' else -a['eye_asym']/2),.035,1.55))
    t=np.linspace(0,1,5);lower_curve=np.polyfit(old_l[:,0],old_l[:,1],2);baseline=np.polyval(lower_curve,u[:,0])
    u[:,1]=baseline-(baseline-u[:,1])*v
    u[:,1]-=15*a['lid_curve']*np.sin(np.pi*t)
    u[:,1]+=22*a['lid_tilt']*(.5-t)
    l[1,1]-=a.get('squint_'+side,a['squint'])*(26 if 'squint_'+side in a else 18)
    if v<.12:
        # Closure can be smiling (arch up) or painful (arch down), with the same IDs.
        ends=np.interp(t,[0,1],[old_l[0,1],old_l[-1,1]])
        u[:,1]=ends-20*a['lid_curve']*np.sin(np.pi*t)
        l=np.array([u[0],u[2],u[-1]])
    _put(p,side+'_eye_upper',u);_put(p,side+'_eye_lower',l)
    p['rig'][side+'_eye_upper']['widths']=[max(1.5,w*(.65+.35*min(v,1))) for w in p['rig'][side+'_eye_upper']['widths']]
    p['rig'][side+'_eye_lower']['opacity']=0 if v<.12 else 1
    end=xy(p,side+'_eye_side_end');set_xy(p,side+'_eye_side_end',u[-1]+(end-old_u[-1])*min(v,1.2))
    p['rig'][side+'_eye_side']['opacity']=0 if v<.12 else p['rig'][side+'_eye_side']['opacity']
    lash=p['rig'][side+'_lash'];idx=int(lash['root_t']*200)
    scales=p['rig'][side+'_eye_upper']['tangent_scales']
    origin_old=sample_cubics(cubic_segments(old_u,scales),50)[0][idx]
    origin_new=sample_cubics(cubic_segments(u,scales),50)[0][idx]
    set_xy(p,side+'_eye_lash_tip',origin_new+(xy(p,side+'_eye_lash_tip')-origin_old)*(1-.14*a.get('warmth',0)))
    lash['width']=max(lash['width'],12)*(.8+.2*min(v,1))
    if v<.12:
        # One soft outward flourish on a closed lid; the former long downward
        # lash crossed the wink line and made the junction look fractured.
        lash.update(root_t=.91,bend=2.5,width=8.)
        origin_new=sample_cubics(cubic_segments(u,scales),50)[0][182]
        set_xy(p,side+'_eye_lash_tip',origin_new+[(1 if side=='left' else -1)*34,-4])
    # Decorations follow their parent region, while continuous wrinkles stay separate.
    for suffix in ('lid_accent_inner','lid_accent_outer'):
        _translate(p,side+'_'+suffix,[0,(u[:,1]-old_u[:,1]).mean()*.45])
        p['rig'][side+'_'+suffix]['opacity']=0 if v<.12 else 1
    # Identical attachment geometry for every category; variants are only a
    # continuous stroke-bank phase, never a category-specific wrinkle topology.
    wrinkle=[l[0]+[0,23],.48*l[0]+.52*l[1]+[0,26],.10*l[0]+.90*l[1]+[0,26]]
    _put(p,side+'_under_eye',wrinkle)
    inner=.35*l[0]+.65*l[1]+[0,31];outer=.85*l[-1]+.15*l[1]+[0,31]
    _put(p,side+'_hatching',[inner,outer])
    h=p['rig'][side+'_hatching'];h.update(count=5,length=44,width=5,angle=-52,offsets=[[0,0,1] for _ in range(8)],slot_weights=[1.,0.,1.,0.,1.,1.,0.,1.])
    set_variant(p,side+'_under_eye',options['under_eye'],refresh=False)
    # Position the pupil in the current opening, not by scaling an entire eye.
    independent='gaze_x_'+side in a
    old_center=xy(p,side+'_pupil_center')
    travel_x=abs(u[-1,0]-u[0,0])*.31 if independent else 38
    center=(u[2]+l[1])/2+[a.get('gaze_x_'+side,a['gaze_x'])*travel_x,0]
    pp=p['rig'][side+'_pupil'];scale=a['pupil_scale']*max(.78,min(1,np.sqrt(v)))
    pp.update(rx=pp['rx']*scale,ry=pp['ry']*scale,openness=min(1,v),opacity=1)
    warmth=a.get('warmth',0)
    pp['rx']*=1+.10*warmth;pp['ry']*=1+.05*warmth;pp['angle']*=1-.16*warmth
    lower_at_pupil=np.polyval(np.polyfit(l[:,0],l[:,1],2),center[0])
    center[1]=(u[2,1]+l[1,1])/2 if v>1.12 else lower_at_pupil-pp['ry']*.93
    gaze_y=a.get('gaze_y_'+side,a['gaze_y'])
    # Extreme gaze may put 3/4 of an iris behind a lid. The clip, rather than
    # clamping the pupil into the opening, determines the visible crescent.
    travel_y=(abs(l[1,1]-u[2,1])*.52+pp['ry']*.28) if independent else 26
    center[1]+=gaze_y*travel_y
    set_xy(p,side+'_pupil_center',center)
    for suffix in ('highlight','secondary_highlight'):
        c=side+'_'+suffix;old=points(p,c)[0];_put(p,c,[center+(old-old_center)*scale])
        for radius in ('rx','ry'):p['rig'][c][radius]*=scale*(1+.20*warmth if suffix=='highlight' else 1)
    if v>=.12 and not independent:
        # A readable light glint follows the visible iris segment in narrow eyes.
        # Keeping the original upward offset would hide it entirely behind the lid.
        samples=sample_cubics(cubic_segments(u),32)[0];order=np.argsort(samples[:,0])
        glint=xy(p,side+'_highlight_center')
        top=np.interp(glint[0],samples[order,0],samples[order,1])
        bottom=np.polyval(np.polyfit(l[:,0],l[:,1],2),glint[0])
        # Fit the whole glint below the inked upper lid, not just its center.
        # Otherwise larger warm highlights become angular cut-off white patches.
        hr=p['rig'][side+'_highlight'];ui=np.argsort(u[:,0]);li=np.argsort(l[:,0])
        upper_ink=np.interp(glint[0],u[ui,0],np.array(p['rig'][side+'_eye_upper']['widths'])[ui])/2
        lower_ink=np.interp(glint[0],l[li,0],np.array(p['rig'][side+'_eye_lower']['widths'])[li])/2
        angle=np.deg2rad(hr['angle']);radius_y=np.hypot(hr['rx']*np.sin(angle),hr['ry']*np.cos(angle))
        room=max(3,(bottom-top-upper_ink-lower_ink-4)/2)
        resize=min(1,room/max(radius_y,1e-6));hr['rx']*=resize;hr['ry']*=resize;radius_y*=resize
        low=top+upper_ink+radius_y+2;high=bottom-lower_ink-radius_y-2
        glint[1]=np.clip(glint[1],low,high) if low<=high else (top+bottom)/2
        set_xy(p,side+'_highlight_center',glint)
    hr=p['rig'][side+'_highlight'];hr['heart_scale']=.92*scale;hr['heart_offset']=[8*scale,17*scale]
    set_variant(p,side+'_highlight',options['highlight'])


def _mouth(p,a,options):
    cx=725.;cy=624.+a['mouth_y']*15;width=210*a['mouth_width'];depth=115*a['mouth_open']
    xs=cx+width/2*np.array([-1,-.52,0,.52,1])
    ys=cy+a['smile']*np.array([-35,7,20,7,-35])+a['mouth_asym']*np.array([20,11,0,-11,-20])
    ys+=a['mouth_tension']*np.array([0,-8,0,8,0])
    if options['mouth'] in ('round','pucker'):
        depth=max(12,depth);height=depth+15
        quarter=np.sqrt(.5)
        xs=cx+width/2*np.array([-1,-quarter,0,quarter,1])
        ys=cy-height/2*np.array([0,quarter,1,quarter,0])+a['mouth_asym']*np.array([10,5,0,-5,-10])
        lower=np.column_stack([cx+width/2*np.array([-quarter,0,quarter]),cy+height/2*np.array([quarter,1,quarter])])
    else:
        lower=np.column_stack([cx+width/2*np.array([-.52,0,.52]),ys[[1,2,3]]+depth*np.array([.72,1,.72])])
    # Optional live lip gesture, separate from the tongue, with stable anchors.
    pout=float(np.clip(a.get('lip_pout',0),0,1))
    pucker=float(np.clip(a.get('mouth_pucker',0),0,1))
    if pout or pucker:
        ys+=pout*np.array([0,-5,-12,-5,0])
        lower[:,1]+=pout*np.array([2,10,2])
        round_top=cy-(8+depth*.18)*np.array([0,.72,1,.72,0])
        ys=ys*(1-pucker*.72)+round_top*pucker*.72
    upper=np.column_stack([xs,ys]);_put(p,'mouth_upper',upper);_put(p,'mouth_lower',lower)
    ur=p['rig']['mouth_upper'];lr=p['rig']['mouth_lower']
    opened=options['mouth']!='closed' and a['mouth_open']>.015
    p['geometry']['mouth_rounding']=1. if options['mouth'] in ('round','pucker') else (.28 if opened and options['mouth']=='teeth' else .08 if opened else 0.)
    ur.update(widths=[2,7,9,7,2],tangent_scales=[1,1,1,1,1],fill_opacity=int(opened),corner_accent=[0,0])
    lr.update(widths=[5,6,5],opacity=int(opened),tangent_scales=[1,1,1])
    if pout:
        lr.update(widths=[5+3*pout,6+8*pout,5+3*pout],opacity=max(int(opened),pout))
    p['variants']['mouth_interior']='white' if options['mouth'] in ('teeth','pucker') else 'dark'
    if options['mouth'] in ('round','pucker'):
        ur.update(widths=[3,4,4,4,3],tangent_scales=[1,1.12,1.12,1.12,1])
        lr['tangent_scales']=[1.12]*3
    if a['smile']>.3 and options['mouth'] not in ('round','pucker'):
        ur['corner_accent']=[1,1];ur['corner_size']=20;ur['corner_width']=7
    mode=options['tongue'];tr=p['rig']['tongue'];cr=p['rig']['tongue_crease']
    tr['opacity']=int(mode!='none' and opened);cr['opacity']=int(mode=='out' and opened)
    half=max(20,width*.2)
    if mode=='inside':
        bottom=lower[1,1]-6;root=bottom-max(14,min(42,depth*.5))
        tongue=[[cx-half,root],[cx-half*.65,bottom-6],[cx,bottom],[cx+half*.65,bottom-6],[cx+half,root],[cx,root-13]]
    else:
        root=ys[2]+2;length=68
        tongue=[[cx-half,root],[cx-half*.78,root+length*.7],[cx+8,root+length],[cx+half*1.1,root+length*.7],[cx+half,root-7],[cx,root]]
    _put(p,'tongue',tongue);tr.update(width=6,tangent_scales=[1]*6)
    set_xy(p,'tongue_crease_tip',[cx+15,ys[2]+48]);cr.update(width=4,bend=12)
    _put(p,'chin',[[cx-27,cy+55],[cx,cy+60],[cx+27,cy+55]])
    p['rig']['chin']['opacity']=int(options['mouth']=='closed' and a['smile']>.35)


@lru_cache(maxsize=1)
def _base_pose(modified_ns):
    return load_pose(ROOT/'poses/smile.json')


def build_pose(profile,actions,finalize=True):
    """Resolve compact expression actions into a complete, independently renderable pose."""
    p=copy.deepcopy(_base_pose((ROOT/'poses/smile.json').stat().st_mtime_ns));a=actions;opt=profile['options']
    # Opt-in geometry is saved in the pose. Old reference and recipe-1.0 JSONs
    # retain their exact original paths when this block is absent.
    p['geometry']={'version':'smooth_v1','ribbon_smoothing':1.,'mouth_rounding':0.,'under_eye_transition':'stroke_bank_v1'}
    # Fitted extremes are useful for exact reference matching, but mild handle
    # relaxation keeps novel expression curves supple without moving anchors.
    for spec in p['rig'].values():
        if 'tangent_scales' in spec:spec['tangent_scales']=[.90*s+.10 for s in spec['tangent_scales']]
    p['rig']['tongue']['opacity']=p['rig']['tongue_crease']['opacity']=p['rig']['chin']['opacity']=0
    for side in ('left','right'):
        _brows(p,side,a);_eyes(p,side,a,opt)
        _translate(p,side+'_moustache',[0,-a['cheek_lift']*11])
        band=points(p,side+'_moustache');pivot=band[4];theta=a['curl']*.2;rot=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
        band[5:]=pivot+(band[5:]-pivot)@rot.T;_put(p,side+'_moustache',band)
    _translate(p,'nose',[0,-a['nose_lift']*10]);_mouth(p,a,opt)
    # Bounded recipes should not hit this fallback; record any correction explicitly.
    adjustments={}
    for c,spec in topology()['components'].items():
        arr=points(p,c);bounded,delta=_within_canvas(arr)
        if np.any(np.abs(delta)>1e-9):_put(p,c,bounded);adjustments[c]=delta.tolist()
    p['name']=profile['slug'];p.pop('controls',None)
    p['provenance']={'kind':'procedural_emonet','base_pose':'smile','recipe_version':catalog()['recipe_version'],'bounds_adjustments':adjustments}
    if finalize:refresh_states(p);validate_pose(p)
    return p


def emotion_pose40(name,seed=None,variation=.65,intensity=1):
    if not math.isfinite(intensity) or not 0<=intensity<=1:raise ValueError('intensity must be in [0,1]')
    profile=resolve_emotion(name);actions,latents=sample_actions(profile,seed,variation);p=build_pose(profile,actions)
    if intensity<1:
        neutral=resolve_emotion('neutral');p=interpolate_pose(build_pose(neutral,neutral['actions']),p,intensity)
    category_id=profile['id'];weights=[0.]*40
    if category_id is not None:weights[category_id-1]=float(intensity)
    p['name']=profile['slug']+(f'_seed{seed}' if seed is not None else '_archetype')
    p['emotion']={'taxonomy_id':catalog()['taxonomy_id'],'category_id':category_id,'slug':profile['slug'],'label':profile['label'],
      'intensity':float(intensity),'weights':weights,'label_kind':'intended_procedural_target','human_validated':False}
    p['recipe']={'version':catalog()['recipe_version'],'seed':seed,'variation':float(variation) if seed is not None else 0.,'intensity':float(intensity),'actions':actions,'latents':latents,'options':copy.deepcopy(profile['options'])}
    refresh_states(p);validate_pose(p);return p


RECOMMENDED_PAIRS=(('amusement','teasing'),('elation','triumph'),('pleasure_ecstasy','contentment'),('contentment','relief'),
 ('gratitude','affection'),('infatuation','affection'),('hope','interest'),('triumph','pride'),('awe','surprise'),('concentration','contemplation'),
 ('doubt','confusion'),('fear','distress'),('distress','helplessness'),('embarrassment','shame'),('disappointment','sadness'),
 ('sadness','helplessness'),('bitterness','envy'),('contempt','malice'),('disgust','sourness'),('anger','impatience'),('fatigue','numbness'))


def compatibility(a,b):
    pa,pb=resolve_emotion(a),resolve_emotion(b);pair=frozenset((pa['slug'],pb['slug']))
    if pa['slug']==pb['slug'] or pair in map(frozenset,RECOMMENDED_PAIRS):kind='recommended'
    elif pa['family']==pb['family']:kind='related'
    else:kind='ambivalent'
    return {'kind':kind,'basis':'authored cartoon mixing policy, not an empirical psychological compatibility score',
      'interpretation':'blend of two intended targets; does not become a separately verified pure category'}


def mix_emotions(a,b,weight=.5,seed=None,variation=.65):
    """Blend full vector state with stable IDs; weight 0 is a, weight 1 is b."""
    if not math.isfinite(weight) or not 0<=weight<=1:raise ValueError('weight must be in [0,1]')
    pa=emotion_pose40(a,seed,variation);pb=emotion_pose40(b,None if seed is None else seed+1,variation)
    p=interpolate_pose(pa,pb,weight);weights=(1-weight)*np.array(pa['emotion']['weights'])+weight*np.array(pb['emotion']['weights'])
    p['emotion']={'taxonomy_id':catalog()['taxonomy_id'],'category_id':None,'slug':None,'label_kind':'intended_procedural_mixture','human_validated':False,
      'weights':weights.tolist(),'mixture':[{'slug':resolve_emotion(a)['slug'],'weight':float(1-weight)},{'slug':resolve_emotion(b)['slug'],'weight':float(weight)}],
      'compatibility':compatibility(a,b)}
    p['recipe']={'version':catalog()['recipe_version'],'kind':'mixture','from':pa['recipe'],'to':pb['recipe'],'weight':float(weight)}
    p['name']=f'{resolve_emotion(a)["slug"]}_{resolve_emotion(b)["slug"]}_{weight:.3f}'
    return p
