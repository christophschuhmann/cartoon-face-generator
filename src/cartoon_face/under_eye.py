"""One continuous under-eye system: a curve and eight permanent morph slots.

The five semantic anchors remain unchanged (three curve anchors, two fold-zone
anchors). Slot geometry is derived, never extra or reassigned landmark IDs.
"""
import numpy as np

MODE='stroke_bank_v1'
STYLE_BLEND={'none':0.,'continuous':0.,'mixed':.55,'hatching':1.}


def set_under_eye_blend(p,side,value,presence=1.):
    value=float(value);presence=float(presence)
    if side not in ('left','right') or not np.isfinite(value) or not 0<=value<=1 or not 0<=presence<=1:
        raise ValueError('Under-eye blend/presence must be in [0,1]')
    p.setdefault('geometry',{'version':'smooth_v1','ribbon_smoothing':0.,'mouth_rounding':0.})['under_eye_transition']=MODE
    for other in ('left','right'):
        other_h=p['rig'][other+'_hatching']
        if 'slot_weights' not in other_h:
            count=int(np.clip(round(other_h['count']),0,8));weights=np.zeros(8)
            if count:weights[np.rint(np.linspace(0,7,count)).astype(int)]=1.
            other_h['slot_weights']=weights.tolist()
            other_h['foldness']=STYLE_BLEND[p['variants'][other+'_under_eye']]
    u=p['rig'][side+'_under_eye'];h=p['rig'][side+'_hatching']
    u['opacity']=presence*(1-value);h['opacity']=presence*value;h['foldness']=value
    return p


def set_under_eye_style(p,side,style):
    if style not in STYLE_BLEND:raise ValueError('Unknown under-eye style')
    return set_under_eye_blend(p,side,STYLE_BLEND[style],0. if style=='none' else 1.)
