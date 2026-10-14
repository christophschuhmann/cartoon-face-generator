"""Download pinned official weights without persisting access credentials.

Already-authorized gated-model access is required. This script never accepts a
license on someone's behalf, logs a token, or calls `huggingface_hub.login`.
"""
from pathlib import Path
import argparse,getpass,json,time
from huggingface_hub import hf_hub_download

ROOT=Path(__file__).resolve().parent
REVISION='49b093a39c19169a8a81721dcc541e07e945232f'
DISTILLED_FILES=[
 'diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors',
 'text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors',
 'vae/ltx-2.5-video-vae-conv-bf16.safetensors',
 'vae/ltx-2.5-audio-vae-bf16.safetensors',
 'latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors']
LORA_FILES=[
 'diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors',
 'loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors']

def download(with_lora=False):
    token=getpass.getpass('Hugging Face read token (not saved): ')
    destination=ROOT/'models/LTX-2.5';start=time.perf_counter();rows=[]
    for filename in DISTILLED_FILES+(LORA_FILES if with_lora else []):
        path=Path(hf_hub_download('Lightricks/LTX-2.5',filename,revision=REVISION,
             local_dir=destination,token=token))
        rows.append({'file':filename,'bytes':path.stat().st_size})
    token=None
    report={'repository':'Lightricks/LTX-2.5','revision':REVISION,'files':rows,
        'download_seconds':time.perf_counter()-start,'total_bytes':sum(row['bytes'] for row in rows),
        'credentials_saved':False}
    (ROOT/'download_latest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--with-lora',action='store_true')
    download(parser.parse_args().with_lora)
