"""Forty LAION Small/Large regressors with the matching SigLIP2 vision encoder.

Inference runs in a separate, single-threaded CPU process. Queues contain at most
one face crop/result. No images or embeddings are written during webcam use.
"""
import json
import math
import multiprocessing as mp
from pathlib import Path
import queue
import time
import numpy as np
from PIL import Image

MODEL_DIR = Path(__file__).parent / 'models/empathic'
ALIASES = {'astonishment_surprise':'surprise','emotional_numbness':'numbness',
           'fatigue_exhaustion':'fatigue','hope_enthusiasm_optimism':'hope',
           'impatience_and_irritability':'impatience','intoxication_altered_states_of_consciousness':'intoxication',
           'jealousy_&_envy':'envy','malevolence_malice':'malice','sexual_lust':'lust',
           'thankfulness_gratitude':'gratitude'}


EXTRA_HEADS = {'arousal', 'dominance', 'emotional_vulnerability', 'valence'}


def head_directory(variant):
    if variant not in ('small', 'large'): raise ValueError('Unknown Empathic variant')
    return MODEL_DIR/'small' if variant == 'small' else MODEL_DIR


def encoder_path():
    # Weight-only Q4 reproduced the author's examples substantially better
    # than dynamic INT8, whose faster runtime changed negative expressions.
    q4 = MODEL_DIR/'vision_q4.onnx'
    return q4 if q4.is_file() else MODEL_DIR/'vision_cpu_int8.onnx'


def model_ready(variant='small'):
    return encoder_path().is_file() and (head_directory(variant)/'numpy_heads.json').is_file()


def convert_heads(variant='small'):
    """One-time, weights-only conversion. Runtime does not import PyTorch."""
    import torch
    from threadpoolctl import threadpool_limits
    torch.set_num_threads(1)
    root = head_directory(variant)
    source = json.loads((root/'source.json').read_text())
    stats = json.loads((root/'neutral_stats.json').read_text())
    output = root/'numpy_heads'
    output.mkdir(exist_ok=True)
    manifest = {}
    rng = np.random.default_rng(99)
    test = rng.normal(size=1152).astype(np.float32); test /= np.linalg.norm(test)
    with threadpool_limits(limits=1):
        for filename in source['heads']:
            key = filename.removesuffix('.pth')
            raw = key.removeprefix('model_').removesuffix('_best')
            if raw in EXTRA_HEADS: continue
            slug = ALIASES.get(raw,raw)
            state = torch.load(root/'heads'/filename, map_location='cpu', weights_only=True)
            indices = sorted(int(k.split('.')[1]) for k in state if k.endswith('.weight'))
            files = []
            a, b = test.copy(), torch.from_numpy(test.copy())
            for layer in indices:
                weight = state[f'layers.{layer}.weight'].numpy()
                bias = state[f'layers.{layer}.bias'].numpy()
                stem = f'{slug}_{layer}'
                np.save(output/(stem+'_weight.npy'),weight,allow_pickle=False)
                np.save(output/(stem+'_bias.npy'),bias,allow_pickle=False)
                files.append(stem)
                a = weight @ a + bias
                b = torch.nn.functional.linear(b, state[f'layers.{layer}.weight'],state[f'layers.{layer}.bias'])
                if layer != indices[-1]: a = np.maximum(a,0); b = torch.relu(b)
            np.testing.assert_allclose(a,b.numpy(),atol=1e-5,rtol=1e-5)
            manifest[slug] = {'layers':files, 'mean':stats[key]['mean'], 'std':stats[key]['std']}
            print('Converted and checked:',slug,flush=True)
    if len(manifest)!=40: raise ValueError('Incomplete head set')
    (root/'numpy_heads.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')


class HeadBank:
    def __init__(self, variant='small'):
        self.variant = variant
        root = head_directory(variant)
        manifest = json.loads((root/'numpy_heads.json').read_text())
        if len(manifest) != 40: raise ValueError('Expected forty emotion heads')
        self.heads = {}
        for slug,item in manifest.items():
            layers = [(np.load(root/'numpy_heads'/(stem+'_weight.npy'),mmap_mode='r',allow_pickle=False),
                       np.load(root/'numpy_heads'/(stem+'_bias.npy'),mmap_mode='r',allow_pickle=False)) for stem in item['layers']]
            self.heads[slug] = (layers,item['mean'],max(item['std'],.25))

    def infer(self, embedding):
        embedding = np.asarray(embedding, dtype=np.float32)
        if embedding.shape != (1152,) or not np.isfinite(embedding).all(): raise ValueError('Invalid embedding')
        scores = {}
        for slug,(layers,mean,std) in self.heads.items():
            value = embedding
            for index,(weight,bias) in enumerate(layers):
                value = weight @ value + bias
                if index < len(layers)-1: value = np.maximum(value,0)
            raw = float(value[0])
            scores[slug] = {'raw':raw,'adjusted':raw-mean,'standardized':(raw-mean)/std,'std':std}
        if not all(math.isfinite(s['raw']) for s in scores.values()): raise ValueError('Nonfinite emotion score')
        return scores


class EmpathicModel:
    def __init__(self, variant='small', encoder=None):
        import onnxruntime as ort
        from threadpoolctl import threadpool_limits
        self.thread_limit = threadpool_limits(limits=1)
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_cpu_mem_arena = False
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.encoder = ort.InferenceSession(str(encoder or encoder_path()), options, providers=['CPUExecutionProvider'])
        self.input_name = self.encoder.get_inputs()[0].name
        outputs = self.encoder.get_outputs()
        self.output_name = next((x.name for x in outputs if 'embed' in x.name), outputs[-1].name)
        self.bank = HeadBank(variant)

    def infer(self, rgb):
        started = time.perf_counter()
        image = Image.fromarray(rgb).resize((384,384),Image.Resampling.BILINEAR)
        tensor = (np.asarray(image,dtype=np.float32)/127.5-1).transpose(2,0,1)[None]
        embedding = self.encoder.run([self.output_name],{self.input_name:np.ascontiguousarray(tensor)})[0].reshape(-1)
        if embedding.shape != (1152,): raise ValueError('Wrong SigLIP embedding: '+str(embedding.shape))
        embedding = embedding / max(float(np.linalg.norm(embedding)),1e-8)
        encoder_ms = (time.perf_counter()-started)*1000
        scores = self.bank.infer(embedding)
        return {'scores':scores,'embedding':embedding.tolist(),'variant':self.bank.variant,
                'encoder_ms':round(encoder_ms,1),'inference_ms':round((time.perf_counter()-started)*1000,1)}


def put_latest(channel, item):
    try: channel.put_nowait(item); return True
    except queue.Full: pass
    try: channel.get_nowait()
    except queue.Empty: pass
    try: channel.put_nowait(item); return True
    except queue.Full: return False


def worker_main(incoming, outgoing, variant):
    try:
        # Windows can terminate the Flask parent without running its finally
        # block. Ensure an expensive orphan inference cannot survive it.
        import os
        import threading
        parent = mp.parent_process()
        if parent is not None:
            def watch_parent():
                while parent.is_alive(): time.sleep(1)
                os._exit(0)
            threading.Thread(target=watch_parent,daemon=True).start()
        try:
            import psutil
            process=psutil.Process()
            # Below-normal priority starves on this dual-core laptop while the
            # browser animates. One normal-priority inference thread progresses
            # fairly alongside tracking; it never blocks the frame request.
            process.nice(psutil.NORMAL_PRIORITY_CLASS)
        except (ImportError,AttributeError,OSError): pass
        model = EmpathicModel(variant)
        put_latest(outgoing,{'state':'ready'})
        while True:
            item = incoming.get()
            if item is None: break
            rgb,captured,generation,signature = item
            result = model.infer(rgb)
            result.pop('embedding', None)
            result['signature'] = signature
            result.update(state='active',captured=captured,completed=time.monotonic(),generation=generation)
            put_latest(outgoing,result)
    except Exception as error: put_latest(outgoing,{'state':'error','error':str(error)})


class EmpathicWorker:
    def __init__(self, variant='small'):
        self.variant = variant
        self.process = self.incoming = self.outgoing = None
        self.result = None
        self.generation = 0
        self.last_submit = -math.inf
        self.state = 'ready' if model_ready(variant) else 'not_installed'
        self.error = None
        self.neutral = None
        self.calibrate_after = None
        self.calibration_queued = False

    def start(self):
        if self.process is not None or not model_ready(self.variant): return
        context=mp.get_context('spawn')
        self.incoming,self.outgoing=context.Queue(1),context.Queue(1)
        self.process=context.Process(target=worker_main,args=(self.incoming,self.outgoing,self.variant),daemon=True,name='Empathic-40-CPU')
        self.process.start()
        self.state='loading'

    def submit(self,rgb,observation,signature=None):
        now=time.monotonic()
        if rgb is None or observation is None or len(observation.landmarks)<468:return
        # Preserve the actual neutral frame, even if the encoder is still busy.
        # Otherwise latest-frame replacement would calibrate a different face
        # expression tens of seconds after the user pressed the button.
        if self.calibration_queued:return
        if self.calibrate_after is None and now-self.last_submit<1.2:return
        self.start()
        if self.process is None:return
        q=np.asarray(observation.landmarks)[:,:2]*[observation.width,observation.height]
        lo,hi=q.min(axis=0),q.max(axis=0)
        center=(lo+hi)/2;size=float(max(hi-lo))*1.25
        if not np.isfinite(size) or size<48:return
        h,w=rgb.shape[:2]
        left,top=np.maximum([0,0],center-size/2).astype(int)
        right,bottom=np.minimum([w,h],center+size/2).astype(int)
        if right<=left or bottom<=top:return
        crop=np.asarray(Image.fromarray(rgb[top:bottom,left:right]).resize((384,384),Image.Resampling.BILINEAR))
        submitted=put_latest(self.incoming,(crop,now,self.generation,signature))
        if submitted and self.calibrate_after is not None:self.calibration_queued=True
        self.last_submit=now

    def snapshot(self):
        if self.outgoing:
            while True:
                try: item=self.outgoing.get_nowait()
                except queue.Empty: break
                if item.get('state')=='active' and item.get('generation')!=self.generation: continue
                self.state=item['state']
                if self.state=='error':self.error=item['error']
                if item.get('generation')==self.generation:
                    self.result=item
                    if self.calibrate_after is not None and item['captured']>=self.calibrate_after:
                        self.neutral={slug:score['raw'] for slug,score in item['scores'].items()}
                        self.calibrate_after=None
                        self.calibration_queued=False
        if self.process and not self.process.is_alive() and self.state!='error':
            self.state='error';self.error='Der 40-Kategorien-Prozess wurde beendet.'
        if self.result:
            age=time.monotonic()-self.result['captured']
            if age < max(6.,self.result['inference_ms']/1000*2.5):
                result=dict(self.result)
                result['age_seconds']=round(age,1)
                if self.neutral:
                    result['scores']={slug:{**s,'adjusted':s['raw']-self.neutral[slug],
                                           'standardized':(s['raw']-self.neutral[slug])/s['std']}
                                      for slug,s in self.result['scores'].items()}
                return result
        return None

    def calibrate(self):
        self.calibrate_after=time.monotonic()
        self.calibration_queued=False

    def clear(self):
        self.generation+=1
        self.result=None
        self.calibrate_after=None
        self.calibration_queued=False
        if self.incoming:
            try:self.incoming.get_nowait()
            except queue.Empty:pass

    def close(self):
        self.clear()
        if self.process:
            self.process.terminate();self.process.join(timeout=3)
            self.incoming.close();self.outgoing.close()
        self.process=self.incoming=self.outgoing=None
        self.state='ready' if model_ready(self.variant) else 'not_installed'
        self.error=None

    def set_variant(self, variant):
        head_directory(variant)
        if variant != self.variant:
            self.close()
            self.variant=variant
            self.neutral=None
            self.state='ready' if model_ready(variant) else 'not_installed'


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--convert',action='store_true')
    parser.add_argument('--benchmark',type=Path)
    parser.add_argument('--variant',choices=('small','large'),default='small')
    args=parser.parse_args()
    if args.convert:convert_heads(args.variant)
    if args.benchmark:
        model=EmpathicModel(args.variant)
        result=model.infer(np.asarray(Image.open(args.benchmark).convert('RGB')))
        result.pop('embedding')
        print(json.dumps(result,indent=2),flush=True)
