"""Sharded SVG + full-pose dataset, with deterministic nuisance and OOD variation.

Each TAR member pair is key.svg/key.json. JSON is a complete renderable pose,
not a seed-only recipe. TAR gzip shards stream without materializing 105k files.
Generation is resumable per class; every record retains all 101 fixed IDs.
"""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import copy,gzip,hashlib,io,json,os,tarfile,time
import numpy as np
from .model import WIDTH,HEIGHT,topology,points,set_xy,landmark_arrays,refresh_states,validate_pose,load_pose
from .emotion_library import catalog,emotion_pose40
from .social_expressions import social_catalog,social_pose,social_cue_checks
from .emotion_validation import cue_checks
from .renderer import render_svg,rasterize
from .reference import ROOT

DATASET_VERSION='cartoon_landmarks_105k_v2'


def generation_fingerprint():
    """Pin source, topology, recipes and fitted identity used to generate shards."""
    source=Path(__file__).parent
    files=[source/n for n in ('model.py','geometry.py','renderer.py','emotion_library.py',
      'social_expressions.py','large_dataset.py','expressions.py','under_eye.py')]
    files+=sorted((source/'components').glob('*.py'))+sorted((source/'emotions').glob('*.json'))
    files+=sorted((source/'topology').glob('*.json'))+sorted((ROOT/'poses').glob('*.json'))
    digest=hashlib.sha256()
    for path in sorted(files):digest.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def categories():
    return [{'class_index':i,'kind':'emonet','id':p['id'],'slug':p['slug'],'label':p['label_de']} for i,p in enumerate(catalog()['profiles'])]+[
      {'class_index':40+i,'kind':'social','id':p['id'],'slug':p['slug'],'label':p['label_de']} for i,p in enumerate(social_catalog()['profiles'])]


def _affine_components(p,names,matrix,center,translation=(0,0)):
    """Sample a rig deformation, with ellipse/zone geometry following its region."""
    center=np.asarray(center);translation=np.asarray(translation);scale=np.sqrt(abs(np.linalg.det(matrix)))
    angle=np.rad2deg(np.arctan2(matrix[1,0],matrix[0,0]))
    for name in names:
        for anchor,q in zip(topology()['components'][name]['anchors'],points(p,name)):
            set_xy(p,anchor,center+matrix@(q-center)+translation)
        r=p['rig'][name]
        if 'rx' in r:
            theta=np.deg2rad(r['angle']);rotation=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
            u,s,_=np.linalg.svd(matrix@rotation@np.diag([r['rx'],r['ry']]))
            r.update(rx=float(s[0]),ry=float(s[1]),angle=float(np.rad2deg(np.arctan2(u[1,0],u[0,0]))))
        if 'widths' in r:r['widths']=[float(w*scale) for w in r['widths']]
        for key in ('width','bulge','bend','corner_width','corner_size'):
            if key in r:r[key]*=float(scale)
        if 'heart_offset' in r:
            r['heart_offset']=(matrix@r['heart_offset']).tolist();r['heart_scale']*=float(scale);r['heart_angle']+=float(angle)
        if 'length' in r:
            theta=np.deg2rad(r['angle']);v=matrix@[np.cos(theta),np.sin(theta)]
            r['length']*=float(np.linalg.norm(v));r['angle']=float(np.rad2deg(np.arctan2(v[1],v[0])))
            r['offsets']=[[*map(float,matrix@slot[:2]),slot[2]] for slot in r['offsets']]


def geometric_variation(p,seed):
    """Correlated component proportions, gaze remains attached; no free XY noise.

    Source-category cues are checked before this orientation-preserving nuisance
    deformation. Everything here is then re-rendered with exact updated labels.
    """
    p=copy.deepcopy(p);rng=np.random.default_rng(seed);latents={}
    for side in ('left','right'):
        sx,sy=rng.uniform(.90,1.10,2);angle=rng.uniform(-4.5,4.5);theta=np.deg2rad(angle)
        matrix=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])@np.diag([sx,sy])
        names=[n for n in topology()['components'] if n.startswith(side+'_') and 'brow' not in n and 'moustache' not in n]
        center=(points(p,side+'_eye_upper')[2]+points(p,side+'_eye_lower')[1])/2
        _affine_components(p,names,matrix,center)
        brow=points(p,side+'_brow');_affine_components(p,[side+'_brow',side+'_brow_accent'],np.diag([rng.uniform(.96,1.04),1]),brow.mean(axis=0),[0,rng.uniform(-7,7)])
        cheek=points(p,side+'_moustache');factor=rng.uniform(.93,1.07)
        _affine_components(p,[side+'_moustache'],np.diag([factor,rng.uniform(.95,1.05)]),cheek.mean(axis=0))
        latents[side]={'eye_scale':[float(sx),float(sy)],'eye_tilt_deg':float(angle),'cheek_width_scale':float(factor)}
    mouth_scale=float(rng.uniform(.89,1.11))
    _affine_components(p,['mouth_upper','mouth_lower','tongue','tongue_crease','chin'],np.diag([mouth_scale,1]),points(p,'mouth_upper').mean(axis=0))
    global_scale=float(rng.uniform(.94,1.05));translation=rng.uniform([-22,-12],[22,12])
    _affine_components(p,list(topology()['components']),np.eye(2)*global_scale,[WIDTH/2,HEIGHT/2],translation)
    coords=landmark_arrays(p)[0] if all(0<=v<=1 for k in p['keypoints'].values() for v in k['xy']) else np.array([p['keypoints'][k['name']]['xy'] for k in topology()['keypoints']])
    span=coords.max(axis=0)-coords.min(axis=0);bounds_scale=min(1.,float(np.min(.988/np.maximum(span,1e-9))))
    if bounds_scale<1:
        _affine_components(p,list(topology()['components']),np.eye(2)*bounds_scale,[WIDTH/2,HEIGHT/2])
        coords=np.array([p['keypoints'][k['name']]['xy'] for k in topology()['keypoints']])
    correction=np.maximum(.006-coords.min(axis=0),0)-np.maximum(coords.max(axis=0)-.994,0)
    for k in p['keypoints'].values():k['xy']=(np.array(k['xy'])+correction).tolist()
    latents.update(mouth_width_scale=mouth_scale,global_scale=global_scale,bounds_fit_scale=bounds_scale,translation_px=translation.tolist(),bounds_translation_normalized=correction.tolist())
    p['recipe']['modified_after_generation']=True;p['recipe']['geometric_variation']={'version':'1.0','seed':int(seed),'latents':latents}
    refresh_states(p);validate_pose(p);return p


def extreme_jitter(p,seed,minimum=.05,maximum=.10):
    """Every XY axis independently moves 5–10% of the canvas, including latent IDs.

    If a chosen sign would leave the canvas, reverse that sign rather than clip
    to an edge. Magnitudes therefore remain exact, with no collapsed labels.
    Self intersections are intentional OOD, not curated emotions.
    """
    if not 0<minimum<=maximum<=.25:raise ValueError('OOD magnitudes must satisfy 0 < min <= max <= .25')
    p=copy.deepcopy(p);rng=np.random.default_rng(seed);old=landmark_arrays(p)[0]
    magnitude=rng.uniform(minimum,maximum,old.shape);sign=rng.choice([-1.,1.],old.shape)
    delta=magnitude*sign;outside=(old+delta<.001)|(old+delta>.999);delta[outside]*=-1
    for k,q in zip(topology()['keypoints'],old+delta):p['keypoints'][k['name']]['xy']=q.tolist()
    source=p.pop('emotion',None) or p.pop('expression',None)
    p['recipe']['modified_after_generation']=True
    p['recipe']['ood_jitter']={'version':'1.0','seed':int(seed),'min_axis_fraction':minimum,'max_axis_fraction':maximum,
       'boundary_rule':'reverse offending sign; no clipping','actual_delta':delta.tolist()}
    p['provenance']={'kind':'ood_independent_landmark_jitter','source_target':source,'semantics':'source expression is not a valid target after deformation'}
    refresh_states(p);validate_pose(p);return p


def sample_pose(category,index,master_seed=42,ood=False):
    group=category['class_index'];seed=master_seed+group*1000000+index
    p=emotion_pose40(category['slug'],seed,.95) if category['kind']=='emonet' else social_pose(category['slug'],seed,.95)
    check=cue_checks(p) if category['kind']=='emonet' else social_cue_checks(p)
    if not check['passed']:raise ValueError(f'{category["slug"]}/{index}: protected source cue lost: {check["failures"]}')
    deformation_seed=master_seed+200000000+group*1000000+index
    p=extreme_jitter(p,deformation_seed) if ood else geometric_variation(p,deformation_seed)
    return p,seed


def _split(index,count):
    return 'train' if index<int(.8*count) else 'validation' if index<int(.9*count) else 'test'


class _Archive:
    def __init__(self,path):
        self.path=path;path.parent.mkdir(parents=True,exist_ok=True);self.temp=path.with_suffix(path.suffix+'.partial')
        self.raw=self.temp.open('wb');self.gz=gzip.GzipFile(filename='',fileobj=self.raw,mode='wb',compresslevel=3,mtime=0)
        self.tar=tarfile.open(fileobj=self.gz,mode='w|',format=tarfile.USTAR_FORMAT);self.count=0;self.logical_bytes=0
    def add(self,name,data):
        info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;info.mode=0o644
        self.tar.addfile(info,io.BytesIO(data));self.logical_bytes+=len(data)
    def close(self):
        self.tar.close();self.gz.close();self.raw.close();self.temp.replace(self.path)
        digest=hashlib.sha256()
        with self.path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
        return {'file':str(self.path),'records':self.count,'bytes':self.path.stat().st_size,'logical_payload_bytes':self.logical_bytes,'sha256':digest.hexdigest()}


def _worker(task):
    category,count,seed,out,ood=task;out=Path(out);slug=category['slug'];kind=category['kind']
    stamp=f'{kind}_{category["id"]:02}_{slug}';done=out/'class_reports'/f'{stamp}.json'
    if done.exists():
        r=json.loads(done.read_text())
        if r['count']==count and r['master_seed']==seed and r['dataset_version']==DATASET_VERSION and all((out/s['file']).exists() and (out/s['file']).stat().st_size==s['bytes'] and file_hash(out/s['file'])==s['sha256'] for s in r['shards']):return r
        raise ValueError(f'Existing class output has a different generation contract: {done}')
    writers={};hashes=set();sum_xy=np.zeros((101,2));sum_sq=np.zeros((101,2));start=time.monotonic()
    for index in range(count):
        if ood:
            source=categories()[index%100];p,record_seed=sample_pose(source,index+100000,seed,True)
        else:p,record_seed=sample_pose(category,index,seed)
        split=_split(index,count);key=f'{stamp}-{index:06}'
        p['name']=key;p['canvas']={'width':768,'height':400}
        p['dataset']={'version':DATASET_VERSION,'sample_id':key,'master_seed':seed,'sample_index':index,'source_seed':record_seed,
          'split':split,'target':None if ood else category,'ood':ood,'landmark_count':101,
          'visibility_method':'component presence plus sampled nonzero pupil/lid clipping; not full overlap segmentation'}
        coords,_=landmark_arrays(p);hashes.add(hashlib.sha256(coords.tobytes()).hexdigest());sum_xy+=coords;sum_sq+=coords**2
        svg=render_svg(p).encode();pose=json.dumps(p,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        if split not in writers:writers[split]=_Archive(out/split/(stamp+'.tar.gz'))
        writer=writers[split];writer.add(key+'.svg',svg);writer.add(key+'.json',pose);writer.count+=1
        if index<4:
            dest=out/'preview'/stamp;dest.mkdir(parents=True,exist_ok=True)
            (dest/(key+'.json')).write_bytes(pose);(dest/(key+'.svg')).write_bytes(svg);rasterize(svg.decode()).save(dest/(key+'.png'))
        if (index+1)%100==0:
            progress=out/'worker_progress';progress.mkdir(exist_ok=True)
            (progress/(stamp+'.json')).write_text(json.dumps({'generated_records':index+1,'target_records':count,'seconds':time.monotonic()-start})+'\n')
    shards=[]
    for writer in writers.values():
        row=writer.close();row['file']=str(Path(row['file']).relative_to(out));shards.append(row)
    std=np.sqrt(np.maximum(sum_sq/count-(sum_xy/count)**2,0))
    report={'dataset_version':DATASET_VERSION,'category':category,'count':count,'master_seed':seed,'ood':ood,
        'unique_coordinate_hashes':len(hashes),'mean_coordinate_std_normalized':float(std.mean()),'shards':shards,
        'seconds':time.monotonic()-start,'all_records_validated':True,'source_cue_checks':'checked before geometric nuisance transform; OOD has no reliable emotion label'}
    done.parent.mkdir(exist_ok=True);temp=done.with_suffix('.partial');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');temp.replace(done)
    return report


def build_dataset(per_category=1000,ood_count=5000,seed=42,workers=16,out=None):
    if per_category<1 or ood_count<0 or seed<0 or workers<1:raise ValueError('Invalid generation counts, seed or worker count')
    out=Path(out or ROOT/'datasets/cartoon_landmarks_v2');out.mkdir(parents=True,exist_ok=True)
    plan={'dataset_version':DATASET_VERSION,'categories':categories(),'per_category':per_category,'ood_count':ood_count,'seed':seed,
        'topology_id':'cartoon_face_v1','emonet_recipe':catalog()['recipe_version'],'social_recipe':social_catalog()['recipe_version'],
        'generator_sha256':generation_fingerprint()}
    plan_path=out/'generation_plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text())!=plan:raise ValueError('Dataset output already contains another generation plan')
    plan_path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    (out/'face_topology.json').write_text(json.dumps(topology(),ensure_ascii=False,indent=2)+'\n')
    (out/'emonet_catalog.json').write_text(json.dumps(catalog(),ensure_ascii=False,indent=2)+'\n')
    (out/'social_catalog.json').write_text(json.dumps(social_catalog(),ensure_ascii=False,indent=2)+'\n')
    tasks=[(p,per_category,seed,str(out),False) for p in categories()]
    if ood_count:tasks.append(({'class_index':100,'kind':'ood','id':1,'slug':'independent_xy_jitter','label':'Unlabeled extreme XY jitter'},ood_count,seed,str(out),True))
    reports=[];failures=[];start=time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures=[executor.submit(_worker,t) for t in tasks]
        for future in as_completed(futures):
            try:report=future.result()
            except Exception as error:
                failures.append(str(error));print('Generation failure: '+str(error),flush=True);continue
            reports.append(report)
            print(f'{len(reports)}/{len(tasks)} {report["category"]["slug"]}: {report["count"]} records, {sum(s["bytes"] for s in report["shards"])/1e6:.1f} MB',flush=True)
            (out/'progress.json').write_text(json.dumps({'completed_categories':len(reports),'total_tasks':len(tasks),'completed_records':sum(r['count'] for r in reports),'compressed_bytes':sum(s['bytes'] for r in reports for s in r['shards']),'elapsed_seconds':time.monotonic()-start},indent=2)+'\n')
    if failures:
        (out/'failures.json').write_text(json.dumps(failures,indent=2)+'\n')
        raise RuntimeError('Incomplete dataset: '+str(failures))
    reports.sort(key=lambda r:r['category']['class_index']);shards=[s for r in reports for s in r['shards']]
    totals={split:sum(s['records'] for s in shards if s['file'].startswith(split+'/')) for split in ('train','validation','test')}
    manifest={**plan,'record_count':sum(r['count'] for r in reports),'split_counts':totals,'shard_count':len(shards),
      'compressed_bytes':sum(s['bytes'] for s in shards),'logical_payload_bytes':sum(s['logical_payload_bytes'] for s in shards),
      'all_records_validated':all(r['all_records_validated'] for r in reports),'all_coordinate_vectors_unique_within_category':all(r['unique_coordinate_hashes']==r['count'] for r in reports),
      'reports':reports,'shards':shards,'generation_seconds':time.monotonic()-start,'human_recognition_accuracy':None}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');return manifest


def iter_records(path,split=None):
    """Stream complete poses and SVG text from shards, without bulk extraction."""
    path=Path(path);manifest=json.loads((path/'manifest.json').read_text())
    for shard in manifest['shards']:
        if split is not None and not shard['file'].startswith(split+'/'):continue
        with tarfile.open(path/shard['file'],mode='r|gz') as archive:
            pending={}
            for member in archive:
                if not member.isfile():continue
                key,ext=member.name.rsplit('.',1);data=archive.extractfile(member).read();pending.setdefault(key,{})[ext]=data
                if 'svg' in pending[key] and 'json' in pending[key]:
                    row=pending.pop(key);yield key,row['svg'].decode(),json.loads(row['json'])
