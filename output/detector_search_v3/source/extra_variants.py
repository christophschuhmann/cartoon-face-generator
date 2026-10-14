"""New training-only complete poses/cache, with unchanged existing holdouts.

Adds normal expressions, moderate deformation bridges, extreme OOD and synthetic
legacy-rig variations. Saves complete pose JSONL.GZ as well as raster/label NPZ.
No original reference raster or validation/test pose is used as a training image.
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import argparse, copy, gzip, hashlib, json, time
import numpy as np
from cartoon_face.augmentation import augment_raster
from cartoon_face.large_dataset import categories, sample_pose, extreme_jitter, geometric_variation, generation_fingerprint
from cartoon_face.model import load_pose, validate_pose
from cartoon_face.reference import ROOT, NAMES

MASTER_SEED = 123456789


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def evaluation_contract(cache):
    cache=Path(cache)
    return {name:file_hash(cache/name) for name in ('validation_heldout.npz','test_heldout.npz',
        'validation_heldout_annotations.jsonl','test_heldout_annotations.jsonl')}


def generate_group(task):
    category, count, mode, out = task
    out=Path(out);stamp=f'{mode}_{category["class_index"]:03}_{category["slug"]}'
    cache=out/'train'/f'{stamp}.npz';poses=out/'poses'/f'{stamp}.jsonl.gz'
    images=[];xy=[];visibility=[];keys=[];seeds=[];class_ids=[];ood_rows=[]
    cache.parent.mkdir(parents=True,exist_ok=True);poses.parent.mkdir(parents=True,exist_ok=True)
    pose_temp=poses.with_suffix('.partial')
    with gzip.open(pose_temp,'wt',compresslevel=3,encoding='utf8') as stream:
        for i in range(count):
            offset={'normal':0,'bridge':10000,'extreme':20000,'legacy':30000}[mode]
            index=i+offset;seed=MASTER_SEED+category['class_index']*1000000+index
            if mode=='legacy':
                p=load_pose(ROOT/'poses'/f'{NAMES[i%len(NAMES)]}.json')
                p['recipe']={'version':'legacy_training_variation_v1','seed':seed}
                p=geometric_variation(p,seed+200000000)
            else:
                p,_=sample_pose(category,index,MASTER_SEED)
                if mode in ('bridge','extreme'):
                    p=extreme_jitter(p,seed+400000000,.008 if mode=='bridge' else .05,.045 if mode=='bridge' else .10)
            key=f'extra_{stamp}-{i:06}';is_ood=mode in ('bridge','extreme')
            p['name']=key;p['canvas']={'width':320,'height':round(320*400/768)}
            p['training_source']={'version':'detector_extra_variants_v1','kind':mode,'seed':seed,'split':'train',
                'source_category':category,'emotion_target_valid':mode=='normal'}
            validate_pose(p);stream.write(json.dumps(p,ensure_ascii=False,separators=(',',':'))+'\n')
            image,ann=augment_raster(p,0,320,192,False)
            images.append(np.asarray(image.convert('L')));xy.append(ann['xy_normalized']);visibility.append(ann['visibility'])
            keys.append(key);seeds.append(seed);class_ids.append(category['class_index']);ood_rows.append(is_ood)
    pose_temp.replace(poses)
    tmp=cache.with_suffix('.partial')
    with tmp.open('wb') as stream:
        np.savez_compressed(stream,images=np.asarray(images,dtype=np.uint8),xy=np.asarray(xy,dtype=np.float32),
            visibility=np.asarray(visibility,dtype=np.uint8),keys=np.array(keys),seeds=np.asarray(seeds,dtype=np.int64),
            categories=np.asarray(class_ids,dtype=np.int16),ood=np.asarray(ood_rows,dtype=bool))
    tmp.replace(cache)
    return {'kind':mode,'category':category['class_index'],'count':count,'cache':str(cache.relative_to(out)),
        'poses':str(poses.relative_to(out)),'cache_sha256':file_hash(cache),'poses_sha256':file_hash(poses),
        'bytes':cache.stat().st_size+poses.stat().st_size}


def build(cache,out,workers=24):
    cache=Path(cache);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    contract=evaluation_contract(cache)
    plan={'version':'detector_extra_variants_v1','master_seed':MASTER_SEED,'generator_sha256':generation_fingerprint(),
        'base_cache':str(cache),'evaluation_sha256':contract,'counts':{'normal':16000,'bridge':8000,'extreme':4000,'legacy':4000}}
    if (out/'manifest.json').exists():
        result=json.loads((out/'manifest.json').read_text())
        if result['plan']!=plan:raise ValueError('Extra cache belongs to another plan')
        return result
    tasks=[(c,count,kind,str(out)) for c in categories() for kind,count in [('normal',160),('bridge',80),('extreme',40)]]
    tasks.append(({'class_index':101,'slug':'legacy_rig'},4000,'legacy',str(out)))
    start=time.monotonic();rows=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(generate_group,t) for t in tasks]):
            rows.append(future.result())
            if len(rows)%20==0:print(f'Extra variants {len(rows)}/{len(tasks)}, records {sum(r["count"] for r in rows)}',flush=True)
    heldout=set()
    for split in ('validation','test'):
        with np.load(cache/f'{split}_heldout.npz') as data:heldout.update(data['keys'].tolist())
    seen=set();hashes=set();duplicates=0
    for row in rows:
        with np.load(out/row['cache']) as d:
            assert not heldout.intersection(d['keys'])
            assert not seen.intersection(d['keys']);seen.update(d['keys'].tolist())
            for q in d['xy']:
                digest=hashlib.sha256(q.tobytes()).hexdigest();duplicates+=digest in hashes;hashes.add(digest)
    assert duplicates==0,duplicates
    assert evaluation_contract(cache)==contract
    result={'plan':plan,'records':sum(r['count'] for r in rows),'unique_ids':len(seen),'unique_coordinate_vectors':len(hashes),
        'evaluation_unchanged':True,'bytes':sum(r['bytes'] for r in rows),'seconds':time.monotonic()-start,'shards':sorted(rows,key=lambda r:r['cache'])}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('shards','plan')}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cache',type=Path,default=Path('datasets/training_cache_v2'))
    parser.add_argument('--output',type=Path,default=Path('datasets/training_extra_v3'));parser.add_argument('--workers',type=int,default=24)
    args=parser.parse_args();build(args.cache,args.output,args.workers)
