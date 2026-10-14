"""Generate genuine LTX-2.5 videos with pinned models and measured phase timings.

The original MP4 is retained. Timings include lazy diffusion/decode when the video
iterator is drained by the encoder. Downloads and environment setup are separate.
"""
from pathlib import Path
from collections.abc import Iterator
import argparse,json,time,functools,platform,subprocess
import torch
from ltx_core.allocator_trim_strategy import AllocatorTrimStrategy
from ltx_core.loader.registry import ModelRegistry
from ltx_core.loader import LTXV_LORA_COMFY_RENAMING_MAP,LoraPathStrengthAndSDOps
from ltx_core.loader.primitives import StateDict
from ltx_core.model.video_vae import get_video_chunks_number
from ltx_pipelines.distilled import DistilledPipeline
from ltx_pipelines.utils.constants import DISTILLED_SIGMAS,STAGE_2_DISTILLED_SIGMAS
from ltx_pipelines.utils.model_paths import ModelPaths
from ltx_pipelines.utils.types import ImageConditioningInput
from ltx_pipelines.utils.media_io import encode_video

ROOT=Path(__file__).resolve().parent


class TimedBlock:
    def __init__(self,block,label,timings,device):
        self.block=block;self.label=label;self.timings=timings;self.device=device
    def __getattr__(self,name):return getattr(self.block,name)
    def __call__(self,*args,**kwargs):
        torch.cuda.synchronize(self.device);start=time.perf_counter()
        result=self.block(*args,**kwargs)
        if isinstance(result,Iterator):
            def drain():
                active=0.
                while True:
                    torch.cuda.synchronize(self.device);tick=time.perf_counter()
                    try:item=next(result)
                    except StopIteration:
                        active+=time.perf_counter()-tick;break
                    torch.cuda.synchronize(self.device);active+=time.perf_counter()-tick;yield item
                self.timings.setdefault(self.label,[]).append(active)
            return drain()
        torch.cuda.synchronize(self.device)
        self.timings.setdefault(self.label,[]).append(time.perf_counter()-start)
        return result


class CachedPrompt:
    """Keep identical prompt encodings between variants; preserve measured calls."""
    def __init__(self,encoder):self.encoder=encoder;self.cache={};self.hits=0
    def __getattr__(self,name):return getattr(self.encoder,name)
    def __call__(self,prompts,**kwargs):
        key=json.dumps([prompts,kwargs],sort_keys=True)
        if key not in self.cache:self.cache[key]=self.encoder(prompts,**kwargs)
        else:self.hits+=1
        return self.cache[key]


class CPUWeightRegistry(ModelRegistry):
    """Retain clean base tensors in RAM so LoRA fusion does not duplicate them in VRAM."""
    def add(self,paths,sd_ops,state_dict):
        retained=StateDict({key:value.to('cpu') for key,value in state_dict.sd.items()},
            torch.device('cpu'),state_dict.size,state_dict.dtype)
        return super().add(paths,sd_ops,retained)


def run(cases=None,device='cuda:0',mode='warm',model_kind='distilled',repeat=1):
    torch.set_num_threads(8)
    device=torch.device(device)
    torch.cuda.set_device(device)
    torch.cuda.init()
    model=ROOT/'models/LTX-2.5'
    paths=ModelPaths.from_split(
        transformer_path=str(model/f'diffusion_models/ltx-2.5-22b-{ "dev" if model_kind=="dev_lora" else "distilled" }-transformer-bf16.safetensors'),
        text_encoder_path=str(model/'text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors'),
        video_vae_path=str(model/'vae/ltx-2.5-video-vae-conv-bf16.safetensors'),
        audio_vae_path=str(model/'vae/ltx-2.5-audio-vae-bf16.safetensors'))
    registry=(CPUWeightRegistry(cache_weights=True,cache_models=True) if model_kind=='dev_lora' and mode=='warm'
              else ModelRegistry(cache_weights=mode=='warm',cache_models=True))
    setup=time.perf_counter()
    loras=[] if model_kind=='distilled' else [LoraPathStrengthAndSDOps(str(model/'loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors'),1.,LTXV_LORA_COMFY_RENAMING_MAP)]
    pipe=DistilledPipeline(paths,str(model/'latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors'),
        loras=loras,device=device,registry=registry,
        alloc_trim_strategy=AllocatorTrimStrategy.DEFER if mode=='warm' else AllocatorTrimStrategy.TRIM)
    pipeline_setup=time.perf_counter()-setup;timings={}
    for name in ['prompt_encoder','image_conditioner','stage','upsampler','video_decoder','audio_decoder']:
        setattr(pipe,name,TimedBlock(getattr(pipe,name),name,timings,device))
    if mode=='warm':pipe.prompt_encoder=CachedPrompt(pipe.prompt_encoder)
    definitions=[
        {'name':'01_happy_angry_start_only','pair':'happy_to_angry','anchors':'start','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'02_happy_angry_start_end','pair':'happy_to_angry','anchors':'ends','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'11_happy_angry_middle_warm','pair':'happy_to_angry','anchors':'middle','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'03_happy_angry_middle','pair':'happy_to_angry','anchors':'middle','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'04_happy_angry_faster_6_2','pair':'happy_to_angry','anchors':'middle','schedule':'6_2','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'05_happy_angry_fastest_4_2','pair':'happy_to_angry','anchors':'middle','schedule':'4_2','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'06_happy_angry_small','pair':'happy_to_angry','anchors':'middle','schedule':'8_3','width':768,'height':384,'frames':129,'seed':42},
        {'name':'07_sad_hopeful','pair':'sad_to_hopeful','anchors':'middle','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':43},
        {'name':'08_doubt_laughter','pair':'doubt_to_laughter','anchors':'ends','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':44},
        {'name':'09_fear_relief','pair':'fear_to_relief','anchors':'middle','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':45},
        {'name':'10_happy_angry_five_anchors','pair':'happy_to_angry','anchors':'five','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'12_happy_angry_dev_fast_lora','pair':'happy_to_angry','anchors':'middle','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'13_happy_angry_dev_fast_lora_warm','pair':'happy_to_angry','anchors':'middle','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'14_happy_angry_clear_margin','pair':'happy_to_angry_clear','anchors':'middle','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'15_happy_angry_clear_fast','pair':'happy_to_angry_clear','anchors':'middle','schedule':'4_2','width':1024,'height':512,'frames':129,'seed':42},
        {'name':'16_fear_relief_margin','pair':'fear_to_relief_margin','anchors':'five','schedule':'8_3','width':1024,'height':512,'frames':129,'seed':45}]
    if model_kind=='distilled':definitions=[case for case in definitions if int(case['name'][:2]) not in (12,13)]
    else:definitions=[case for case in definitions if int(case['name'][:2]) in (12,13)]
    if cases is not None:definitions=[case for case in definitions if int(case['name'][:2]) in cases]
    if repeat<1:raise ValueError('repeat must be positive')
    if repeat>1:
        definitions=[{**case,'name':f"{case['name']}_repeat{iteration:02d}",'repeat_index':iteration}
                     for case in definitions for iteration in range(1,repeat+1)]
    output=ROOT/'output';output.mkdir(exist_ok=True)
    generated=0
    for case in definitions:
        dest=output/case['name'];dest.mkdir(exist_ok=True)
        if (dest/'timing.json').exists():print('Already completed: '+case['name'],flush=True);continue
        source=ROOT/'inputs'/case['pair'];prompt=(source/'prompt.txt').read_text().strip();timings.clear()
        anchors=[ImageConditioningInput(str(source/'start.png'),0,1.,0)]
        if case['anchors'] in ('middle','five'):anchors.append(ImageConditioningInput(str(source/'middle.png'),64,.85,0))
        if case['anchors']=='five':
            anchors.extend([ImageConditioningInput(str(source/'quarter.png'),32,.8,0),ImageConditioningInput(str(source/'three_quarters.png'),96,.8,0)])
        if case['anchors']!='start':anchors.append(ImageConditioningInput(str(source/'end.png'),128,1.,0))
        stage1=DISTILLED_SIGMAS;stage2=STAGE_2_DISTILLED_SIGMAS
        if case['schedule']=='6_2':stage1=DISTILLED_SIGMAS[[0,2,4,5,6,7,8]];stage2=STAGE_2_DISTILLED_SIGMAS[[0,2,3]]
        if case['schedule']=='4_2':stage1=DISTILLED_SIGMAS[[0,3,5,7,8]];stage2=STAGE_2_DISTILLED_SIGMAS[[0,2,3]]
        serialized_anchors=[{**a._asdict(),'path':str(Path(a.path).relative_to(ROOT))} for a in anchors]
        (dest/'prompt.txt').write_text(prompt+'\n');(dest/'settings.json').write_text(json.dumps({**case,'anchors':serialized_anchors,
            'stage1_sigmas':stage1.tolist(),'stage2_sigmas':stage2.tolist(),'model_kind':model_kind,'lora_strength':1. if loras else None,
            'model_revision':'49b093a39c19169a8a81721dcc541e07e945232f'},indent=2)+'\n')
        torch.cuda.reset_peak_memory_stats(device);torch.cuda.synchronize(device);start=time.perf_counter()
        print('Generating '+case['name'],flush=True)
        with torch.inference_mode():
            result=pipe(prompt=prompt,seed=case['seed'],height=case['height'],width=case['width'],frame_rate=24.,
                images=anchors,num_frames=case['frames'],stage_1_sigmas=stage1,stage_2_sigmas=stage2)
            encode_video(result.video,24,result.audio,str(dest/'video.mp4'),get_video_chunks_number(result.num_frames,result.tiling_config),thread_count=4)
        torch.cuda.synchronize(device);elapsed=time.perf_counter()-start
        report={**case,'wall_seconds':elapsed,'video_seconds':result.num_frames/24,'wall_seconds_per_video_second':elapsed/(result.num_frames/24),
            'phase_seconds':{name:sum(values) for name,values in timings.items()},'phase_calls':{name:len(values) for name,values in timings.items()},
            'peak_allocated_gb':torch.cuda.max_memory_allocated(device)/1e9,'peak_reserved_gb':torch.cuda.max_memory_reserved(device)/1e9,
            'pipeline_setup_seconds':pipeline_setup,'cache_mode':mode,'prompt_cache_hits':getattr(pipe.prompt_encoder,'hits',0),
            'model_kind':model_kind,'torch':torch.__version__,'cuda':torch.version.cuda,
            'weight_cache_device':'cpu' if isinstance(registry,CPUWeightRegistry) else 'cuda' if mode=='warm' else 'none',
            'gpu':torch.cuda.get_device_name(device),'vendor_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'vendor/LTX-2',text=True).strip(),
            'denoise_updates':{'stage1':len(stage1)-1,'stage2':len(stage2)-1},'first_run_in_process':generated==0}
        (dest/'timing.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
        generated+=1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cases',type=int,nargs='+');parser.add_argument('--device',default='cuda:0')
    parser.add_argument('--mode',choices=['warm','cold'],default='warm');parser.add_argument('--model-kind',choices=['distilled','dev_lora'],default='distilled')
    parser.add_argument('--repeat',type=int,default=1)
    args=parser.parse_args();run(args.cases,args.device,args.mode,args.model_kind,args.repeat)
