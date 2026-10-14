"""Longer warm-start candidates on extra variants and unchanged evaluation files.

Each candidate sees every base training record plus deterministic OOD repeats.
Checkpoints are ranked on validation ONLY. Test evaluation is deferred until all
candidates finish and selection has been written to disk by compare_search.py.
"""
from pathlib import Path
import argparse, copy, json, math, random, time
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset,DataLoader
from .augmentation import sample_training_transform,training_coordinates,training_image,VERSION
from .extra_variants import evaluation_contract,file_hash
from .model import LandmarkNet,landmark_loss
from .train import evaluate,HoldoutDataset,worker_setup


class ExpandedDataset(Dataset):
    def __init__(self,cache,extra,seed,profile,ood_fraction):
        shards=sorted((Path(cache)/'train').glob('*.npz'))+sorted((Path(extra)/'train').glob('*.npz'))
        rows=[]
        for file in shards:
            with np.load(file) as data:rows.append({k:data[k] for k in data.files})
        self.data={k:np.concatenate([row[k] for row in rows]) for k in rows[0]}
        del rows
        self.seed=seed;self.profile=profile;self.epoch=0;self.strength=1.
        ood_indices=np.flatnonzero(self.data['ood']);normal_count=int((~self.data['ood']).sum())
        target_ood=round(normal_count*ood_fraction/(1-ood_fraction))
        count=max(0,target_ood-len(ood_indices))
        repeats=np.random.default_rng(seed).choice(ood_indices,count,replace=True) if count else np.empty(0,dtype=np.int64)
        self.indices=np.concatenate([np.arange(len(self.data['images'])),repeats])
        self.source_count=len(self.data['images'])
        self.ood_views=int(self.data['ood'][self.indices].sum())
    def __len__(self):return len(self.indices)
    def __getitem__(self,view):
        index=self.indices[view];base=self.data['images'][index];h,w=base.shape
        seed=int(self.seed+self.data['seeds'][index]+self.epoch*1000000007+view*100003+(500000000 if self.data['ood'][index] else 0))
        descriptor=sample_training_transform((w,h),seed,self.profile,self.strength)
        image=training_image(Image.fromarray(base),descriptor)
        q=training_coordinates(self.data['xy'][index]*[w,h],descriptor)/[w,h]
        v=self.data['visibility'][index][np.array(descriptor['label_permutation'])].copy()
        v[(q[:,0]<0)|(q[:,0]>=1)|(q[:,1]<0)|(q[:,1]>=1)]=0
        for x0,y0,x1,y1 in descriptor['occluders']:
            hidden=(q[:,0]>=x0/w)&(q[:,0]<x1/w)&(q[:,1]>=y0/h)&(q[:,1]<y1/h)&(v>0);v[hidden]=1
        return (torch.from_numpy(np.asarray(image,dtype=np.float32).transpose(2,0,1)/255),
            torch.tensor(q,dtype=torch.float32),torch.tensor(v,dtype=torch.int64),torch.tensor(bool(self.data['ood'][index])))


def validation_score(metrics,normal_guard=.5):
    """Balanced normal/OOD mean error, with <=0.5px normal-quality guardrail."""
    if metrics['normal']['mean_error_px']>normal_guard:return float('inf')
    return .25*metrics['clean']['nme_diagonal']+.25*metrics['augmented']['nme_diagonal']+.5*metrics['ood']['nme_diagonal']


def train_candidate(cache,extra,out,initial,profile='strong',epochs=40,batch_size=256,workers=16,
                    seed=101,device='cuda:0',lr=.0005,ood_weight=.5,ood_fraction=.2,patience=10,
                    min_epochs=24,max_steps=None):
    cache=Path(cache);extra=Path(extra);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if (out/'config.json').exists():raise ValueError('Use a new candidate directory; existing run will not be overwritten')
    contract=evaluation_contract(cache);extra_manifest=json.loads((extra/'manifest.json').read_text())
    assert extra_manifest['evaluation_unchanged'] and contract==extra_manifest['plan']['evaluation_sha256']
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.set_num_threads(4)
    if device.startswith('cuda'):
        if not torch.cuda.is_available():raise RuntimeError('CUDA is unavailable')
        torch.cuda.manual_seed_all(seed);torch.backends.cudnn.benchmark=True
    data=ExpandedDataset(cache,extra,seed,profile,ood_fraction);validation=HoldoutDataset(cache/'validation_heldout.npz')
    state=torch.load(initial,map_location=device,weights_only=False);model=LandmarkNet().to(device);model.load_state_dict(state['model'])
    optimizer=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=.00015)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=epochs,eta_min=.00002)
    scaler=torch.amp.GradScaler('cuda',enabled=device.startswith('cuda'))
    heldout_ids=set(validation.data['keys'])
    with np.load(cache/'test_heldout.npz') as test:heldout_ids.update(test['keys'])
    assert not heldout_ids.intersection(data.data['keys'])
    config={'architecture':'LandmarkNet101-v1','parameters':sum(p.numel() for p in model.parameters()),'epochs':epochs,
        'batch_size':batch_size,'workers':workers,'seed':seed,'device':device,'torch':torch.__version__,'augmentation':VERSION,
        'profile':profile,'train_records':data.source_count,'views_per_epoch':len(data),'ood_views_per_epoch':data.ood_views,
        'lr':lr,'ood_loss_weight':ood_weight,'initial_checkpoint_sha256':file_hash(initial),'initial_epoch':state['epoch'],
        'evaluation_sha256':contract,'extra_manifest_sha256':file_hash(extra/'manifest.json'),
        'selection':'validation only: .25 clean NME + .25 augmented NME + .5 OOD NME; normal error must be <= .5px',
        'normal_error_guard_px':.5,'min_epochs':min_epochs,'early_stop_patience':patience,'max_steps':max_steps,
        'data_contract':state['data_contract'],'topology_id':'cartoon_face_v1',
        'landmark_names':state['config']['landmark_names'],'human_video_accuracy':'unmeasured'}
    (out/'config.json').write_text(json.dumps(config,indent=2)+'\n');print(json.dumps(config),flush=True)
    baseline,_,_=evaluate(model,validation,device,batch_size)
    best=validation_score(baseline);best_normal=baseline['normal']['nme_diagonal'];best_epoch=0;history=[];start=time.monotonic()
    save={'model':copy.deepcopy(model.state_dict()),'config':config,'epoch':0,'validation':baseline,'data_contract':state['data_contract']}
    torch.save(save,out/'best.pt');torch.save(save,out/'best_normal.pt')
    (out/'initial_validation.json').write_text(json.dumps(baseline,indent=2)+'\n')
    for epoch in range(epochs):
        data.epoch=epoch
        # Curriculum ramps stronger distortions; the tail restores precise easy views.
        strength=min(1.,.35+epoch/8) if profile=='curriculum' else 1.
        if epoch>=epochs-6:strength*=.55
        data.strength=strength;epoch_start=time.monotonic();seen=0;loss_sum=0
        loader=DataLoader(data,batch_size=batch_size,shuffle=True,num_workers=workers,pin_memory=device.startswith('cuda'),
            worker_init_fn=worker_setup,prefetch_factor=2 if workers else None,generator=torch.Generator().manual_seed(seed+epoch))
        model.train()
        for step,(x,q,v,ood) in enumerate(loader):
            if max_steps is not None and step>=max_steps:break
            x=x.to(device,non_blocking=True);q=q.to(device,non_blocking=True);v=v.to(device,non_blocking=True);ood=ood.to(device,non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type='cuda' if device.startswith('cuda') else 'cpu',dtype=torch.float16,enabled=device.startswith('cuda')):
                heatmaps,presence=model(x);loss,_=landmark_loss(heatmaps,presence,q,v,ood,ood_weight)
            if not torch.isfinite(loss):raise ValueError('Nonfinite training loss')
            scaler.scale(loss).backward();scaler.unscale_(optimizer);torch.nn.utils.clip_grad_norm_(model.parameters(),5.)
            scaler.step(optimizer);scaler.update();seen+=len(x);loss_sum+=float(loss.detach())*len(x)
            if (step+1)%150==0:print(f'Epoch {epoch+1}/{epochs}: {seen}/{len(data)} views',flush=True)
        scheduler.step();metrics,_,_=evaluate(model,validation,device,batch_size);score=validation_score(metrics)
        row={'epoch':epoch+1,'augmentation_strength':strength,'train_loss':loss_sum/seen,'views':seen,
            'seconds':time.monotonic()-epoch_start,'score':score if math.isfinite(score) else None,
            'validation':{k:metrics[k] for k in ('normal','clean','augmented','ood')}}
        history.append(row);print(json.dumps(row),flush=True)
        save={'model':model.state_dict(),'config':config,'epoch':epoch+1,'validation':metrics,'data_contract':state['data_contract']}
        if score<best:best=score;best_epoch=epoch+1;torch.save(save,out/'best.pt')
        if metrics['normal']['nme_diagonal']<best_normal:
            best_normal=metrics['normal']['nme_diagonal'];torch.save(save,out/'best_normal.pt')
        torch.save({**save,'optimizer':optimizer.state_dict(),'scheduler':scheduler.state_dict(),'scaler':scaler.state_dict()},out/'last.pt')
        (out/'history.json').write_text(json.dumps(history,indent=2)+'\n')
        if epoch+1>=min_epochs and epoch+1-best_epoch>=patience:break
    assert evaluation_contract(cache)==contract
    chosen=torch.load(out/'best.pt',map_location='cpu',weights_only=False)
    report={'completed':True,'best_epoch':chosen['epoch'],'epochs_completed':len(history),'training_seconds':time.monotonic()-start,
        'config':config,'validation':chosen['validation'],'best_score':best,'evaluation_files_unchanged':True,
        'test_evaluated':False,'total_augmented_training_views':sum(row['views'] for row in history)}
    (out/'candidate.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('config','validation')}),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,default=Path('datasets/training_cache_v2'))
    p.add_argument('--extra',type=Path,default=Path('datasets/training_extra_v3'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--initial',type=Path,default=Path('output/detector/best.pt'));p.add_argument('--profile',choices=['mild','strong','robust','curriculum'],default='strong')
    p.add_argument('--epochs',type=int,default=40);p.add_argument('--batch-size',type=int,default=256);p.add_argument('--workers',type=int,default=16)
    p.add_argument('--seed',type=int,default=101);p.add_argument('--device',default='cuda:0');p.add_argument('--lr',type=float,default=.0005)
    p.add_argument('--ood-weight',type=float,default=.5);p.add_argument('--ood-fraction',type=float,default=.2)
    p.add_argument('--patience',type=int,default=10);p.add_argument('--min-epochs',type=int,default=24);p.add_argument('--max-steps',type=int)
    a=p.parse_args();train_candidate(a.cache,a.extra,a.output,a.initial,a.profile,a.epochs,a.batch_size,a.workers,a.seed,a.device,
        a.lr,a.ood_weight,a.ood_fraction,a.patience,a.min_epochs,a.max_steps)
