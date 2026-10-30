import contextlib,json,time,sys,torch,numpy as np,soundfile as sf
from pathlib import Path
from scipy.signal import resample_poly
from nets.model_wrapper import SeparationModel
from utils.config import yaml_to_parser
from utils.average_model_params import average_model_params
root=Path('/mnt/nvme/moss-15-v2/robo-integration/vendor/tuss/pretrained_models/tuss.medium.2-4src');torch.set_num_threads(4)
h=yaml_to_parser(root/'hparams.yaml').parse_args([]);m=SeparationModel(h.encoder_name,h.encoder_conf,h.decoder_name,h.decoder_conf,h.model_name,h.model_conf,h.css_conf,h.variance_normalization)
with contextlib.redirect_stdout(sys.stderr):sd=average_model_params([root/'checkpoints/model.pth'])
m.load_state_dict({k.replace('model.',''):v for k,v in sd.items()});m.eval();y,sr=sf.read('/mnt/nvme/moss-15-v2/robo-integration/.runtime/lfm3-tests/speech-music.wav',dtype='float32');y=resample_poly(y,48000,sr).astype('float32');x=torch.from_numpy(y).unsqueeze(0);t=time.perf_counter()
with torch.inference_mode():cpu=m(x.clone(),[['speech','sfxbg','musicbg']])[0]
cpu_ms=(time.perf_counter()-t)*1000;free_before=torch.cuda.mem_get_info()[0];t=time.perf_counter();m=m.to('cuda:0');x=x.to('cuda:0');torch.cuda.synchronize();load_ms=(time.perf_counter()-t)*1000;torch.cuda.reset_peak_memory_stats();times=[]
with torch.inference_mode():
 for i in range(6):
  t=time.perf_counter();pred=m(x.clone(),[['speech','sfxbg','musicbg']])[0];torch.cuda.synchronize();times.append(round((time.perf_counter()-t)*1000,1))
 result=pred.cpu();err=(result-cpu).square().mean().sqrt().item();rms=cpu.square().mean().sqrt().item();t=time.perf_counter();speech=pred[0:1].clone();out=m(speech,[['speech','speech']])[0];torch.cuda.synchronize();split_ms=(time.perf_counter()-t)*1000
print(json.dumps({'audio_s':round(len(y)/48000,3),'cpu_ms':round(cpu_ms,1),'gpu_first_and_warm_ms':times,'gpu_load_ms':round(load_ms,1),'two_speaker_gpu_ms':round(split_ms,1),'output_shape':list(result.shape),'gpu_vs_cpu_relative_rms_error':round(err/(rms+1e-12),6),'gpu_peak_allocated_mb':round(torch.cuda.max_memory_allocated()/1048576,1),'gpu_free_before_mb':round(free_before/1048576,1)},ensure_ascii=False),flush=True)
