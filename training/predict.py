"""CPU or GPU inference on external cartoon images, preserving original pixels."""
from pathlib import Path
import argparse,json,time
import numpy as np
from PIL import Image
import torch
from cartoon_face.augmentation import sample_transform
from .model import LandmarkNet,decode


def predict(image,checkpoint,device='cpu'):
    torch.set_num_threads(4);state=torch.load(checkpoint,map_location=device,weights_only=False)
    model=LandmarkNet().to(device);model.load_state_dict(state['model']);model.eval()
    image=image.convert('RGB');sw,sh=image.size;w,h=320,192;fit=min(w/sw,h/sh)
    # Preserve RGB appearance: ordinary inference must not replace user colors.
    import cv2
    transform=np.array([[fit,0,(w-fit*sw)/2],[0,fit,(h-fit*sh)/2]],dtype=float)
    resized=cv2.warpAffine(np.array(image),transform,(w,h),borderValue=(255,255,255))
    x=torch.from_numpy(resized.astype(np.float32).transpose(2,0,1)[None]/255).to(device)
    start=time.perf_counter()
    with torch.inference_mode():maps,logits=model(x);q=decode(maps)[0].cpu().numpy();visibility=logits.softmax(-1)[0].cpu().numpy()
    elapsed=(time.perf_counter()-start)*1000
    pixels=(q*[w,h]-transform[:,2])/fit
    from cartoon_face.model import topology
    return {'schema_version':'predicted_cartoon_landmarks_v1','topology_id':'cartoon_face_v1','canvas':{'width':sw,'height':sh},
      'xy_pixels':pixels.tolist(),'xy_normalized':(pixels/[sw,sh]).tolist(),'keypoint_names':[k['name'] for k in topology()['keypoints']],
      'keypoint_ids':list(range(101)),'visibility_probabilities':visibility.tolist(),'inference_ms':elapsed,
      'scope':'This synthetic-cartoon detector is separate from the human MediaPipe webcam mapper.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--checkpoint',type=Path,default=Path('output/detector/best.pt'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--device',default='cpu');a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(predict(Image.open(a.image),a.checkpoint,a.device),indent=2)+'\n')
