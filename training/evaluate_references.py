"""Check original rasters; synthetic variants of their rig families may be trained."""
from pathlib import Path
import argparse,json,time
import numpy as np
from PIL import Image
import torch,cv2
from cartoon_face.model import load_pose,landmark_arrays
from cartoon_face.reference import ROOT,NAMES
from .model import LandmarkNet,decode
from .visualize import visualize_predictions


def evaluate_references(checkpoint,out):
    torch.set_num_threads(4);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    state=torch.load(checkpoint,map_location='cpu',weights_only=False)
    model=LandmarkNet();model.load_state_dict(state['model']);model.eval();rows=[];images=[];coords=[];pred=[];vis=[];timings=[]
    for name in NAMES:
        source=Image.open(ROOT/f'output/references/{name}.png').convert('RGB');sw,sh=source.size;w,h=320,192;scale=min(w/sw,h/sh)
        matrix=np.array([[scale,0,(w-scale*sw)/2],[0,scale,(h-scale*sh)/2]])
        image=cv2.warpAffine(np.array(source),matrix,(w,h),borderValue=(255,255,255));p=load_pose(ROOT/f'poses/{name}.json')
        q,v=landmark_arrays(p);q=q*[sw,sh]*scale+matrix[:,2]
        x=torch.from_numpy(image.astype(np.float32).transpose(2,0,1)[None]/255)
        with torch.inference_mode():
            model(x)
            trials=[]
            for _ in range(10):
                start=time.perf_counter();maps,_=model(x);actual=decode(maps)[0].numpy();trials.append((time.perf_counter()-start)*1000)
        errors=np.linalg.norm(actual*[w,h]-q,axis=1);selected=errors[v>0];timings+=trials
        rows.append({'reference':name,'annotated_points':int(np.sum(v>0)),'mean_error_px_320x192':float(selected.mean()),
          'pck_1pct':float(np.mean(selected<np.hypot(w,h)*.01)),'pck_2pct':float(np.mean(selected<np.hypot(w,h)*.02)),
          'cpu_inference_median_ms':float(np.median(trials))})
        images.append(image);coords.append(q/[w,h]);pred.append(actual);vis.append(v)
    data={'images':np.array(images),'xy':np.array(coords),'categories':np.arange(len(NAMES)),
      'conditions':np.array(['augmented']*len(NAMES)),'keys':np.array(NAMES)}
    visualize_predictions(data,np.array(pred),np.array(vis),out/'external_references.png')
    report={'kind':'additional external reference-domain evaluation, not used for checkpoint selection','source_images':6,
      'canvas':[320,192],'checkpoint_epoch':state['epoch'],'per_reference':rows,
      'mean_error_px_mean_of_references':float(np.mean([r['mean_error_px_320x192'] for r in rows])),
      'cpu_inference_median_ms':float(np.median(timings)),'cpu_threads':4,
      'original_rasters_used_for_training':False,
      'synthetic_reference_pose_families_in_training':state['config'].get('augmentation')=='training_raster_aug_v3',
      'scope':'Six original drawings of the same identity; rig-fitted labels, not independent human annotations. Synthetic pose families may be trained. Not arbitrary cartoons or real video; MediaPipe is separate.'}
    (out/'external_references.json').write_text(json.dumps(report,indent=2)+'\n');return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--checkpoint',type=Path,default=ROOT/'output/detector/best.pt')
    parser.add_argument('--output',type=Path,default=ROOT/'output/detector')
    args=parser.parse_args();print(json.dumps(evaluate_references(args.checkpoint,args.output),indent=2))


if __name__=='__main__':main()
