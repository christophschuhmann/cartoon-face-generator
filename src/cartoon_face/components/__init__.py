"""Shared SVG components. No reference-dependent branches or stored outlines."""
import numpy as np
from ..model import points,xy,topology
from ..geometry import ribbon_path, cubic_segments, sample_cubics, path_data, contour_path, mouth_curves

def _band(p,anchors,widths,scales=None,end_tangents=None):
    return ribbon_path(anchors,widths,scales,p.get('geometry',{}).get('ribbon_smoothing',0),end_tangents)

def ribbon(p,name):
    r=p['rig'][name]
    return {'id':name,'kind':'path','d':_band(p,points(p,name),r['widths'],r['tangent_scales']),'fill':'black','opacity':r.get('opacity',1)}

def ellipse(p,name,fill='black'):
    r=p['rig'][name];c=points(p,name)[0]
    return {'id':name,'kind':'ellipse','center':c.tolist(),'rx':r['rx'],'ry':r['ry'],'angle':r.get('angle',0),'fill':fill,'opacity':r.get('opacity',1)}

def eye_opening(p,side):
    u=points(p,side+'_eye_upper');l=points(p,side+'_eye_lower')
    return path_data(np.concatenate([cubic_segments(u,p['rig'][side+'_eye_upper']['tangent_scales']),cubic_segments(l[::-1],p['rig'][side+'_eye_lower']['tangent_scales'][::-1])]),True)

def render_eye(p,side):
    u=points(p,side+'_eye_upper');l=points(p,side+'_eye_lower');out=[]
    pupil=ellipse(p,side+'_pupil');pupil['clip']=side+'_eye_clip';out.append(pupil)
    for name in (side+'_highlight',side+'_secondary_highlight'):
        s=ellipse(p,name,'white');s['clip']=side+'_pupil_clip';out.append(s)
    r=p['rig'][side+'_highlight'];c=xy(p,side+'_pupil_center')+r['heart_offset']
    # Shared four-cubic heart, scaled and rotated as a symbol inside the pupil.
    scale=r['heart_scale'];angle=np.deg2rad(r['heart_angle']);rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    s=np.array([[[0,36],[-13,27],[-47,10],[-36,-9]],[[-36,-9],[-27,-28],[-5,-22],[0,-7]],[[0,-7],[5,-22],[27,-28],[36,-9]],[[36,-9],[47,10],[13,27],[0,36]]],float)*scale
    s=s@rot.T+c
    out.append({'id':side+'_heart','kind':'path','d':path_data(s,True),'fill':'white','opacity':r.get('heart_opacity',0),'clip':side+'_pupil_clip'})
    for c in (side+'_eye_upper',side+'_eye_lower'):out.append(ribbon(p,c))
    r=p['rig'][side+'_eye_side'];end=xy(p,side+'_eye_side_end');start=u[-1]
    mid=(start+end)/2+[r['bulge'],0]
    out.append({'id':side+'_eye_side','kind':'path','d':_band(p,[start,mid,end],[r['width'],r['width'],.5]),'fill':'black','opacity':r['opacity']})
    r=p['rig'][side+'_lash'];sp,_=sample_cubics(cubic_segments(u,p['rig'][side+'_eye_upper']['tangent_scales']),samples=50)
    start=sp[int(r['root_t']*(len(sp)-1))];end=xy(p,side+'_eye_lash_tip');mid=(start+end)/2+[0,r['bend']]
    out.append({'id':side+'_lash','kind':'path','d':_band(p,[start,mid,end],[r['width'],r['width']*.55,1]),'fill':'black','opacity':r['opacity']})
    # Optional lower-corner accents have a fixed relationship to their lid endpoints.
    for i,v in enumerate(p['rig'][side+'_eye_lower'].get('corner_accents',[0,0])):
        if v<=0:continue
        q=l[0] if i==0 else l[-1];sign=1 if q[0]>np.mean(l[:,0]) else -1
        out.append({'id':side+'_lower_accent_'+str(i),'kind':'path','d':_band(p,[q+[sign*24,-6],q+[sign*10,-5],q],[1,5,3]),'fill':'black','opacity':v})
    return out

def render_eyebrow(p,side):return [ribbon(p,side+'_brow'),ribbon(p,side+'_brow_accent')]
def render_moustache(p,side):return [ribbon(p,side+'_moustache')]
def render_nose(p):return [ribbon(p,'nose')]

def render_details(p,side):
    out=[ribbon(p,side+'_'+n) for n in ('lid_accent_inner','lid_accent_outer','under_eye')]
    r=p['rig'][side+'_hatching'];a,b=points(p,side+'_hatching');n=float(r['count'])
    unified=p.get('geometry',{}).get('under_eye_transition')=='stroke_bank_v1'
    if unified:
        # Permanent slots do not redistribute when their visibility/count changes.
        # At foldness=0 they sit on fragments of the continuous curve; at 1 they
        # become tapered parallel folds. Phase and opacity interpolate separately.
        ur=p['rig'][side+'_under_eye'];curve=sample_cubics(cubic_segments(points(p,side+'_under_eye'),ur['tangent_scales']),40)[0]
        distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(curve,axis=0),axis=1))];distance/=max(distance[-1],1e-9)
        phase=r['foldness']
    for i in range(8):
        t=i/7 if unified else i/max(n-1,1)
        slot_opacity=r['slot_weights'][i] if unified else float(np.clip(n-i,0,1))
        if slot_opacity<=0 and not unified:continue
        dx,dy,length=r['offsets'][i];c=(1-t)*a+t*b+[dx,dy];v=np.array([np.cos(np.deg2rad(r['angle'])),np.sin(np.deg2rad(r['angle']))])*r['length']*length/2
        anchors=np.array([c-v,c,c+v]);widths=[.15,r['width'],.15]
        if unified:
            ts=np.array([i,i+.5,i+1])/8
            baseline=np.column_stack([np.interp(ts,distance,curve[:,axis]) for axis in (0,1)])
            anchors=(1-phase)*baseline+phase*anchors
            base_width=np.interp(ts,[0,.5,1],ur['widths'])
            widths=((1-phase)*base_width+phase*np.array(widths)).tolist()
        out.append({'id':side+'_hatch_'+str(i),'kind':'path','d':_band(p,anchors,widths),'fill':'black','opacity':r['opacity']*slot_opacity})
    return out

def render_mouth(p):
    u=points(p,'mouth_upper');l=points(p,'mouth_lower');r=p['rig']['mouth_upper']
    boundary=np.concatenate([cubic_segments(u,p['rig']['mouth_upper']['tangent_scales']),cubic_segments(np.vstack([u[-1],l[::-1],u[0]]))])
    rounding=p.get('geometry',{}).get('mouth_rounding',0)
    if rounding>0:
        lower_scales=[1,*p['rig']['mouth_lower']['tangent_scales'],1]
        us,ls,du,dl=mouth_curves(u,l,r['tangent_scales'],lower_scales,rounding)
        boundary=np.concatenate([us,ls[::-1,::-1]])
    fill='white' if p['variants']['mouth_interior']=='white' else 'black'
    out=[{'id':'mouth_fill','kind':'path','d':path_data(boundary,True),'fill':fill,'opacity':r['fill_opacity']}]
    upper=ribbon(p,'mouth_upper')
    if rounding>0:upper['d']=_band(p,u,r['widths'],r['tangent_scales'],du)
    out.append(upper)
    lr=p['rig']['mouth_lower'];lp=np.vstack([u[0],l,u[-1]])
    out.append({'id':'mouth_lower','kind':'path','d':_band(p,lp,[r['widths'][0],*lr['widths'],r['widths'][-1]],lower_scales if rounding>0 else None,dl if rounding>0 else None),'fill':'black','opacity':lr['opacity']})
    for i,q in enumerate((u[0],u[-1])):
        size=r['corner_size'];sign=1 if i==0 else -1
        out.append({'id':f'mouth_corner_{i}','kind':'path','d':_band(p,[q+[sign*size*.35,8],q+[0,-size*.12],q+[-sign*size*.6,-6]],[.5,r['corner_width'],1]),'fill':'black','opacity':r['corner_accent'][i]})
    tongue=points(p,'tongue');tr=p['rig']['tongue']
    out.append({'id':'tongue','kind':'path','d':contour_path(tongue,tr['tangent_scales']),'fill':'white','stroke':'black','stroke_width':tr['width'],'opacity':tr['opacity']})
    cr=p['rig']['tongue_crease'];start=tongue[-1];end=xy(p,'tongue_crease_tip');mid=(start+end)/2+[cr['bend'],0]
    out.append({'id':'tongue_crease','kind':'path','d':_band(p,[start,mid,end],[cr['width'],cr['width'],.5]),'fill':'black','opacity':cr['opacity']*tr['opacity']})
    out.append(ribbon(p,'chin'));return out
