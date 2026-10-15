"""Checksummed HTTP range downloads for unreliable connections. Project-local only."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import urllib.request
import time
import os
import subprocess

def download(url,path,size,sha256=None,git_blob=None,workers=8):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    def valid(p):
        if not p.is_file() or p.stat().st_size!=size:return False
        data=p.read_bytes()
        return (not sha256 or hashlib.sha256(data).hexdigest()==sha256) and (not git_blob or hashlib.sha1(f'blob {size}\0'.encode()+data).hexdigest()==git_blob)
    if valid(path):return
    parts=path.with_name(path.name+'.chunks');parts.mkdir(exist_ok=True)
    block=512*1024
    def get(index):
        start=index*block;end=min(size,start+block)-1;target=parts/str(index)
        if target.is_file() and target.stat().st_size==end-start+1:return
        for attempt in range(8):
            try:
                address=url+('&' if '?' in url else '?')+f'chunk={index}'
                if os.name=='nt':
                    # Windows' native TLS transport avoids stalled OpenSSL
                    # connections observed on this machine. Still verify bytes.
                    tmp=target.with_suffix('.tmp');header=target.with_suffix('.headers')
                    subprocess.run(['curl.exe','-sS','-L','--fail','--ssl-revoke-best-effort','--connect-timeout','10','--max-time','45',
                        '--range',f'{start}-{end}','-D',str(header),'-o',str(tmp),address],check=True,capture_output=True)
                    if f'content-range: bytes {start}-{end}/{size}' not in header.read_text().lower():
                        raise ValueError('Unexpected HTTP range response')
                    data=tmp.read_bytes();header.unlink(missing_ok=True)
                else:
                    req=urllib.request.Request(address,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity','Connection':'close'})
                    with urllib.request.urlopen(req,timeout=25) as response:
                        if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{size}':raise ValueError('Unexpected HTTP range response')
                        data=response.read(end-start+1)
                if len(data)!=end-start+1:raise ValueError('Incomplete range')
                tmp=target.with_suffix('.tmp');tmp.write_bytes(data);tmp.replace(target);return
            except Exception:
                if attempt==7:raise
                time.sleep(min(2,.3*(attempt+1)))
    count=(size+block-1)//block
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(get,i) for i in range(count)]
        for done,future in enumerate(as_completed(futures),1):
            future.result()
            if done%20==0 or done==count:print(path.name,f'{done}/{count}',flush=True)
    temporary=path.with_name(path.name+'.assembled')
    with temporary.open('wb') as dest:
        for i in range(count):dest.write((parts/str(i)).read_bytes())
    if not valid(temporary):raise ValueError('Checksum mismatch: '+str(path))
    temporary.replace(path)
    for i in range(count):(parts/str(i)).unlink()
    for temporary in parts.glob('*.headers'):temporary.unlink()
    parts.rmdir()
    print('VERIFIED',path.name,size,flush=True)

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);a=p.parse_args()
    for row in json.loads(a.manifest.read_text()):download(**row)

if __name__=='__main__':main()
