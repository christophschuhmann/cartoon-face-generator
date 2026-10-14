"""Read every stored pair; validate 101 labels, hashes, splits and sampled replay."""
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import argparse,hashlib,json,sys,time
import numpy as np
from cartoon_face.reference import ROOT
from cartoon_face.model import validate_pose
from cartoon_face.renderer import render_svg
from cartoon_face.large_dataset import file_hash,generation_fingerprint
sys.path.insert(0,str(ROOT))
from training.prepare import shard_records


def audit_shard(task):
    root,row=task;path=Path(root)/row['file'];count=0;ids=[];replays=0;split=row['file'].split('/')[0]
    assert path.stat().st_size==row['bytes'] and file_hash(path)==row['sha256']
    chosen={0,row['records']//2,row['records']-1}
    for i,(key,svg,p) in enumerate(shard_records(path)):
        validate_pose(p);assert len(p['keypoints'])==101
        assert p['dataset']['sample_id']==key and p['dataset']['split']==split
        assert p['geometry']['under_eye_transition']=='stroke_bank_v1'
        if p['dataset']['ood']:
            delta=np.abs(p['recipe']['ood_jitter']['actual_delta']);assert np.all(delta>=.05) and np.all(delta<=.1)
            assert p['dataset']['target'] is None and 'emotion' not in p and 'expression' not in p
        if i in chosen:assert render_svg(p)==svg;replays+=1
        ids.append(key);count+=1
    assert count==row['records']
    return {'file':row['file'],'count':count,'replays':replays,'sample_ids':ids}


def audit(root,workers=16):
    root=Path(root);m=json.loads((root/'manifest.json').read_text());start=time.monotonic();reports=[]
    assert m['generator_sha256']==generation_fingerprint()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n,future in enumerate(as_completed([pool.submit(audit_shard,(str(root),row)) for row in m['shards']])):
            reports.append(future.result())
            if (n+1)%50==0:print(f'Audited {n+1}/{len(m["shards"])} shards',flush=True)
    ids=[key for r in reports for key in r['sample_ids']]
    assert len(ids)==len(set(ids))==m['record_count']
    result={'dataset_version':m['dataset_version'],'generator_fingerprint_matches':True,'all_shard_hashes_match':True,
      'all_records_read_and_validated':len(ids),'unique_sample_ids':len(set(ids)),
      'byte_exact_svg_replays':sum(r['replays'] for r in reports),'shards':len(reports),'seconds':time.monotonic()-start}
    (root/'audit.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=ROOT/'datasets/cartoon_landmarks_v2');p.add_argument('--workers',type=int,default=16)
    a=p.parse_args();print(json.dumps(audit(a.dataset,a.workers),indent=2))
