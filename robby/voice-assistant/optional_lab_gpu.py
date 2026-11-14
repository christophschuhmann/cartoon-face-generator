"""Nonblocking, process-shared lease for optional research models on GPU 0.

Conversation, ASR, TTS and other users' processes never participate or get stopped.
Only the two optional labs may offload each other's idle model workers.
"""
import fcntl, os
from pathlib import Path

class OptionalLabBusy(RuntimeError):
    pass

class Lease:
    def __init__(self):
        self.fd=None
    def acquire(self):
        path=Path(os.getenv('ROBO_OPTIONAL_GPU_LOCK',str(Path.home()/'.cache/robby-optional-lab.lock')))
        path.parent.mkdir(parents=True,exist_ok=True)
        self.fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
        try:fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd);self.fd=None
            raise OptionalLabBusy('The other optional research lab is analyzing audio. Retry after it finishes.')
        return self
    def release(self):
        if self.fd is not None:
            fcntl.flock(self.fd,fcntl.LOCK_UN);os.close(self.fd);self.fd=None
    def __enter__(self):return self.acquire()
    def __exit__(self,*args):self.release()
