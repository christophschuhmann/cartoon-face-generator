"""On-demand raster augmentation with the SAME transform for all 101 labels.

The output annotation is a raster observation, not a renderable pose. Keep its
source SVG/pose: image degradation cannot be inverted into an SVG rig. Geometry
is recorded explicitly; photometric randomness has its own reproducible seed.
"""
from pathlib import Path
import io,json
import cv2
import numpy as np
from PIL import Image,ImageDraw
from .model import topology,landmark_arrays
from .renderer import rasterize,render_svg

AUGMENTATION_VERSION='face_raster_aug_v2'


def flip_permutation():
    """Reinterpret a mirrored character with the original anatomical convention.

    Bilateral anatomical names swap IDs; central curve roles keep their IDs.
    This permutation is also applied to presence/occlusion, not just xy.
    """
    names=[k['name'] for k in topology()['keypoints']];lookup={n:i for i,n in enumerate(names)}
    def mirror(name):
        if name.startswith('left_'):return 'right_'+name[5:]
        if name.startswith('right_'):return 'left_'+name[6:]
        return name.replace('_left','_right') if '_left' in name else name.replace('_right','_left')
    return np.array([lookup[mirror(n)] for n in names],dtype=int)


def sample_transform(source_size,target_size,seed=42,augment=True):
    """Letterbox first, then mild affine/flip and invertible two-stage sine shear."""
    sw,sh=source_size;w,h=target_size
    if not all(isinstance(v,int) and 8<=v<=8192 for v in (sw,sh,w,h)):raise ValueError('Raster dimensions must be integers in [8,8192]')
    if not isinstance(seed,int) or seed<0:raise ValueError('Augmentation seed must be a nonnegative integer')
    rng=np.random.default_rng(seed);fit=min(w/sw,h/sh);padding_y=(h-fit*sh)/2
    if augment:
        fit=min(w*rng.uniform(.93,1)/sw,h*rng.uniform(.82,1)/sh)
        # Extra lower margin varies without squashing the face. Coordinates use
        # this exact letterbox placement, rather than assuming centered padding.
        padding_y=rng.uniform(.15,.50)*max(0,h-fit*sh)
    letter=np.array([[fit,0,(w-fit*sw)/2],[0,fit,padding_y],[0,0,1.]])
    affine=np.eye(3);flip=False;elastic={'ax':0.,'ay':0.,'phase_x':0.,'phase_y':0.}
    appearance={'background':[255.]*3,'ink':[0.]*3,'gradient_x':0.,'gradient_y':0.,'noise_sigma':0.,
      'noise_seed':int(seed),'blur_sigma':0.,'low_resolution_scale':1.,'jpeg_quality':None}
    occluders=[]
    if augment:
        theta=np.deg2rad(rng.uniform(-12,12));scale=rng.uniform(.86,1.10);sx,sy=scale*rng.uniform(.90,1.10,2)
        linear=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])@np.diag([sx,sy])
        center=np.array([w/2,h/2]);translation=rng.uniform([-w*.06,-h*.06],[w*.06,h*.06])
        affine[:2,:2]=linear;affine[:2,2]=center-linear@center+translation
        flip=bool(rng.random()<.35)
        if flip:affine=np.array([[-1.,0,w-1],[0,1.,0],[0,0,1.]])@affine
        if rng.random()<.55:
            elastic={'ax':float(rng.uniform(-.018,.018)*w),'ay':float(rng.uniform(-.025,.025)*h),
              'phase_x':float(rng.uniform(0,2*np.pi)),'phase_y':float(rng.uniform(0,2*np.pi))}
        palettes=np.array([[250,239,204],[205,227,252],[240,213,226],[223,243,218],[241,241,241]])
        background=palettes[int(rng.integers(0,len(palettes)))]+rng.uniform(-12,10,3)
        if rng.random()<.25:background=rng.uniform(190,255,3)
        ink=rng.uniform(0,45,3)
        if rng.random()<.10:ink,background=background,ink
        appearance={'background':background.tolist(),'ink':ink.tolist(),'gradient_x':float(rng.uniform(-12,12)),'gradient_y':float(rng.uniform(-12,12)),
          'noise_sigma':float(rng.uniform(.4,6.5)),'noise_seed':int(rng.integers(0,2**32)),
          'blur_sigma':float(rng.uniform(.15,.75)) if rng.random()<.35 else 0.,
          'low_resolution_scale':float(rng.uniform(.48,1)) if rng.random()<.25 else 1.,
          'jpeg_quality':int(rng.integers(50,98)) if rng.random()<.55 else None}
        if rng.random()<.15:
            pw,ph=int(rng.uniform(.05,.12)*w),int(rng.uniform(.06,.16)*h)
            x=int(rng.uniform(.15*w,max(.15*w+1,.85*w-pw)));y=int(rng.uniform(.2*h,max(.2*h+1,.8*h-ph)))
            occluders.append([x,y,x+pw,y+ph])
    return {'version':AUGMENTATION_VERSION,'seed':seed,'augmented':augment,'source_size':[sw,sh],'target_size':[w,h],
      'affine':(affine@letter)[:2].tolist(),'horizontal_flip':flip,
      'label_permutation':flip_permutation().tolist() if flip else list(range(101)),
      'elastic':elastic,'occluders':occluders,'appearance':appearance}


def transform_coordinates(coords,descriptor):
    """Forward transform in continuous pixel units; never clamp outside points.

    OpenCV integer pixel centers define the flip x' = W - 1 - x. Normalization
    divides by W/H, as does the pose contract; the convention is explicit here.
    """
    matrix=np.asarray(descriptor['affine']);q=np.asarray(coords)@matrix[:,:2].T+matrix[:,2]
    w,h=descriptor['target_size'];e=descriptor['elastic'];q=q.copy()
    q[:,0]+=e['ax']*np.sin(2*np.pi*q[:,1]/h+e['phase_x'])
    q[:,1]+=e['ay']*np.sin(2*np.pi*q[:,0]/w+e['phase_y'])
    return q[np.array(descriptor['label_permutation'])]


def inverse_elastic(coords,descriptor):
    """Exact inverse of the triangular shear, matching cv2.remap's sampling map."""
    q=np.asarray(coords).copy();w,h=descriptor['target_size'];e=descriptor['elastic']
    q[...,1]-=e['ay']*np.sin(2*np.pi*q[...,0]/w+e['phase_y'])
    q[...,0]-=e['ax']*np.sin(2*np.pi*q[...,1]/h+e['phase_x'])
    return q


def transform_image(image,descriptor):
    w,h=descriptor['target_size'];grey=np.asarray(image.convert('L'))
    grey=cv2.warpAffine(grey,np.array(descriptor['affine']),(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=255)
    e=descriptor['elastic']
    if e['ax'] or e['ay']:
        yy,xx=np.mgrid[:h,:w];mapping=inverse_elastic(np.stack([xx,yy],axis=-1).astype(float),descriptor)
        grey=cv2.remap(grey,mapping[...,0].astype('float32'),mapping[...,1].astype('float32'),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=255)
    for x0,y0,x1,y1 in descriptor['occluders']:grey[y0:y1,x0:x1]=255
    a=descriptor['appearance'];small=a['low_resolution_scale']
    if small<1:grey=cv2.resize(cv2.resize(grey,(max(8,round(w*small)),max(8,round(h*small))),interpolation=cv2.INTER_AREA),(w,h),interpolation=cv2.INTER_LINEAR)
    if a['blur_sigma']>0:grey=cv2.GaussianBlur(grey,(0,0),a['blur_sigma'])
    background=np.array(a['background']);ink=np.array(a['ink'])
    rgb=grey.astype(float)[...,None]/255*(background-ink)+ink
    rgb+=(np.linspace(-.5,.5,w)[None,:]*a['gradient_x']+np.linspace(-.5,.5,h)[:,None]*a['gradient_y'])[...,None]
    if a['noise_sigma']>0:rgb+=np.random.default_rng(a['noise_seed']).normal(0,a['noise_sigma'],rgb.shape)
    result=Image.fromarray(np.clip(np.rint(rgb),0,255).astype('uint8'))
    if a['jpeg_quality'] is not None:
        buf=io.BytesIO();result.save(buf,format='JPEG',quality=a['jpeg_quality']);buf.seek(0);result=Image.open(buf).copy()
    return result.convert('RGB')


def annotation_for_pose(p,descriptor,sample_id=None):
    coords,visibility=landmark_arrays(p,pixels=True);q=transform_coordinates(coords,descriptor)
    visibility=visibility[np.array(descriptor['label_permutation'])];source_visibility=visibility.copy()
    w,h=descriptor['target_size'];in_frame=(q[:,0]>=0)&(q[:,0]<w)&(q[:,1]>=0)&(q[:,1]<h)
    occluded=np.zeros(101,dtype=bool)
    for x0,y0,x1,y1 in descriptor['occluders']:occluded |= (q[:,0]>=x0)&(q[:,0]<x1)&(q[:,1]>=y0)&(q[:,1]<y1)
    visibility[(visibility>0)&occluded]=1;visibility[~in_frame]=0
    return {'schema_version':'raster_landmarks_v1','topology_id':p['topology_id'],'sample_id':sample_id or p.get('name'),
      'canvas':{'width':w,'height':h},'keypoint_ids':list(range(101)),
      'keypoint_names':[k['name'] for k in topology()['keypoints']],
      'xy_pixels':q.tolist(),'xy_normalized':(q/[w,h]).tolist(),'visibility':visibility.tolist(),
      'source_visibility':source_visibility.tolist(),'in_frame':in_frame.tolist(),'synthetic_occlusion':occluded.tolist(),
      'regression_mask':((source_visibility>0)&in_frame).tolist(),'visible_mask':((visibility==2)&in_frame).tolist(),
      'ood':p.get('dataset',{}).get('ood',False),'target':p.get('dataset',{}).get('target'),
      'emotion':p.get('emotion'),'expression':p.get('expression'),'transform':descriptor,
      'visibility_note':'Presence/lid clipping from source; synthetic occlusion and out-of-frame masks added; no full pixel-overlap segmentation'}


def augment_raster(p,seed=42,width=768,height=400,augment=True,svg=None):
    descriptor=sample_transform((p['canvas']['width'],p['canvas']['height']),(width,height),seed,augment)
    image=rasterize(svg or render_svg(p),*descriptor['source_size'])
    return transform_image(image,descriptor),annotation_for_pose(p,descriptor)


def draw_annotation(image,annotation):
    image=image.copy();draw=ImageDraw.Draw(image)
    for q,v,frame in zip(annotation['xy_pixels'],annotation['visibility'],annotation['in_frame']):
        if frame and v:draw.ellipse((q[0]-2,q[1]-2,q[0]+2,q[1]+2),fill='#2877da' if v==2 else '#c6468b')
    return image


def augmented_records(path,split='train',seed=42,width=768,height=400,augment=True):
    """Lazy iterator: SVG -> raster -> annotation. It does not save PNGs."""
    from .large_dataset import iter_records
    # Source seeds are unique per record and independent of iteration/worker order.
    for key,svg,p in iter_records(path,split):
        sample_seed=seed+p.get('dataset',{}).get('source_seed',0)+int(p.get('dataset',{}).get('ood',False))*500000000
        im,ann=augment_raster(p,sample_seed,width,height,augment,svg);ann['sample_id']=key
        yield key,im,ann


def export_rasters(path,out,split='train',limit=100,seed=42,width=768,height=400,augment=True,format='png'):
    """Export a requested subset plus JSONL and COCO-compatible 101-point labels."""
    if limit<1 or format not in ('png','jpg'):raise ValueError('Use positive limit and png or jpg')
    out=Path(out);(out/'images').mkdir(parents=True,exist_ok=True)
    names=[k['name'] for k in topology()['keypoints']];coco={'info':{'description':'Synthetic cartoon landmarks; intended expression labels are not human-validated'},
      'images':[],'annotations':[],'categories':[{'id':1,'name':'cartoon_face','keypoints':names,'skeleton':[]}]}
    count=0
    with (out/'annotations.jsonl').open('w') as handle:
        for i,(key,image,ann) in enumerate(augmented_records(path,split,seed,width,height,augment)):
            if i>=limit:break
            filename=f'images/{key}.{format}';image.save(out/filename,**({'quality':92} if format=='jpg' else {}))
            ann['image']=filename;handle.write(json.dumps(ann,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
            coords=np.array(ann['xy_pixels']);v=np.array(ann['visibility']);valid=coords[v>0]
            if len(valid):lo=np.maximum(valid.min(axis=0)-10,0);hi=np.minimum(valid.max(axis=0)+10,[width,height])
            else:lo=np.zeros(2);hi=np.zeros(2)
            bbox=[*lo.tolist(),*(hi-lo).tolist()]
            coco['images'].append({'id':i+1,'file_name':filename,'width':width,'height':height})
            coco['annotations'].append({'id':i+1,'image_id':i+1,'category_id':1,'keypoints':np.column_stack([coords,v]).ravel().tolist(),
              'num_keypoints':int(np.count_nonzero(v)),'bbox':bbox,'area':float(np.prod(hi-lo)),'iscrowd':0,'sample_id':key})
            if i<12:
                preview=out/'annotated_preview';preview.mkdir(exist_ok=True);draw_annotation(image,ann).save(preview/(key+'.png'))
            count+=1
    (out/'coco_keypoints.json').write_text(json.dumps(coco,ensure_ascii=False,separators=(',',':'))+'\n')
    report={'count':count,'source_dataset':str(path),'split':split,'seed':seed,'canvas':[width,height],'augmented':augment,'format':format,
      'annotation_schema':'raster_landmarks_v1','topology_id':'cartoon_face_v1','bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file())}
    (out/'export_manifest.json').write_text(json.dumps(report,indent=2)+'\n');return report
