"""Cache clean rasters; freeze five unseen poses/class, clean + augmented each."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import argparse,copy,io,json,tarfile,time
import numpy as np
from PIL import Image
from cartoon_face.augmentation import augment_raster,sample_transform,transform_coordinates,transform_image,draw_annotation


def shard_records(path):
    with tarfile.open(path,mode='r|gz') as archive:
        pending={}
        for member in archive:
            if not member.isfile():continue
            key,ext=member.name.rsplit('.',1);pending.setdefault(key,{})[ext]=archive.extractfile(member).read()
            if 'svg' in pending[key] and 'json' in pending[key]:
                row=pending.pop(key);yield key,row['svg'].decode(),json.loads(row['json'])
        if pending:raise ValueError('Unpaired SVG/JSON shard members')


def _prepare_class(task):
    report,source,out,width,height,heldout=task;source=Path(source);out=Path(out)
    cls=report['category'];ood=report['ood'];stamp=f"{cls['kind']}_{cls['id']:02}_{cls['slug']}";reports=[]
    for shard in report['shards']:
        split=shard['file'].split('/')[0];destination=out/split/(stamp+'.npz');destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():
            with np.load(destination) as data:reports.append({'file':str(destination.relative_to(out)),'split':split,'count':len(data['images']),'ood':ood})
            continue
        images=[];coords=[];vis=[];keys=[];seeds=[];categories=[]
        for i,(key,svg,p) in enumerate(shard_records(source/shard['file'])):
            if split!='train' and i>=(100 if ood else heldout):break
            p=copy.deepcopy(p);p['canvas']={'width':width,'height':round(width*400/768)}
            image,ann=augment_raster(p,0,width,height,False,svg)
            images.append(np.asarray(image.convert('L')));coords.append(ann['xy_normalized']);vis.append(ann['visibility'])
            keys.append(key);seeds.append(p['dataset']['source_seed']);categories.append(cls['class_index'])
        if images:
            tmp=destination.with_suffix('.partial')
            with tmp.open('wb') as f:np.savez_compressed(f,images=np.array(images,dtype=np.uint8),xy=np.array(coords,dtype=np.float32),
                visibility=np.array(vis,dtype=np.uint8),keys=np.array(keys),seeds=np.array(seeds,dtype=np.int64),
                categories=np.array(categories,dtype=np.int16),ood=np.full(len(images),ood,dtype=bool))
            tmp.replace(destination);reports.append({'file':str(destination.relative_to(out)),'split':split,'count':len(images),'ood':ood})
    return reports


def freeze_holdout(out,split,width,height,seed):
    """Two images per held-out source pose; every class contributes exactly five."""
    images=[];coordinates=[];visibility=[];ids=[];keys=[];conditions=[];ood_rows=[];source_seeds=[]
    images_dir=out/'heldout_examples'/split;images_dir.mkdir(parents=True,exist_ok=True)
    annotation_path=out/f'{split}_heldout_annotations.jsonl'
    with annotation_path.open('w') as annotations:
        for file in sorted((out/split).glob('*.npz')):
            with np.load(file) as rows:
                for i in range(len(rows['images'])):
                    source_image=Image.fromarray(rows['images'][i]);key=str(rows['keys'][i]);is_ood=bool(rows['ood'][i])
                    for condition in ('clean','augmented'):
                        sample_seed=int(seed+rows['seeds'][i]+(500000000 if is_ood else 0))
                        transform=sample_transform((width,height),(width,height),sample_seed,condition=='augmented')
                        image=transform_image(source_image,transform);q=transform_coordinates(rows['xy'][i]*[width,height],transform)
                        v=rows['visibility'][i][np.array(transform['label_permutation'])].copy()
                        in_frame=(q[:,0]>=0)&(q[:,0]<width)&(q[:,1]>=0)&(q[:,1]<height);v[~in_frame]=0
                        for x0,y0,x1,y1 in transform['occluders']:
                            hidden=(q[:,0]>=x0)&(q[:,0]<x1)&(q[:,1]>=y0)&(q[:,1]<y1)&(v>0);v[hidden]=1
                        ann={'sample_id':key,'condition':condition,'source_split':split,'ood':is_ood,'keypoint_ids':list(range(101)),
                          'xy_pixels':q.tolist(),'xy_normalized':(q/[width,height]).tolist(),'visibility':v.tolist(),'in_frame':in_frame.tolist(),
                          'transform':transform,'image':f'heldout_examples/{split}/{key}_{condition}.png'}
                        image.save(images_dir/f'{key}_{condition}.png');annotations.write(json.dumps(ann,ensure_ascii=False,separators=(',',':'))+'\n')
                        images.append(np.array(image));coordinates.append(q/[width,height]);visibility.append(v);keys.append(key)
                        ids.append(int(rows['categories'][i]));conditions.append(condition);ood_rows.append(is_ood);source_seeds.append(int(rows['seeds'][i]))
    np.savez_compressed(out/f'{split}_heldout.npz',images=np.array(images,dtype=np.uint8),xy=np.array(coordinates,dtype=np.float32),
      visibility=np.array(visibility,dtype=np.uint8),categories=np.array(ids,dtype=np.int16),conditions=np.array(conditions),
      ood=np.array(ood_rows,dtype=bool),keys=np.array(keys),seeds=np.array(source_seeds,dtype=np.int64))
    return {'source_poses':len(images)//2,'clean_images':conditions.count('clean'),'augmented_images':conditions.count('augmented'),
      'normal_images':sum(not x for x in ood_rows),'ood_images':sum(ood_rows),'duplicate_source_ids_across_conditions':True}


def prepare(source,out,width=320,height=192,heldout=5,workers=16,seed=42):
    source=Path(source);out=Path(out);out.mkdir(parents=True,exist_ok=True);manifest=json.loads((source/'manifest.json').read_text())
    plan={'dataset_generator':manifest['generator_sha256'],'dataset_version':manifest['dataset_version'],
      'canvas':[width,height],'heldout_per_class':heldout,'seed':seed,'clean_and_augmented':True,'augmentation_version':'face_raster_aug_v2'}
    plan_path=out/'preparation_plan.json'
    if plan_path.exists() and json.loads(plan_path.read_text())!=plan:raise ValueError('Training cache already belongs to another preparation plan')
    plan_path.write_text(json.dumps(plan,indent=2)+'\n');start=time.monotonic();rows=[]
    tasks=[(r,str(source),str(out),width,height,heldout) for r in manifest['reports']]
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for n,future in enumerate(as_completed([executor.submit(_prepare_class,t) for t in tasks])):
            rows+=future.result();print(f'Raster cache {n+1}/{len(tasks)}',flush=True)
    holdout={split:freeze_holdout(out,split,width,height,seed+900000000+(100000000 if split=='test' else 0)) for split in ('validation','test')}
    train_ids=set()
    for p in (out/'train').glob('*.npz'):
        with np.load(p) as d:train_ids.update(d['keys'].tolist())
    validation=np.load(out/'validation_heldout.npz');test=np.load(out/'test_heldout.npz')
    assert not train_ids.intersection(validation['keys']) and not train_ids.intersection(test['keys'])
    assert not set(validation['keys']).intersection(test['keys'])
    result={**plan,'train_records':len(train_ids),'holdout':holdout,'split_disjoint':True,'cache_shards':rows,
      'seconds':time.monotonic()-start,'compressed_bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file())}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--dataset',type=Path,default=Path('datasets/cartoon_landmarks_v2'))
    a.add_argument('--output',type=Path,default=Path('datasets/training_cache_v2'));a.add_argument('--workers',type=int,default=16)
    args=a.parse_args();print(json.dumps(prepare(args.dataset,args.output,workers=args.workers),indent=2))
