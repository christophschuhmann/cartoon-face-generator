"""Optional CPU tongue evidence from Babble or SigLIP2, always off the frame path.

Neither is calibrated for this user's webcam. SigLIP similarities are not
probabilities; old results are discarded when the mouth has changed.
"""
from pathlib import Path
import math
import threading
import time
import json
import numpy as np
import cv2
from PIL import Image

ROOT=Path(__file__).parent/'models/mouth'
PROMPTS={
 'tongue':['a photo of a person sticking their tongue out of their mouth.',
           'a close-up of a face with the tongue extended over the lower lip.',
           'a person showing their tongue to the camera.'],
 'pout':['a photo of a person pouting with closed lips.',
         'a close-up of a face with pursed lips making a kiss.',
         'a person pushing their lower lip forward without showing the tongue.'],
 'smile':['a photo of a person smiling and showing their teeth.',
          'a close-up of a smiling face with no tongue visible.',
          'a person laughing with their teeth visible.'],
 'open':['a photo of a person speaking with their mouth open.',
         'a person opening their mouth without sticking out their tongue.',
         'a close-up of a face with an open mouth and teeth.'],
 'closed':['a photo of a person with their mouth closed.',
           'a close-up of a relaxed face with closed lips.',
           'a person looking at the camera with a neutral mouth.'],
}

def available(mode):
    if mode=='babble':return (ROOT/'babble.onnx').is_file() and (ROOT/'babble.onnx').stat().st_size==23691283
    if mode=='siglip':return (ROOT/'vision_model_q4.onnx').is_file() and (ROOT/'mouth_prompts.npy').is_file()
    return mode in ('geometry','off')

def session(path):
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=options.inter_op_num_threads=1
    options.add_session_config_entry('session.intra_op.allow_spinning','0')
    options.enable_cpu_mem_arena=False
    return ort.InferenceSession(str(path),options,providers=['CPUExecutionProvider'])

def mouth_crop(rgb,observation):
    q=np.asarray(observation.landmarks)[:,:2]*[observation.width,observation.height]
    width=float(np.linalg.norm(q[291]-q[61]))
    if not np.isfinite(q).all() or width<16:return None
    center=(q[13]+q[14])/2
    xaxis=(q[291]-q[61])/width;yaxis=np.array([-xaxis[1],xaxis[0]])
    basis=np.stack([xaxis,yaxis])*(224/(width*2.3))
    offset=np.array([112.,95.])-basis@center
    return cv2.warpAffine(rgb,np.column_stack([basis,offset]),(224,224),borderMode=cv2.BORDER_REPLICATE)

def face_crop(rgb,observation):
    q=np.asarray(observation.landmarks)[:,:2]*[observation.width,observation.height]
    lo=q.min(axis=0);hi=q.max(axis=0);center=(lo+hi)/2;size=max(hi-lo)*1.12
    if not np.isfinite(size) or size<32:return None
    matrix=np.array([[224/size,0,112-center[0]*224/size],[0,224/size,112-center[1]*224/size]])
    return cv2.warpAffine(rgb,matrix,(224,224),borderMode=cv2.BORDER_REPLICATE)

class BabbleModel:
    def __init__(self):self.net=session(ROOT/'babble.onnx')
    def infer(self,rgb):
        gray=cv2.cvtColor(cv2.resize(rgb,(224,224)),cv2.COLOR_RGB2GRAY).astype(np.float32)/255
        scores=self.net.run(None,{self.net.get_inputs()[0].name:gray[None,None]})[0].reshape(-1)
        if scores.size!=45 or not np.isfinite(scores).all():raise ValueError('Invalid Babble output')
        return {'tongue':float(np.clip(scores[33],0,1)), 'pout':float(np.clip(max(scores[11],scores[17]),0,1)),
                'jaw':float(np.clip(scores[4],0,1))}

def prepare_prompts():
    from tokenizers import Tokenizer
    tokenizer=Tokenizer.from_file(str(ROOT/'tokenizer.json'));tokenizer.enable_truncation(max_length=64)
    tokenizer.enable_padding(length=64,pad_id=0,pad_token='<pad>')
    net=session(ROOT/'text_model_int8.onnx')
    output=next((o.name for o in net.get_outputs() if 'embed' in o.name),net.get_outputs()[-1].name)
    vectors=[]
    for label,prompts in PROMPTS.items():
        rows=[]
        for text in prompts:
            ids=np.asarray([tokenizer.encode(text.lower()).ids],np.int64)
            feed={x.name:ids if 'input_ids' in x.name else (ids!=0).astype(np.int64) for x in net.get_inputs()}
            embedding=net.run([output],feed)[0].reshape(-1).astype(np.float32)
            rows.append(embedding/max(np.linalg.norm(embedding),1e-8))
        vector=np.mean(rows,axis=0);vectors.append(vector/max(np.linalg.norm(vector),1e-8))
        print('Prompt vectors:',label,flush=True)
    np.save(ROOT/'mouth_prompts.npy',np.stack(vectors),allow_pickle=False)
    (ROOT/'mouth_prompts.json').write_text(json.dumps(PROMPTS,indent=2))

class SiglipMouthModel:
    def __init__(self):
        self.net=session(ROOT/'vision_model_q4.onnx');self.prompts=np.load(ROOT/'mouth_prompts.npy',allow_pickle=False)
        self.output=next((o.name for o in self.net.get_outputs() if 'embed' in o.name),self.net.get_outputs()[-1].name)
    def infer(self,rgb):
        image=Image.fromarray(rgb).resize((224,224),Image.Resampling.BILINEAR)
        tensor=(np.asarray(image,dtype=np.float32)/127.5-1).transpose(2,0,1)[None]
        v=self.net.run([self.output],{self.net.get_inputs()[0].name:np.ascontiguousarray(tensor)})[0].reshape(-1)
        v=v/max(np.linalg.norm(v),1e-8);cosine=self.prompts@v
        if not np.isfinite(cosine).all():raise ValueError('Invalid SigLIP output')
        margin=float(cosine[0]-max(cosine[1:]))
        scores=dict(zip(PROMPTS,map(float,cosine)))
        return {'tongue':float(np.clip((margin+.005)/.05,0,1)), 'pout':float(np.argmax(cosine)==1),
                'label':max(scores,key=scores.get),'similarities':scores,'margin':margin}

class MouthTracker:
    def __init__(self,mode=None):
        self.mode=mode or ('siglip' if available('siglip') else 'babble' if available('babble') else 'geometry')
        self.lock=threading.Lock();self.event=threading.Event();self.pending=None;self.result=None
        self.release_requested=False
        self.generation=0;self.thread=None;self.error=None;self.last_submit=-math.inf
    def settings(self):return {'mode':self.mode,'available':{m:available(m) for m in ('babble','siglip','geometry','off')},'error':self.error}
    def configure(self,data):
        mode=data.get('mode',self.mode)
        if mode not in ('babble','siglip','geometry','off') or not available(mode):raise ValueError('Mundmodell ist noch nicht eingerichtet.')
        if mode!=self.mode:self.clear();self.mode=mode
    def clear(self):
        with self.lock:self.generation+=1;self.pending=self.result=None
    def close(self):
        self.clear()
        with self.lock:self.release_requested=True
        self.event.set()
    def _run(self):
        models={}
        while True:
            self.event.wait()
            with self.lock:
                item,self.pending=self.pending,None;self.event.clear()
                release=self.release_requested;self.release_requested=False
            if release:models.clear()
            if item is None:continue
            crop,captured,generation,mode,signature=item
            try:
                if mode not in models:models[mode]=BabbleModel() if mode=='babble' else SiglipMouthModel()
                started=time.perf_counter();result=models[mode].infer(crop)
                result.update(captured=captured,ms=(time.perf_counter()-started)*1000,signature=signature,mode=mode)
                with self.lock:
                    if generation==self.generation:self.result=result;self.error=None
            except Exception as error:
                with self.lock:
                    if generation==self.generation:self.error=str(error)
    def update(self,rgb,observation):
        if observation is None:self.clear();return {'mode':self.mode,'state':'no_face'}
        shapes=observation.blendshapes;geometry=observation.tongue_out
        if self.mode=='off':observation.tongue_out=0;return {'mode':'off','state':'off'}
        if self.mode=='geometry':return {'mode':'geometry','state':'active','tongue':geometry}
        now=time.monotonic();signature=np.array([shapes.get(k,0) for k in ('jawOpen','mouthPucker','mouthSmileLeft','mouthShrugLower')])
        if now-self.last_submit>(.10 if self.mode=='babble' else .65) and len(observation.landmarks)>=468:
            crop=(mouth_crop if self.mode=='babble' else face_crop)(rgb,observation)
            if crop is not None:
                with self.lock:
                    self.pending=(crop,now,self.generation,self.mode,signature);self.last_submit=now
                    if self.thread is None:self.thread=threading.Thread(target=self._run,daemon=True,name='mouth-cpu');self.thread.start()
                self.event.set()
        with self.lock:result=dict(self.result) if self.result else None;error=self.error
        status={'mode':self.mode,'state':'loading','error':error,'geometry':geometry}
        if result:
            age=now-result['captured'];agreement=float(np.max(np.abs(signature-result.pop('signature'))))
            status.update({k:v for k,v in result.items() if k!='captured'},age_seconds=age,state='active')
            # Never replay an extended tongue from a different mouth pose.
            fresh=age<(1.0 if self.mode=='babble' else 3.0) and agreement<.24
            signal=result['tongue'] if fresh else 0.
            jaw=shapes.get('jawOpen',0);pout=shapes.get('mouthPucker',0)
            if pout>.35 and jaw<.18:signal*=.12
            if jaw<.025 and geometry<.08:signal=0.
            observation.tongue_out=max(geometry*.35,float(np.clip((signal-.18)/.65,0,1)))
            if fresh and self.mode=='siglip' and result.get('label')=='pout' and jaw<.15:
                # A pushed lower lip is its own motion, never tongue evidence.
                shapes['mouthShrugLower']=max(shapes.get('mouthShrugLower',0),.55)
            if not fresh:status['state']='stale'
        else:observation.tongue_out=geometry*.35
        return status

if __name__=='__main__':prepare_prompts()
