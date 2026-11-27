#!/usr/bin/env python3
"""Start the explicitly local Gemma 4 26B Robby backend (no cloud fallbacks)."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
MODEL_ROOT=Path(os.environ.get('ROBO_GEMMA26_DIR','/dev/shm/robby-gemma'))
MODEL=MODEL_ROOT/'model/gemma-4-26B_q4_0-it.gguf'
DRAFT=MODEL_ROOT/'qat-mtp/mtp-gemma-4-26B-A4B-it.gguf'
MODEL_REPO='google/gemma-4-26B-A4B-it-qat-q4_0-gguf'
MODEL_REV='d1c082be9cf3c8a514acf63b8761f4b41935842e'
DRAFT_REPO='unsloth/gemma-4-26B-A4B-it-qat-GGUF'
DRAFT_REV='7b92b5b28818151e8669af2e45e88d6086f490dd'


def download(drafts):
    MODEL_ROOT.mkdir(parents=True,exist_ok=True)
    required=(0 if MODEL.exists() else 14439363584)+(0 if not drafts or DRAFT.exists() else 251939328)
    if shutil.disk_usage(MODEL_ROOT).free<required+1024**3:
        raise RuntimeError('Insufficient free space for Gemma weights plus 1 GiB working margin')
    os.environ.setdefault('HF_HOME',str(MODEL_ROOT/'cache'))
    os.environ.setdefault('HF_HUB_DISABLE_XET','1')
    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT','120')
    from huggingface_hub import hf_hub_download
    if not MODEL.exists():hf_hub_download(repo_id=MODEL_REPO,revision=MODEL_REV,filename=MODEL.name,local_dir=MODEL.parent)
    if drafts and not DRAFT.exists():hf_hub_download(repo_id=DRAFT_REPO,revision=DRAFT_REV,filename=DRAFT.name,local_dir=DRAFT.parent)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--download',action='store_true',help='download pinned weights if absent')
    p.add_argument('--drafts',type=int,choices=range(4),default=1,help='MTP drafts; 0 disables MTP')
    p.add_argument('--gpu',type=int,default=1,help='physical CUDA GPU (default 1)')
    p.add_argument('--context',type=int,default=8192)
    p.add_argument('--engine',default=os.environ.get('ROBO_GEMMA_LLAMA_SERVER','/home/c4r33u19/moss15v2/llama.cpp/build/bin/llama-server'))
    a=p.parse_args()
    if a.download:download(a.drafts)
    if not MODEL.is_file() or (a.drafts and not DRAFT.is_file()):
        p.error('Weights missing. Use --download; default model directory is temporary /dev/shm.')
    if not Path(a.engine).is_file():p.error('llama-server not found; use --engine or ROBO_GEMMA_LLAMA_SERVER')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',18826))==0:p.error('Port 18826 is already in use; no process was stopped')
    cmd=[a.engine,'-m',str(MODEL),'--alias','gemma-4-26b-a4b-q4','--host','127.0.0.1','--port','18826',
         '--device','CUDA0','--fit','off','-ngl','all','-c',str(a.context),'-np','1','-fa','on',
         '-ctk','q8_0','-ctv','q8_0','-b','512','-ub','256','--jinja','--no-mmproj',
         '--cors-origins','http://localhost:8793','--no-cors-credentials','-t','8']
    if a.drafts:cmd+=['--spec-type','draft-mtp','-md',str(DRAFT),'--spec-draft-n-max',str(a.drafts),'--spec-draft-ngl','all']
    env=os.environ.copy();env['CUDA_VISIBLE_DEVICES']=str(a.gpu)
    (ROOT/'logs').mkdir(exist_ok=True);(ROOT/'.runtime').mkdir(exist_ok=True)
    with (ROOT/'logs/gemma26-server.log').open('ab') as out:
        proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True)
    (ROOT/'.runtime/gemma26.json').write_text(json.dumps({'pid':proc.pid,'gpu':a.gpu,'port':18826,'drafts':a.drafts,'context':a.context,'model':str(MODEL),'engine':a.engine,'started':time.time()}))
    print(f'Gemma server started on 127.0.0.1:18826 (PID {proc.pid}); check /health and logs/gemma26-server.log.')

if __name__=='__main__':main()
