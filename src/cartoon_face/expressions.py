"""Correlated expression controls above the shared semantic rig.
Controls edit the serialized geometry; there is no second renderer or hidden template.
"""
import copy
from pathlib import Path
import numpy as np
from .model import xy,set_xy,points,load_pose,topology,refresh_states,validate_pose
from .reference import ROOT

EMOTIONS=('neutral','happy','joy','love','proud','sad','angry','surprised','afraid','worried','disgust','sleepy','wink','playful')


def set_variant(p,name,value):
    p['variants'][name]=value
    if name.endswith('_under_eye'):
        side=name.removesuffix('_under_eye')
        if p.get('geometry',{}).get('under_eye_transition')=='stroke_bank_v1':
            from .under_eye import set_under_eye_style
            set_under_eye_style(p,side,value)
        else:p['rig'][side+'_under_eye']['opacity']=float(value in ('continuous','mixed'));p['rig'][side+'_hatching']['opacity']=float(value in ('hatching','mixed'))
    elif name.endswith('_highlight'):
        side=name.removesuffix('_highlight');p['rig'][side+'_highlight']['heart_opacity']=float(value=='heart')
    return refresh_states(p)


def eye_openness(p,side,value,squint=0):
    """Independent upper/lower lid deformation, plus cheek-squint curvature.
    This is deliberately not a vertical scaling of a whole eye.
    """
    value=float(np.clip(value,0,1.6));u=points(p,side+'_eye_upper');l=points(p,side+'_eye_lower')
    # A quadratic lower lid defines the closure curve, separately from upper arch geometry.
    co=np.polyfit(l[:,0],l[:,1],2);baseline=np.polyval(co,u[:,0])
    for i,(name,q) in enumerate(zip(topology()['components'][side+'_eye_upper']['anchors'],u)):
        q[1]=baseline[i]-(baseline[i]-q[1])*value-squint*14*np.sin(i*np.pi/4);set_xy(p,name,q)
    for i,(name,q) in enumerate(zip(topology()['components'][side+'_eye_lower']['anchors'],l)):
        q[1]-=squint*20*np.sin(i*np.pi/2);set_xy(p,name,q)
    if value<1:
        r=p['rig'][side+'_eye_upper'];r['widths']=[w*(.5+.5*value) for w in r['widths']]
        p['rig'][side+'_eye_side']['opacity']*=value
        p['rig'][side+'_eye_lower']['opacity']*=min(1,value*2)
        # Pupil occlusion comes from the actual opening clip, preserving solid black ink.
    p['rig'][side+'_pupil']['openness']=min(1,value)
    return refresh_states(p)


def shift_component(p,c,dx=0,dy=0,scale_x=1,scale_y=1):
    a=points(p,c);center=a.mean(axis=0)
    for name,q in zip(topology()['components'][c]['anchors'],a):set_xy(p,name,center+(q-center)*[scale_x,scale_y]+[dx,dy])


def apply_controls(p,controls):
    """Apply deltas to a loaded pose. UI rebuilds from its base state for every slider update."""
    p=copy.deepcopy(p)
    for side in ('left','right'):
        if side+'_under_eye_blend' in controls:
            from .under_eye import set_under_eye_blend
            set_under_eye_blend(p,side,controls[side+'_under_eye_blend'])
        if side+'_eye_openness' in controls or side+'_squint' in controls:eye_openness(p,side,controls.get(side+'_eye_openness',1),controls.get(side+'_squint',0))
        if side+'_brow_raise' in controls:shift_component(p,side+'_brow',dy=-controls[side+'_brow_raise']*55)
        if side+'_brow_tilt' in controls:
            a=points(p,side+'_brow');cx=a[:,0].mean();v=controls[side+'_brow_tilt']
            for name,q in zip(topology()['components'][side+'_brow']['anchors'],a):q[1]+=(q[0]-cx)*v*.25;set_xy(p,name,q)
        if side+'_moustache_curl' in controls:
            a=points(p,side+'_moustache');pivot=a[4];angle=np.deg2rad(controls[side+'_moustache_curl']*28);r=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
            for name,q in zip(topology()['components'][side+'_moustache']['anchors'][5:],a[5:]):set_xy(p,name,pivot+(q-pivot)@r.T)
        if side+'_moustache_width' in controls:p['rig'][side+'_moustache']['widths']=[float(w*controls[side+'_moustache_width']) for w in p['rig'][side+'_moustache']['widths']]
        if side+'_pupil_scale' in controls:
            for dim in ('rx','ry'):p['rig'][side+'_pupil'][dim]*=controls[side+'_pupil_scale']
        gaze=np.array([controls.get('gaze_x',0)*22,controls.get('gaze_y',0)*18])
        for suffix in ('pupil_center','highlight_center','secondary_highlight_center'):set_xy(p,side+'_'+suffix,xy(p,side+'_'+suffix)+gaze)
    if 'smile' in controls:
        a=points(p,'mouth_upper');v=controls['smile']
        for i,(n,q) in enumerate(zip(topology()['components']['mouth_upper']['anchors'],a)):
            q[1]+=v*40*np.sin(i*np.pi/4);set_xy(p,n,q)
        for side in ('left','right'):shift_component(p,side+'_moustache',dy=-abs(v)*4)
    if 'mouth_open' in controls:
        v=max(0,controls['mouth_open']);u=points(p,'mouth_upper')
        low=np.stack([(u[0]*.7+u[-1]*.3),u[2],(u[0]*.3+u[-1]*.7)])
        low[:,1]+=[v*65,v*125,v*65]
        for n,q in zip(topology()['components']['mouth_lower']['anchors'],low):set_xy(p,n,q)
        p['rig']['mouth_upper']['fill_opacity']=min(1,v*5);p['rig']['mouth_lower']['opacity']=min(1,v*5)
    for k in p['keypoints'].values():k['xy']=np.clip(k['xy'],.004,.996).tolist()
    p['controls']=dict(controls);refresh_states(p);validate_pose(p);return p


def emotion_pose(name,intensity=1):
    if name not in EMOTIONS:raise ValueError(f'Unknown emotion {name}')
    if not 0<=intensity<=1:raise ValueError('Emotion intensity must be in [0,1]')
    bases={'neutral':'smile','happy':'cheeky','joy':'love','love':'love','proud':'skeptical','sad':'smile','angry':'skeptical','surprised':'tongue','afraid':'tense','worried':'tense','disgust':'skeptical','sleepy':'smile','wink':'cheeky','playful':'tongue'}
    p=load_pose(ROOT/f'poses/{bases[name]}.json');p['name']=name;p['provenance']={'source':'shared emotion controls','base':bases[name]}
    if name not in ('playful','love','joy'):
        p['rig']['tongue']['opacity']=0;p['rig']['tongue_crease']['opacity']=0
    if name!='love':
        for side in ('left','right'):set_variant(p,side+'_highlight','round')
    if name=='neutral':
        p=apply_controls(p,{'smile':-.55});p['rig']['mouth_upper']['corner_accent']=[0,0]
    elif name=='happy':p=apply_controls(p,{'left_eye_openness':.85,'right_eye_openness':.85,'left_squint':.55,'right_squint':.55,'smile':.2})
    elif name=='joy':p=apply_controls(p,{'left_eye_openness':.6,'right_eye_openness':.6,'left_squint':.8,'right_squint':.8,'left_brow_raise':.2,'right_brow_raise':.2})
    elif name=='proud':p=apply_controls(p,{'left_eye_openness':.8,'right_eye_openness':.75,'smile':.05})
    elif name in ('sad','worried','afraid'):
        for side in ('left','right'):
            a=points(p,side+'_brow')
            for i,(n,q) in enumerate(zip(topology()['components'][side+'_brow']['anchors'],a)):
                q[1]+=(20-65*i/4);set_xy(p,n,q)
        if name=='sad':
            # Symmetric downturned mouth, preserving the same corner identities.
            for n,q in zip(topology()['components']['mouth_upper']['anchors'],[[625,622],[658,599],[725,587],[785,599],[820,622]]):set_xy(p,n,q)
            p['rig']['mouth_upper']['corner_accent']=[0,0];p=apply_controls(p,{'left_eye_openness':.78,'right_eye_openness':.78,'gaze_y':.65})
        elif name=='afraid':p=apply_controls(p,{'left_eye_openness':1.16,'right_eye_openness':1.16,'left_pupil_scale':.8,'right_pupil_scale':.8,'mouth_open':.65})
        else:p=apply_controls(p,{'left_eye_openness':.85,'right_eye_openness':1,'gaze_x':-.4})
    elif name=='angry':
        for side in ('left','right'):
            a=points(p,side+'_brow')
            for i,(n,q) in enumerate(zip(topology()['components'][side+'_brow']['anchors'],a)):
                q[1]+=-25+60*i/4;set_xy(p,n,q)
        p=apply_controls(p,{'left_eye_openness':.68,'right_eye_openness':.68})
        for n,q in zip(topology()['components']['mouth_upper']['anchors'],[[625,626],[670,614],[724,607],[778,614],[823,626]]):set_xy(p,n,q)
        for n,q in zip(topology()['components']['mouth_lower']['anchors'],[[658,650],[724,656],[790,650]]):set_xy(p,n,q)
        p['variants']['mouth_interior']='white'
        p['rig']['mouth_upper'].update({'fill_opacity':1,'corner_accent':[0,0],'widths':[4,5,6,5,4]})
        p['rig']['mouth_lower'].update({'opacity':1,'widths':[5,6,5]})
        p['rig']['chin']['opacity']=0
    elif name=='surprised':
        p=apply_controls(p,{'left_brow_raise':.15,'right_brow_raise':.15,'left_pupil_scale':.7,'right_pupil_scale':.7})
        for side in ('left','right'):
            c=points(p,side+'_eye_upper').mean(axis=0)+[0,35];old=xy(p,side+'_pupil_center');delta=c-old
            for suffix in ('pupil_center','highlight_center','secondary_highlight_center'):set_xy(p,side+'_'+suffix,xy(p,side+'_'+suffix)+delta)
        for n,q in zip(topology()['components']['mouth_upper']['anchors'],[[667,632],[680,601],[722,585],[764,601],[777,632]]):set_xy(p,n,q)
        for n,q in zip(topology()['components']['mouth_lower']['anchors'],[[680,678],[722,700],[764,678]]):set_xy(p,n,q)
        p['rig']['mouth_upper'].update({'fill_opacity':1,'corner_accent':[0,0],'widths':[3,4,5,4,3]})
        p['rig']['mouth_lower'].update({'opacity':1,'widths':[4,4,4]})
        p['rig']['mouth_upper']['tangent_scales']=[1.8,1.0,1.1,1.0,1.8]
        for side in ('left','right'):p['rig'][side+'_moustache']['tangent_scales'][1]=1.0
    elif name=='disgust':p=apply_controls(p,{'left_eye_openness':.52,'right_eye_openness':.9,'left_brow_raise':-.25,'right_brow_raise':.15,'gaze_x':.7,'smile':-.6})
    elif name=='sleepy':p=apply_controls(p,{'left_eye_openness':.03,'right_eye_openness':.03,'smile':-.25})
    elif name=='wink':p=apply_controls(p,{'left_eye_openness':.03,'right_eye_openness':.9,'left_brow_raise':-.1,'right_brow_raise':.2,'smile':.25})
    # Keep all normalized points valid even for strong brow raises near the crop edge.
    for k in p['keypoints'].values():k['xy']=np.clip(k['xy'],.005,.995).tolist()
    p['emotion']={'name':name,'intensity':float(intensity)};refresh_states(p);validate_pose(p)
    if intensity<1:
        from .animation import interpolate_pose
        p=interpolate_pose(emotion_pose('neutral',1) if name!='neutral' else p,p,float(intensity));p['emotion']={'name':name,'intensity':float(intensity)}
    return p
