"""Single-owner CUDA admission and bounded local IPC; safe to import in GPU0 Robby."""
import asyncio
from multiprocessing import Pipe
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parent
_owner=None


class IsolationBusy(RuntimeError):pass


class GPUWorker:
    def __init__(self,gpu=None):
        self.gpu=str(gpu or os.environ.get('ROBO_ISOLATION_GPU','1'))
        self.process=None;self.conn=None;self.lock=threading.Lock();self.closed=threading.Event()

    def start(self):
        if self.closed.is_set():raise RuntimeError('Filter startup cancelled')
        # Preserve room for existing services. This does not reserve memory for
        # other users; the child's allocator is separately bounded at 16%.
        free=subprocess.check_output(['nvidia-smi','--id='+self.gpu,'--query-gpu=memory.free',
                                     '--format=csv,noheader,nounits'],text=True,timeout=5)
        if int(free.strip())<4096:raise RuntimeError('Insufficient free GPU memory')
        parent,child=Pipe(duplex=True)
        env={**os.environ,'CUDA_VISIBLE_DEVICES':self.gpu,'OMP_NUM_THREADS':'2',
             'HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1'}
        # Child does not need any credentials. Never send audio or voiceprints to a log.
        env={k:v for k,v in env.items() if not any(s in k.upper() for s in ('TOKEN','API_KEY','SECRET','PASSWORD'))}
        env['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
        try:
            self.process=subprocess.Popen([sys.executable,'-u',str(ROOT/'input_isolation_worker.py'),
                '--fd',str(child.fileno())],cwd=ROOT,env=env,pass_fds=(child.fileno(),),
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.conn=parent
            if self.closed.is_set():self.close();raise RuntimeError('Filter startup cancelled')
        except Exception:parent.close();raise
        finally:child.close()

    def request(self,message,timeout=1.):
        with self.lock:
            if self.process is None or self.process.poll() is not None:raise RuntimeError('Filter worker unavailable')
            self.conn.send(message)
            if not self.conn.poll(timeout):raise TimeoutError('Filter inference deadline exceeded')
            result=self.conn.recv()
            if not result.get('ok'):raise RuntimeError('Filter '+result.get('operation','')+' failed: '+result.get('error','unknown'))
            return result

    def close(self):
        self.closed.set()
        # The handle belongs only to this worker; never kill unrelated GPU jobs.
        p=self.process
        if p is not None and p.poll() is None:
            p.terminate()
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
        if self.conn is not None:self.conn.close()


def reserve(worker):
    global _owner
    if _owner is not None and _owner is not worker:raise IsolationBusy('Another browser session is using the filter GPU')
    _owner=worker


def release(worker):
    global _owner
    if _owner is worker:_owner=None


async def close_worker(worker):
    if worker is None:return
    try:await asyncio.to_thread(worker.close)
    finally:release(worker)
