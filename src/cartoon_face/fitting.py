"""Hierarchical reconstruction from a shared rig, using bidirectional contour fitting.
Raster contours are temporary observations, NEVER pose data or renderer assets.
"""
from pathlib import Path
import copy,json,time
import numpy as np
import cv2
from scipy.spatial import cKDTree
from scipy.optimize import least_squares
from .model import points,xy,set_xy,topology,refresh_states,save_pose
from .geometry import outline_cubics,sample_cubics,cubic_segments
from .seeds import seed_pose,DATA
from .reference import ROOT,preprocess


def boundary(mask):
    cs,_=cv2.findContours(mask.astype('uint8'),cv2.RETR_LIST,cv2.CHAIN_APPROX_NONE)
    if not cs:return np.empty((0,2))
    return np.concatenate([c[:,0,:] for c in cs]).astype(float)


def fit_ribbon(p,name,target,max_nfev=100):
    r=p['rig'][name];a=points(p,name);w=np.array(r['widths']);s=np.array(r['tangent_scales']);n=len(a)
    # At most 8 anatomical anchors per fit; C1 handles remain bounded.
    x0=np.concatenate([a.ravel(),w,s]);q=boundary(target)
    if len(q)<8:return {'skipped':'empty observation'}
    q=q[np.linspace(0,len(q)-1,min(len(q),1600),dtype=int)];tree=cKDTree(q)
    def curve(x):return sample_cubics(outline_cubics(x[:n*2].reshape(n,2),x[n*2:n*3],x[n*3:]),samples=8)[0]
    def residual(x):
        g=curve(x);_,ix=tree.query(g);_,jx=cKDTree(g).query(q)
        # Match both sides, plus compact geometry and a stable width/tangent prior.
        return np.concatenate([(g-q[ix]).ravel(),(q-g[jx]).ravel(),.025*(x[:n*2]-x0[:n*2]),.08*(x[n*2:n*3]-w),.7*(x[n*3:]-1)])
    lo=np.concatenate([(a-35).ravel(),np.zeros(n),np.full(n,.3)]);hi=np.concatenate([(a+35).ravel(),np.full(n,125),np.full(n,2.4)])
    res=least_squares(residual,x0,bounds=(lo,hi),max_nfev=max_nfev,diff_step=.00008,ftol=1e-5,xtol=1e-5,gtol=1e-4,loss='soft_l1',f_scale=2)
    for key,pt in zip(topology()['components'][name]['anchors'],res.x[:n*2].reshape(n,2)):set_xy(p,key,pt)
    r['widths']=res.x[n*2:n*3].tolist();r['tangent_scales']=res.x[n*3:].tolist()
    return {'initial_contour_rmse':float(np.sqrt(np.mean(residual(x0)**2))),'final_contour_rmse':float(np.sqrt(np.mean(residual(res.x)**2))),'evaluations':res.nfev,'converged':bool(res.success)}


def component_observation(mask,p,name):
    n,labels,stats,cents=cv2.connectedComponentsWithStats(mask.astype('uint8'))
    pts=points(p,name);center=pts.mean(axis=0)
    choices=[]
    for i in range(1,n):
        if stats[i,4]<20:continue
        q=boundary(labels==i)
        score=cKDTree(q).query(pts)[0].mean()
        choices.append((score,i))
    if not choices:return np.zeros_like(mask)
    return labels==min(choices)[1]


def fit_one(name,max_nfev=100):
    p=seed_pose(name);ref=cv2.imread(str(ROOT/f'output/references/{name}.png'),cv2.IMREAD_GRAYSCALE);mask=ref<128
    history={'pose':name,'method':'bounded bidirectional contour least squares','stages':[]};start=time.time()
    # A: exact shared crop is the global initialization; no arbitrary normalization per pose.
    # B/C: optimize separate large forms, then thinner independent detail contours.
    for suffix in ('brow','moustache','lid_accent_inner','lid_accent_outer','brow_accent','under_eye'):
        for side in ('left','right'):
            c=side+'_'+suffix
            if p['rig'][c]['opacity']<.01:continue
            obs=component_observation(mask,p,c)
            h=fit_ribbon(p,c,obs,max_nfev);history['stages'].append({'component':c,**h})
    h=fit_ribbon(p,'nose',component_observation(mask,p,'nose'),max_nfev);history['stages'].append({'component':'nose',**h})
    for side in ('left','right'):
        history['stages'].append({'component':side+'_eye','raster_stages':fit_eye(p,side,mask,ref,min(max_nfev,45))})
    for side in ('left','right'):fit_hatching(p,side,mask)
    history['stages'].append({'component':'mouth','raster_fit':fit_mouth(p,mask,ref,min(max_nfev,65))})
    for c,spec in topology()['components'].items():
        if spec['kind']!='ribbon' or c in ('mouth_upper','mouth_lower') or '_eye_' in c or p['rig'][c]['opacity']<.01:continue
        history['stages'].append({'component':c,'final_raster_refinement':refine_ribbon_raster(p,c,component_observation(mask,p,c),ref,min(max_nfev,40))})
    refresh_states(p);history['seconds']=time.time()-start
    out=ROOT/'output/fitting';out.mkdir(exist_ok=True);(out/f'{name}.json').write_text(json.dumps(history,indent=2))
    save_pose(p,ROOT/f'poses/{name}.json');return history


def fit_references(max_nfev=100,workers=2):
    preprocess()
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(fit_one,n,max_nfev) for n in DATA]
        for f in futures:
            r=f.result();print(r['pose'],round(r['seconds'],1),'s',flush=True)


def fit_eye(p,side,mask,gray,max_nfev=40):
    """A regional raster fit, using the exact same CairoSVG component as final output."""
    from .renderer import shape_xml
    from .components import render_eye,ellipse,eye_opening
    from PIL import Image
    import cairosvg,io
    obs=component_observation(mask,p,side+'_eye_upper')
    yy,xx=np.where(obs);x0=max(0,int(xx.min())-18);y0=max(0,int(yy.min())-18);x1=int(xx.max())+19;y1=int(yy.max())+19
    width=x1-x0;height=y1-y0;rw=round(width*.55);rh=round(height*.55)
    region=cv2.dilate(obs.astype('uint8'),np.ones((3,3),np.uint8))>0
    target=np.where(region,gray,255)[y0:y1,x0:x1]
    target=cv2.resize(target,(rw,rh),interpolation=cv2.INTER_AREA)/255.
    def image_pose():
        opening=eye_opening(p,side);ep=ellipse(p,side+'_pupil');ep['id']='clip_ellipse';ep['opacity']=1
        defs=f'<defs><clipPath id="{side}_eye_clip"><path d="{opening}"/></clipPath><clipPath id="{side}_pupil_clip">{shape_xml(ep)}</clipPath></defs>'
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{rw}" height="{rh}" viewBox="{x0} {y0} {width} {height}">{defs}<rect x="{x0}" y="{y0}" width="{width}" height="{height}" fill="white"/>'+''.join(shape_xml(s) for s in render_eye(p,side))+'</svg>'
        data=cairosvg.svg2png(bytestring=svg.encode());a=np.asarray(Image.open(io.BytesIO(data)).convert('L'))/255.
        return a
    history=[]
    for stage in ('pupil','curves','pupil'):
        refs=[]
        def key(name,axis,scale=10):refs.append(('key',name,axis,scale))
        def rig(component,field,index=None,scale=5):refs.append(('rig',component,field,index,scale))
        if stage=='pupil':
            for suffix in ('pupil_center','highlight_center','secondary_highlight_center'):
                if suffix.startswith('secondary') and p['rig'][side+'_secondary_highlight']['opacity']==0:continue
                for axis in (0,1):key(side+'_'+suffix,axis,6)
            for suffix in ('pupil','highlight','secondary_highlight'):
                if suffix=='secondary_highlight' and p['rig'][side+'_secondary_highlight']['opacity']==0:continue
                for f in ('rx','ry'):rig(side+'_'+suffix,f,scale=5)
            rig(side+'_pupil','angle',scale=8)
            if p['rig'][side+'_highlight']['heart_opacity']>0:
                for i in (0,1):rig(side+'_highlight','heart_offset',i,scale=8)
                rig(side+'_highlight','heart_scale',scale=.2);rig(side+'_highlight','heart_angle',scale=10)
        else:
            for suffix in ('eye_upper','eye_lower'):
                c=side+'_'+suffix
                for name in topology()['components'][c]['anchors']:
                    for axis in (0,1):key(name,axis,8)
                for i in range(len(p['rig'][c]['widths'])):rig(c,'widths',i,scale=5)
            for axis in (0,1):key(side+'_eye_lash_tip',axis,8)
            rig(side+'_lash','width',scale=7);rig(side+'_lash','bend',scale=7)
            if p['rig'][side+'_eye_side']['opacity']:
                for axis in (0,1):key(side+'_eye_side_end',axis,8)
                rig(side+'_eye_side','width',scale=5);rig(side+'_eye_side','bulge',scale=7)
        base=[]
        for ref in refs:
            if ref[0]=='key':base.append(xy(p,ref[1])[ref[2]])
            else:
                v=p['rig'][ref[1]][ref[2]];base.append(v if ref[3] is None else v[ref[3]])
        base=np.array(base,float);scales=np.array([ref[-1] for ref in refs]);lo=np.full(len(refs),-2.);hi=np.full(len(refs),4.)
        for i,ref in enumerate(refs):
            if ref[0]=='rig' and ref[2] in ('rx','ry','width','widths','heart_scale'):lo[i]=max(lo[i],1+(.15-base[i])/scales[i])
        def apply(z):
            from .model import xy
            v=base+(z-1)*scales
            for ref,val in zip(refs,v):
                if ref[0]=='key':q=xy(p,ref[1]);q[ref[2]]=val;set_xy(p,ref[1],q)
                elif ref[3] is None:p['rig'][ref[1]][ref[2]]=float(val)
                else:p['rig'][ref[1]][ref[2]][ref[3]]=float(val)
        target_blur=cv2.GaussianBlur(target,(0,0),.8 if stage=='curves' else .6)
        def residual(z):
            apply(z);a=cv2.GaussianBlur(image_pose(),(0,0),.8 if stage=='curves' else .6)
            return np.concatenate([(a-target_blur).ravel(),.035*(z-1)])
        initial=np.mean(residual(np.ones(len(refs)))**2)
        res=least_squares(residual,np.ones(len(refs)),bounds=(lo,hi),max_nfev=max_nfev,diff_step=.015,ftol=1e-4,xtol=1e-4,gtol=1e-5,tr_solver='lsmr')
        apply(res.x);final=float(np.mean(residual(res.x)**2));history.append({'stage':stage,'initial_loss':float(initial),'final_loss':final,'evaluations':res.nfev})
    return history


def fit_hatching(p,side,mask):
    """Recover the parametric lane + short strokes, without new landmark IDs."""
    r=p['rig'][side+'_hatching']
    if r['opacity']==0:return
    n,labels,stats,cents=cv2.connectedComponentsWithStats(mask.astype('uint8'))
    a,b=points(p,side+'_hatching');v=b-a;ll=v@v
    found=[]
    for i in range(1,n):
        x,y,w,h,area=stats[i];c=cents[i];t=np.clip((c-a)@v/max(ll,1),0,1)
        if 35<area<600 and 12<h<85 and 8<w<85 and np.linalg.norm(c-(a+t*v))<35:
            found.append((c,i))
    found.sort(key=lambda z:z[0][0],reverse=side=='right')
    if not 2<=len(found)<=8:return
    r['count']=len(found);a=found[0][0];b=found[-1][0]
    for name,q in zip(topology()['components'][side+'_hatching']['anchors'],[a,b]):set_xy(p,name,q)
    lengths=[];angles=[];widths=[];centers=[]
    for c,i in found:
        yy,xx=np.where(labels==i);q=np.column_stack([xx,yy]);cov=np.cov(q.T);eig,vec=np.linalg.eigh(cov);axis=vec[:,-1]
        if axis[1]>0:axis=-axis
        angles.append(np.rad2deg(np.arctan2(axis[1],axis[0])));u=(q-c)@axis;lengths.append(float(u.max()-u.min()+1));widths.append(float(stats[i,4]/max(lengths[-1],1)*2));centers.append(c)
    r['angle']=float(np.mean(angles));r['length']=float(np.mean(lengths));r['width']=float(np.mean(widths))
    r['offsets']=[[0,0,1] for _ in range(8)]
    for i,t in enumerate(np.linspace(0,1,len(found))):
        d=centers[i]-((1-t)*a+t*b);r['offsets'][i]=[float(d[0]),float(d[1]),lengths[i]/r['length']]


def fit_mouth(p,mask,gray,max_nfev=60):
    from .components import render_mouth
    from .renderer import shape_xml
    from .model import xy
    import cairosvg,io
    from PIL import Image
    obs=component_observation(mask,p,'mouth_upper')
    if p['rig']['chin']['opacity']>0:obs |= component_observation(mask,p,'chin')
    yy,xx=np.where(obs);x0=int(xx.min())-14;y0=int(yy.min())-14;x1=int(xx.max())+15;y1=min(gray.shape[0],int(yy.max())+15)
    width=x1-x0;height=y1-y0;rw=round(width*.8);rh=round(height*.8)
    region=cv2.dilate(obs.astype('uint8'),np.ones((3,3),np.uint8))>0
    target=cv2.resize(np.where(region,gray,255)[y0:y1,x0:x1],(rw,rh),interpolation=cv2.INTER_AREA)/255.
    refs=[]
    for c in ('mouth_upper','mouth_lower','tongue','tongue_crease','chin'):
        if p['rig'][c]['opacity']<.01:continue
        for name in topology()['components'][c]['anchors']:
            for axis in (0,1):refs.append(('key',name,axis,None,8))
        for i in range(len(p['rig'][c].get('widths',[]))):refs.append(('rig',c,'widths',i,5))
        if c=='tongue':
            refs.append(('rig',c,'width',None,4))
            for i in range(6):refs.append(('rig',c,'tangent_scales',i,.25))
    base=[]
    for typ,c,field,index,scale in refs:
        if typ=='key':base.append(xy(p,c)[field])
        else:base.append(p['rig'][c][field] if index is None else p['rig'][c][field][index])
    base=np.array(base);scales=np.array([r[-1] for r in refs]);lo=np.full(len(refs),-3.);hi=np.full(len(refs),5.)
    for i,(typ,c,field,index,scale) in enumerate(refs):
        if typ=='rig':lo[i]=max(lo[i],1+(.1-base[i])/scale)
        if typ=='rig' and field=='tangent_scales':
            lo[i]=max(lo[i],1+(.3-base[i])/scale);hi[i]=min(hi[i],1+(2.4-base[i])/scale)
        if typ=='key' and field==1:hi[i]=min(hi[i],1+(749-base[i])/scale)
    def apply(z):
        for ref,value in zip(refs,base+(z-1)*scales):
            typ,c,field,index,_=ref
            if typ=='key':q=xy(p,c);q[field]=value;set_xy(p,c,q)
            elif index is None:p['rig'][c][field]=float(value)
            else:p['rig'][c][field][index]=float(value)
    def residual(z):
        apply(z)
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{rw}" height="{rh}" viewBox="{x0} {y0} {width} {height}"><rect x="{x0}" y="{y0}" width="{width}" height="{height}" fill="white"/>'+''.join(shape_xml(s) for s in render_mouth(p))+'</svg>'
        a=np.asarray(Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))).convert('L'))/255.
        return np.concatenate([(cv2.GaussianBlur(a,(0,0),.6)-cv2.GaussianBlur(target,(0,0),.6)).ravel(),.022*(z-1)])
    initial=float(np.mean(residual(np.ones(len(refs)))**2))
    res=least_squares(residual,np.ones(len(refs)),bounds=(lo,hi),max_nfev=max_nfev,diff_step=.015,ftol=1e-5,xtol=1e-4,gtol=1e-5,tr_solver='lsmr')
    apply(res.x);return {'initial_loss':initial,'final_loss':float(np.mean(residual(res.x)**2)),'evaluations':res.nfev}


def refine_ribbon_raster(p,name,obs,gray,max_nfev=40):
    """Final local mask refinement with real SVG pixels, holding semantic ordering fixed."""
    from .components import ribbon
    from .renderer import shape_xml
    from .model import xy
    from PIL import Image
    import cairosvg,io
    yy,xx=np.where(obs)
    x0=int(xx.min())-8;y0=int(yy.min())-8;x1=int(xx.max())+9;y1=int(yy.max())+9
    width=x1-x0;height=y1-y0;rw=max(12,round(width*.85));rh=max(12,round(height*.85))
    region=cv2.dilate(obs.astype('uint8'),np.ones((3,3),np.uint8))>0
    target=cv2.resize(np.where(region,gray,255)[y0:y1,x0:x1],(rw,rh),interpolation=cv2.INTER_AREA)/255.
    target_blur=cv2.GaussianBlur(target,(0,0),.5)
    r=p['rig'][name];anchors=topology()['components'][name]['anchors'];n=len(anchors)
    a=points(p,name);w=np.array(r['widths']);ts=np.array(r['tangent_scales']);base=np.r_[a.ravel(),w,ts];scale=np.r_[np.full(n*3,4),np.full(n,.15)]
    lo=np.full(len(base),-2.);hi=np.full(len(base),4.)
    lo[n*2:n*3]=np.maximum(lo[n*2:n*3],1-w/4);hi[n*2:n*3]=np.minimum(hi[n*2:n*3],1+(125-w)/4)
    lo[n*3:]=np.maximum(lo[n*3:],1+(.3-ts)/.15);hi[n*3:]=np.minimum(hi[n*3:],1+(2.4-ts)/.15)
    def apply(z):
        x=base+(z-1)*scale
        for key,q in zip(anchors,x[:n*2].reshape(n,2)):set_xy(p,key,q)
        r['widths']=x[n*2:n*3].tolist();r['tangent_scales']=x[n*3:].tolist()
    def render():
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{rw}" height="{rh}" viewBox="{x0} {y0} {width} {height}"><rect x="{x0}" y="{y0}" width="{width}" height="{height}" fill="white"/>'+shape_xml(ribbon(p,name))+'</svg>'
        return np.asarray(Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode()))).convert('L'))/255.
    def residual(z):
        apply(z);im=render()
        return np.r_[(cv2.GaussianBlur(im,(0,0),.5)-target_blur).ravel(),.012*(z-1),.022*(np.array(r['tangent_scales'])-1)]
    initial=float(np.mean(residual(np.ones(len(base)))**2));old=render()
    res=least_squares(residual,np.ones(len(base)),bounds=(lo,hi),max_nfev=max_nfev,diff_step=.03,ftol=1e-5,xtol=1e-4,gtol=1e-5,tr_solver='lsmr')
    apply(res.x);new=render()
    def dice(im):
        a=target<.5;b=im<.5;return float(2*np.sum(a&b)/max(np.sum(a)+np.sum(b),1))
    accepted=dice(new)>=dice(old)-.002
    final=float(np.mean(residual(res.x)**2))
    if not accepted:apply(np.ones(len(base)))
    return {'initial_loss':initial,'final_loss':final,'initial_dice':dice(old),'final_dice':dice(new),'accepted':accepted,'evaluations':res.nfev}


def refine_saved(name):
    from .model import load_pose
    p=load_pose(ROOT/f'poses/{name}.json');gray=cv2.imread(str(ROOT/f'output/references/{name}.png'),0);mask=gray<128;history=[]
    for c,spec in topology()['components'].items():
        if spec['kind']!='ribbon' or c in ('mouth_upper','mouth_lower') or '_eye_' in c or p['rig'][c]['opacity']<.01:continue
        obs=component_observation(mask,p,c);history.append({'component':c,**refine_ribbon_raster(p,c,obs,gray)})
    save_pose(p,ROOT/f'poses/{name}.json');out=ROOT/'output/fitting';(out/f'{name}_raster_refinement.json').write_text(json.dumps(history,indent=2));return name
