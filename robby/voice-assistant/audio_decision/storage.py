"""Capability-owned private cache. No upload/result is served as a public static file."""
import hashlib,json,os,secrets,shutil,time
from pathlib import Path
from .engine import ASSETS,MODEL,REVISION,PROMPT_VERSION

ROOT=ASSETS/'private';ROOT.mkdir(parents=True,exist_ok=True);ROOT.chmod(0o700)
TTL=3600;MAX_BYTES=1024**3
def owner_key(token):return hashlib.sha256(token.encode()).hexdigest()
def directory(owner,identifier):
    if not identifier or len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):raise FileNotFoundError
    p=ROOT/owner/identifier
    if not p.exists():raise FileNotFoundError
    return p
def create(owner):
    identifier=secrets.token_hex(16);p=ROOT/owner/identifier;p.mkdir(parents=True);p.chmod(0o700)
    return identifier,p
def write(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False));os.chmod(tmp,0o600);tmp.replace(path)
def key(audio_sha,config):
    return hashlib.sha256(json.dumps({'audio':audio_sha,'config':config,'model':MODEL,'revision':REVISION,'prompt':PROMPT_VERSION},sort_keys=True).encode()).hexdigest()
def expire(protected=()):
    now=time.time();entries=[]
    for p in ROOT.glob('*/*'):
        if not p.is_dir() or p.name in protected:continue
        files=list(p.glob('*'));size=sum(f.stat().st_size for f in files if f.is_file());mtime=max([f.stat().st_mtime for f in files]+[p.stat().st_mtime])
        if now-mtime>TTL:shutil.rmtree(p)
        else:entries.append((mtime,size,p))
    size=sum(x[1] for x in entries)
    for _,n,p in sorted(entries):
        if size<=MAX_BYTES:break
        shutil.rmtree(p);size-=n
