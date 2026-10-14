"""Validate all additional full poses and exact sampled raster/label replays."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import argparse,gzip,json,sys
import numpy as np
from cartoon_face.model import validate_pose
from cartoon_face.augmentation import augment_raster
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from training.extra_variants import file_hash,evaluation_contract


def audit_shard(task):
    root,row=task;root=Path(root);cache=root/row['cache'];poses=root/row['poses']
    assert file_hash(cache)==row['cache_sha256'] and file_hash(poses)==row['poses_sha256']
    chosen={0,row['count']//2,row['count']-1};count=0;replays=0
    with np.load(cache) as data,gzip.open(poses,'rt',encoding='utf8') as stream:
        for i,line in enumerate(stream):
            pose=json.loads(line);validate_pose(pose);assert pose['name']==data['keys'][i]
            assert pose['training_source']['split']=='train'
            if i in chosen:
                image,annotation=augment_raster(pose,0,320,192,False)
                assert np.array_equal(np.asarray(image.convert('L')),data['images'][i])
                assert np.array_equal(np.asarray(annotation['xy_normalized'],dtype=np.float32),data['xy'][i])
                assert np.array_equal(annotation['visibility'],data['visibility'][i])
                replays+=1
            count+=1
    assert count==row['count']
    return {'count':count,'replays':replays}


def main():
    p=argparse.ArgumentParser();p.add_argument('--extra',type=Path,default=Path('datasets/training_extra_v3'))
    p.add_argument('--cache',type=Path,default=Path('datasets/training_cache_v2'));p.add_argument('--workers',type=int,default=12)
    args=p.parse_args();manifest=json.loads((args.extra/'manifest.json').read_text())
    assert evaluation_contract(args.cache)==manifest['plan']['evaluation_sha256']
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(audit_shard,(str(args.extra),row)) for row in manifest['shards']]):rows.append(future.result())
    report={'all_extra_poses_validated':sum(row['count'] for row in rows),'byte_exact_raster_and_label_replays':sum(row['replays'] for row in rows),
        'all_shard_hashes_match':True,'frozen_evaluation_unchanged':True}
    (args.extra/'audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
