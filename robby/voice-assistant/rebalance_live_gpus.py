"""Move the currently owned Robby services to GPU 0; never touch Podcast.

Operational utility for this machine. Existing credentials are inherited directly
from each process in memory, never printed or written. Re-run only with current,
explicit PID arguments after checking that no Robby generation is active.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parent

def get(port, path):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=10) as r:
        return json.load(r)

def capture(pid, marker):
    proc = Path(f'/proc/{pid}')
    argv = [x.decode() for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
    if not any(marker in x for x in argv):
        raise RuntimeError(f'PID {pid} does not match expected service {marker}')
    env = dict(x.decode().split('=', 1) for x in (proc/'environ').read_bytes().split(b'\0') if b'=' in x)
    return {'pid': pid, 'argv': argv, 'env': env, 'cwd': str((proc/'cwd').resolve())}

def restart(label, record, updates, cpu_llm=False):
    args = record['argv'][:]
    if cpu_llm:
        args[args.index('-ngl')+1] = '0'
    os.kill(record['pid'], signal.SIGTERM)
    deadline = time.monotonic()+40
    while Path(f'/proc/{record["pid"]}').exists() and time.monotonic()<deadline:
        time.sleep(.25)
    if Path(f'/proc/{record["pid"]}').exists():
        raise RuntimeError(f'{label} has not stopped; leaving other services untouched')
    path = ROOT/'logs'/f'{label}-gpu-split.log'
    with path.open('ab') as log:
        child = subprocess.Popen(args, cwd=record['cwd'], env={**record['env'], **updates},
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    print(json.dumps({'service':label,'pid':child.pid,'log':str(path),'device':updates}), flush=True)
    return child.pid

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('tts','bolt','ears','diarization'):
        p.add_argument('--'+name, type=int, required=True)
    a=p.parse_args()
    if get(8792,'/api/state').get('busy') or get(8815,'/api/status').get('busy'):
        raise RuntimeError('Robby TTS or optional Decision lab is active; retry when idle')
    records={name:capture(getattr(a,name),marker) for name,marker in
             [('tts','small_app:app'),('bolt','llama-server'),('ears','voice_caption_worker.py'),('diarization','diarization_service.py')]}
    from optional_lab_gpu import Lease
    with Lease():
        request=urllib.request.Request('http://127.0.0.1:8815/internal/offload',data=b'',method='POST')
        with urllib.request.urlopen(request,timeout=45) as r:
            print('Idle Decision model offloaded: '+str(json.load(r)),flush=True)
        pids={}
        pids['bolt']=restart('bolt-cpu',records['bolt'],{'CUDA_VISIBLE_DEVICES':''},cpu_llm=True)
        pids['tts']=restart('tts-gpu0',records['tts'],{
            'ACTING_DEVICE':'cuda:0','SMALL_DEVICE':'cuda:0','SMALL_SCORE_DEVICE':'cuda:0',
            'SMALL_ALIGN_DEVICE':'cuda:0','SMALL_VC_DEVICE':'cuda:0'})
        pids['ears']=restart('ears-gpu0',records['ears'],{'ROBO_CAPTION_DEVICE':'cuda:0'})
        pids['diarization']=restart('diarization-gpu0',records['diarization'],{
            'CUDA_VISIBLE_DEVICES':'0','ROBO_DIARIZATION_DEVICE':'cuda'})
        receipt={'changed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'pids':pids,
                 'robby_gpu':0,'podcast_gpu':1,'podcast_untouched':True,
                 'optional_decision':'offloaded; service remains online','optional_bolt':'CPU',
                 'url':'https://diane-asylum-understood-invoice.trycloudflare.com/desk-robot/'}
        (ROOT/'logs/gpu-split-deployment.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print('Services started; readiness and generation still need verification.',flush=True)

if __name__=='__main__':main()
