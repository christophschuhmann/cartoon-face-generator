"""Real supervised training with per-epoch augmentation and frozen holdout pairs."""
from pathlib import Path
import argparse,json,random,time,copy
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset,DataLoader
from cartoon_face.augmentation import sample_transform,transform_image,transform_coordinates
from cartoon_face.model import topology
from .model import LandmarkNet,decode,landmark_loss


class TrainingDataset(Dataset):
    def __init__(self,path,seed=42):
        rows=[]
        for file in sorted((Path(path)/'train').glob('*.npz')):
            with np.load(file) as data:rows.append({k:data[k] for k in data.files})
        self.data={k:np.concatenate([row[k] for row in rows]) for k in rows[0]}
        self.seed=seed;self.epoch=0
    def __len__(self):return len(self.data['images'])
    def __getitem__(self,index):
        base=self.data['images'][index];h,w=base.shape
        # A new, reproducible augmentation is sampled each epoch. Validation
        # source IDs never enter this dataset, in either clean or augmented form.
        seed=int(self.seed+self.data['seeds'][index]+self.epoch*1000000007+(500000000 if self.data['ood'][index] else 0))
        d=sample_transform((w,h),(w,h),seed,True);image=transform_image(Image.fromarray(base),d)
        q=transform_coordinates(self.data['xy'][index]*[w,h],d)/[w,h]
        v=self.data['visibility'][index][np.array(d['label_permutation'])].copy()
        in_frame=(q[:,0]>=0)&(q[:,0]<1)&(q[:,1]>=0)&(q[:,1]<1);v[~in_frame]=0
        for x0,y0,x1,y1 in d['occluders']:
            hidden=(q[:,0]>=x0/w)&(q[:,0]<x1/w)&(q[:,1]>=y0/h)&(q[:,1]<y1/h)&(v>0);v[hidden]=1
        x=np.array(image,dtype=np.float32).transpose(2,0,1)/255
        return torch.from_numpy(x),torch.tensor(q,dtype=torch.float32),torch.tensor(v,dtype=torch.int64),torch.tensor(bool(self.data['ood'][index]),dtype=torch.bool)


class HoldoutDataset(Dataset):
    def __init__(self,path):
        with np.load(path) as data:self.data={k:data[k] for k in data.files}
    def __len__(self):return len(self.data['images'])
    def __getitem__(self,index):
        d=self.data;image=d['images'][index].astype(np.float32).transpose(2,0,1)/255
        return torch.from_numpy(image),torch.from_numpy(d['xy'][index]),torch.tensor(d['visibility'][index],dtype=torch.int64),torch.tensor(bool(d['ood'][index]),dtype=torch.bool),index


def worker_setup(_):
    import cv2
    cv2.setNumThreads(1);torch.set_num_threads(1)


@torch.inference_mode()
def evaluate(model,dataset,device,batch_size=128,workers=0):
    model.eval();predictions=[];presence_pred=[];ground=[];visible=[];indexes=[]
    loader=DataLoader(dataset,batch_size=batch_size,shuffle=False,num_workers=workers,worker_init_fn=worker_setup)
    for x,q,v,ood,idx in loader:
        maps,presence=model(x.to(device));predictions.append(decode(maps).cpu().numpy());presence_pred.append(presence.argmax(-1).cpu().numpy())
        ground.append(q.numpy());visible.append(v.numpy());indexes+=idx.tolist()
    pred=np.concatenate(predictions);truth=np.concatenate(ground);vis=np.concatenate(visible);presence=np.concatenate(presence_pred)
    h,w=dataset.data['images'].shape[1:3];errors=np.linalg.norm((pred-truth)*[w,h],axis=-1);diagonal=np.hypot(w,h)
    data=dataset.data
    def metrics(rows):
        mask=(vis>0)&rows[:,None];only_visible=(vis==2)&rows[:,None];error=errors[mask]
        return {'image_count':int(rows.sum()),'annotated_point_count':int(mask.sum()),'mean_error_px':float(error.mean()) if len(error) else None,
          'median_error_px':float(np.median(error)) if len(error) else None,'nme_diagonal':float(error.mean()/diagonal) if len(error) else None,
          'pck_1pct':float(np.mean(error<.01*diagonal)) if len(error) else None,'pck_2pct':float(np.mean(error<.02*diagonal)) if len(error) else None,
          'pck_5pct':float(np.mean(error<.05*diagonal)) if len(error) else None,
          'visible_only_mean_error_px':float(errors[only_visible].mean()) if only_visible.any() else None,
          'visibility_accuracy':float(np.mean((presence==vis)[rows])) if rows.any() else None}
    report={'canvas':[w,h],'normal':metrics(~data['ood']),
      'clean':metrics((~data['ood'])&(data['conditions']=='clean')),'augmented':metrics((~data['ood'])&(data['conditions']=='augmented')),
      'ood':metrics(data['ood']),'per_category':{str(i):metrics(data['categories']==i) for i in range(100)},
      'metric_definition':'Euclidean pixel error; NME and PCK thresholds relative to full image diagonal. Absent/out-of-frame points excluded; occluded points included.'}
    return report,pred,vis


def train(cache,out,epochs=15,batch_size=128,workers=12,seed=42,device='cuda:0',resume=None):
    cache=Path(cache);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.set_num_threads(4)
    if device.startswith('cuda'):
        if not torch.cuda.is_available():raise RuntimeError('CUDA requested but unavailable; use --device cpu explicitly')
        torch.cuda.manual_seed_all(seed);torch.backends.cudnn.benchmark=True
    manifest=json.loads((cache/'manifest.json').read_text());data=TrainingDataset(cache,seed);validation=HoldoutDataset(cache/'validation_heldout.npz')
    model=LandmarkNet().to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=.0015,weight_decay=.0001)
    scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=epochs,eta_min=.00006)
    scaler=torch.amp.GradScaler('cuda',enabled=device.startswith('cuda'));start_epoch=0;best=float('inf');history=[]
    if resume:
        checkpoint=torch.load(resume,map_location=device,weights_only=False)
        if checkpoint['data_contract']!=manifest['dataset_generator']:raise ValueError('Checkpoint belongs to another dataset generation contract')
        model.load_state_dict(checkpoint['model']);optimizer.load_state_dict(checkpoint['optimizer']);scheduler.load_state_dict(checkpoint['scheduler'])
        scaler.load_state_dict(checkpoint['scaler']);start_epoch=checkpoint['epoch'];best=checkpoint['best_nme'];history=checkpoint['history']
    config={'architecture':'LandmarkNet101-v1','parameters':sum(p.numel() for p in model.parameters()),'epochs':epochs,'batch_size':batch_size,
      'seed':seed,'device':device,'torch':torch.__version__,'train_records':len(data),'validation_images':len(validation),
      'data_contract':manifest['dataset_generator'],'topology_id':'cartoon_face_v1','landmark_names':[k['name'] for k in topology()['keypoints']],
      'augmentation':'face_raster_aug_v2; one new mild transformed image per source/epoch','ood_loss_weight':.25,
      'visibility_weights':{'absent':0,'occluded':.35,'visible':1},'human_video_accuracy':'unmeasured; model detects this authored cartoon rig'}
    (out/'config.json').write_text(json.dumps(config,indent=2)+'\n');print(json.dumps(config),flush=True);start=time.monotonic()
    for epoch in range(start_epoch,epochs):
        data.epoch=epoch
        # Restart workers so the epoch seed is observed in every worker copy.
        loader=DataLoader(data,batch_size=batch_size,shuffle=True,num_workers=workers,pin_memory=device.startswith('cuda'),
          worker_init_fn=worker_setup,prefetch_factor=2 if workers else None,generator=torch.Generator().manual_seed(seed+epoch))
        model.train();loss_sum=0.;seen=0;epoch_start=time.monotonic()
        for step,(x,q,v,ood) in enumerate(loader):
            x=x.to(device,non_blocking=True);q=q.to(device,non_blocking=True);v=v.to(device,non_blocking=True);ood=ood.to(device,non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type='cuda' if device.startswith('cuda') else 'cpu',dtype=torch.float16,enabled=device.startswith('cuda')):
                maps,presence=model(x);loss,parts=landmark_loss(maps,presence,q,v,ood)
            if not torch.isfinite(loss):raise ValueError('Nonfinite training loss')
            scaler.scale(loss).backward();scaler.unscale_(optimizer);torch.nn.utils.clip_grad_norm_(model.parameters(),5.)
            scaler.step(optimizer);scaler.update();loss_sum+=float(loss.detach())*len(x);seen+=len(x)
            if (step+1)%100==0:print(f'Epoch {epoch+1}/{epochs}, {seen}/{len(data)} images, loss {loss_sum/seen:.4f}',flush=True)
        scheduler.step();metrics,_,_=evaluate(model,validation,device,batch_size)
        score=metrics['normal']['nme_diagonal'];improved=score<best
        if improved:best=score
        row={'epoch':epoch+1,'train_loss':loss_sum/seen,'seconds':time.monotonic()-epoch_start,'validation':{k:metrics[k] for k in ('normal','clean','augmented','ood')}}
        history.append(row);print(json.dumps(row),flush=True)
        checkpoint={'model':model.state_dict(),'optimizer':optimizer.state_dict(),'scheduler':scheduler.state_dict(),'scaler':scaler.state_dict(),
          'epoch':epoch+1,'best_nme':best,'history':history,'config':config,'data_contract':manifest['dataset_generator']}
        torch.save(checkpoint,out/'last.pt')
        if improved:torch.save({'model':model.state_dict(),'config':config,'epoch':epoch+1,'validation':metrics,'data_contract':manifest['dataset_generator']},out/'best.pt')
        (out/'history.json').write_text(json.dumps(history,indent=2)+'\n')
    best_checkpoint=torch.load(out/'best.pt',map_location=device,weights_only=False);model.load_state_dict(best_checkpoint['model'])
    report={'best_epoch':best_checkpoint['epoch'],'training_seconds':time.monotonic()-start,'config':config,'validation':best_checkpoint['validation']}
    test=HoldoutDataset(cache/'test_heldout.npz');test_report,pred,vis=evaluate(model,test,device,batch_size);report['test']=test_report
    np.savez_compressed(out/'test_predictions.npz',xy=pred,visibility=vis,keys=test.data['keys'],conditions=test.data['conditions'])
    (out/'evaluation.json').write_text(json.dumps(report,indent=2)+'\n')
    from .visualize import visualize_predictions
    visualize_predictions(test.data,pred,vis,out/'test_examples.png')
    print(json.dumps({k:test_report[k] for k in ('normal','clean','augmented','ood')},indent=2),flush=True);return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,default=Path('datasets/training_cache_v2'));p.add_argument('--output',type=Path,default=Path('output/detector'))
    p.add_argument('--epochs',type=int,default=15);p.add_argument('--batch-size',type=int,default=128);p.add_argument('--workers',type=int,default=12)
    p.add_argument('--seed',type=int,default=42);p.add_argument('--device',default='cuda:0');p.add_argument('--resume',type=Path)
    a=p.parse_args();train(a.cache,a.output,a.epochs,a.batch_size,a.workers,a.seed,a.device,a.resume)
