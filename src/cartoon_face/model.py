"""Versioned pose contract and central stable landmark registry."""
from pathlib import Path
import copy,json,math
from functools import lru_cache
import numpy as np

WIDTH,HEIGHT=1450,750
SCHEMA='1.0';TOPOLOGY='cartoon_face_v1'
TOPOLOGY_PATH=Path(__file__).parent/'topology/face_topology.json'

@lru_cache(maxsize=1)
def topology():return json.loads(TOPOLOGY_PATH.read_text())
def load_pose(path):
    p=json.loads(Path(path).read_text());validate_pose(p);return p

def save_pose(p,path):
    validate_pose(p);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(p,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def xy(p,name):
    """Read one normalized landmark in canonical pixels (1450 x 750).

    Rig lengths also use this canonical space; output-resolution scaling happens
    once, in the SVG viewBox. 'left' always means the character's left.
    """
    return np.asarray(p['keypoints'][name]['xy'],float)*[WIDTH,HEIGHT]

def set_xy(p,name,point):
    """Write canonical pixel coordinates back to normalized JSON coordinates."""
    p['keypoints'][name]['xy']=(np.asarray(point)/[WIDTH,HEIGHT]).tolist()

def points(p,component):
    """Read anchors in the component's documented curve order, never dict order."""
    return np.array([xy(p,n) for n in topology()['components'][component]['anchors']])

def landmark_arrays(p,pixels=False):
    """Return (xy[101,2], visibility[101]) in fixed landmark-ID order.

    Visibility codes: absent=0, occluded=1, visible=2. Latent xy values are kept
    for all three states. Pixel output uses the serialized canvas resolution;
    these are actual SVG/PNG coordinates because preserveAspectRatio is none.
    This is data inspection/export, not a detector or training implementation.
    """
    validate_pose(p);definitions=sorted(topology()['keypoints'],key=lambda k:k['id'])
    coords=np.array([p['keypoints'][k['name']]['xy'] for k in definitions],dtype=float)
    states={'absent':0,'occluded':1,'visible':2}
    visibility=np.array([states[p['keypoints'][k['name']]['state']] for k in definitions],dtype=np.uint8)
    if pixels:coords*=np.array([p['canvas']['width'],p['canvas']['height']])
    return coords,visibility

def validate_pose(p):
    if p.get('schema_version')!=SCHEMA or p.get('topology_id')!=TOPOLOGY:raise ValueError('Unsupported schema/topology')
    if p.get('coordinate_system')!='normalized':raise ValueError('Expected normalized xy')
    if p.get('style')!={'background':'white','ink':'black'}:raise ValueError('Phase 1 uses white background and black ink')
    t=topology();expected={k['name']:k['id'] for k in t['keypoints']}
    if set(p['keypoints'])!=set(expected):raise ValueError('Landmark names must exactly match the fixed topology')
    for name,k in p['keypoints'].items():
        if k.get('id')!=expected[name]:raise ValueError(f'Wrong landmark ID: {name}')
        if k.get('state') not in ('visible','occluded','absent'):raise ValueError(f'Invalid landmark state: {name}')
        a=k.get('xy',[])
        if len(a)!=2 or not all(isinstance(x,(int,float)) and math.isfinite(x) and 0<=x<=1 for x in a):raise ValueError(f'Invalid normalized xy: {name}')
    def finite(v):
        if isinstance(v,dict):return all(finite(x) for x in v.values())
        if isinstance(v,list):return all(finite(x) for x in v)
        return not isinstance(v,(float,int)) or math.isfinite(v)
    if not finite(p):raise ValueError('Nonfinite pose value')
    if 'geometry' in p:
        g=p['geometry']
        if not isinstance(g,dict) or g.get('version')!='smooth_v1':raise ValueError('Unsupported geometry mode')
        for field in ('ribbon_smoothing','mouth_rounding'):
            if not isinstance(g.get(field),(int,float)) or not 0<=g[field]<=1:raise ValueError(f'Invalid geometry {field}')
        if 'under_eye_transition' in g and g['under_eye_transition']!='stroke_bank_v1':raise ValueError('Unknown under-eye transition mode')
    emotion=p.get('emotion')
    if isinstance(emotion,dict) and emotion.get('taxonomy_id')=='emonet_face_40_v1':
        weights=emotion.get('weights',[])
        if not isinstance(weights,list) or len(weights)!=40 or any(not isinstance(w,(int,float)) or isinstance(w,bool) or not 0<=w<=1 for w in weights):
            raise ValueError('EmoNet weights must contain forty finite control values in [0,1]')
        if sum(weights)>1+1e-9:raise ValueError('EmoNet control weights must sum to at most one')
        category=emotion.get('category_id')
        if category is not None and (not isinstance(category,int) or isinstance(category,bool) or not 1<=category<=40):
            raise ValueError('EmoNet category ID must be 1..40 or null for a mixture/neutral')
    expression=p.get('expression')
    if isinstance(expression,dict) and expression.get('catalog_id')=='cartoon_social_60_v1':
        weights=expression.get('weights',[])
        if not isinstance(weights,list) or len(weights)!=60 or any(not isinstance(w,(int,float)) or isinstance(w,bool) or not 0<=w<=1 for w in weights) or sum(weights)>1+1e-9:
            raise ValueError('Social-expression weights must contain sixty values in [0,1] with total at most one')
        category=expression.get('category_id')
        if category is not None and (not isinstance(category,int) or isinstance(category,bool) or not 1<=category<=60):
            raise ValueError('Social-expression category ID must be 1..60 or null for a mixture')
    if set(p.get('rig',{}))!=set(t['components']):raise ValueError('Missing or extra rig component')
    for name,c in t['components'].items():
        r=p['rig'][name];n=len(c['anchors'])
        if c['kind']=='ribbon' and (len(r.get('widths',[]))!=n or any(w<0 or w>130 for w in r['widths'])):raise ValueError(f'Invalid widths: {name}')
        if 'tangent_scales' in r and (len(r['tangent_scales'])!=n or any(s<0.1 or s>3 for s in r['tangent_scales'])):raise ValueError(f'Invalid tangents: {name}')
        if not 0<=r.get('opacity',1)<=1:raise ValueError(f'Invalid opacity: {name}')
        if c['kind']=='ellipse':
            if any(not 0.1<=r.get(f,0)<=180 for f in ('rx','ry')):raise ValueError(f'Invalid ellipse radii: {name}')
        if c['kind']=='hatching':
            if not 0<=r.get('count',-1)<=8 or not 1<=r.get('length',0)<=160 or not 0<=r.get('width',-1)<=30:raise ValueError(f'Invalid hatching: {name}')
            offsets=r.get('offsets',[])
            if len(offsets)!=8 or any(len(v)!=3 or not .05<=v[2]<=3 for v in offsets):raise ValueError(f'Invalid hatching slots: {name}')
            if p.get('geometry',{}).get('under_eye_transition')=='stroke_bank_v1':
                weights=r.get('slot_weights',[])
                if len(weights)!=8 or any(not isinstance(v,(int,float)) or not 0<=v<=1 for v in weights) or not 0<=r.get('foldness',-1)<=1:raise ValueError(f'Invalid under-eye morph slots: {name}')
        if name.endswith('_highlight') and not name.endswith('secondary_highlight'):
            if not .1<=r.get('heart_scale',0)<=3 or not 0<=r.get('heart_opacity',-1)<=1:raise ValueError(f'Invalid heart: {name}')
        if name.endswith('_lash') and not 0<=r.get('root_t',-1)<=1:raise ValueError(f'Invalid lash root: {name}')
    upper=p['rig']['mouth_upper']
    if not 0<=upper.get('fill_opacity',-1)<=1 or len(upper.get('corner_accent',[]))!=2 or any(not 0<=v<=1 for v in upper['corner_accent']):raise ValueError('Invalid mouth visibility')
    for side in ('left','right'):
        if p['variants'][side+'_under_eye'] not in ('none','continuous','hatching','mixed'):raise ValueError('Invalid under-eye mode')
        if p['variants'][side+'_highlight'] not in ('round','heart'):raise ValueError('Invalid highlight mode')
    if p['variants']['mouth_interior'] not in ('dark','white'):raise ValueError('Invalid mouth interior')
    c=p['canvas']
    if not all(isinstance(c[x],int) and 1<=c[x]<=8192 for x in ('width','height')):raise ValueError('Canvas size outside 1..8192')
    return p

def inside_nonzero_polygon(outline,q):
    """SVG's default nonzero winding rule, including self-intersecting OOD lids.

    This is sampled curve geometry, not full rendered-pixel occlusion. An even-odd
    polygon test would incorrectly hide pupils in a twice-wound OOD opening.
    """
    a=np.asarray(outline,dtype=float);b=np.roll(a,-1,axis=0);q=np.asarray(q,dtype=float)
    cross=(b[:,0]-a[:,0])*(q[1]-a[:,1])-(q[0]-a[:,0])*(b[:,1]-a[:,1])
    up=(a[:,1]<=q[1])&(b[:,1]>q[1])&(cross>0)
    down=(a[:,1]>q[1])&(b[:,1]<=q[1])&(cross<0)
    boundary=(np.abs(cross)<1e-7)&(np.sum((q-a)*(q-b),axis=1)<=1e-7)
    return bool(np.any(boundary) or np.count_nonzero(up)!=np.count_nonzero(down))

def refresh_states(p):
    t=topology()
    for k in t['keypoints']:
        opacity=p['rig'][k['component']].get('opacity',1)
        if k['component'].endswith('_hatching') and p['rig'][k['component']]['count']<=.01:opacity=0
        if k['component']=='tongue_crease':opacity*=p['rig']['tongue']['opacity']
        p['keypoints'][k['name']]['state']='visible' if opacity>0.01 else 'absent'
    for side in ('left','right'):
        from .geometry import cubic_segments,sample_cubics
        u=points(p,side+'_eye_upper');l=points(p,side+'_eye_lower')
        outline=np.concatenate([sample_cubics(cubic_segments(u,p['rig'][side+'_eye_upper']['tangent_scales']),32)[0],
          sample_cubics(cubic_segments(l[::-1],p['rig'][side+'_eye_lower']['tangent_scales'][::-1]),32)[0]]).astype('float32')
        pupil=p['rig'][side+'_pupil'];center=xy(p,side+'_pupil_center');angle=np.deg2rad(pupil['angle'])
        rotation=np.array([[np.cos(angle),np.sin(angle)],[-np.sin(angle),np.cos(angle)]])
        for suffix in ('pupil_center','highlight_center','secondary_highlight_center'):
            landmark=p['keypoints'][side+'_'+suffix]
            if landmark['state']=='absent':continue
            q=xy(p,side+'_'+suffix)
            hidden=pupil.get('openness',1)<.08 or not inside_nonzero_polygon(outline,q)
            if suffix!='pupil_center':
                local=rotation@(q-center);hidden |= (local[0]/pupil['rx'])**2+(local[1]/pupil['ry'])**2>1
            if hidden:landmark['state']='occluded'
    return p
