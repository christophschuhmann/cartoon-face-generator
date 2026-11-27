"""Start the local-model TLS gateway, without printing secrets."""
import json,os,socket,subprocess,sys,time
from pathlib import Path

root=Path(__file__).resolve().parent
private=Path.home()/'.config/robby-api'
for name in ('token','server.key','server.crt'):
    if not (private/name).is_file():raise SystemExit('Missing gateway credential: '+str(private/name))
with socket.socket() as s:
    if s.connect_ex(('127.0.0.1',18830))==0:raise SystemExit('Port 18830 already in use')
(root/'logs').mkdir(exist_ok=True);(root/'.runtime').mkdir(exist_ok=True)
cmd=[sys.executable,'-m','uvicorn','openai_gateway:app','--host','0.0.0.0','--port','18830',
     '--ssl-keyfile',str(private/'server.key'),'--ssl-certfile',str(private/'server.crt'),'--no-access-log']
with (root/'logs/openai-gateway.log').open('ab') as log:
    process=subprocess.Popen(cmd,cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
(root/'.runtime/openai-gateway.json').write_text(json.dumps({'pid':process.pid,'port':18830,'started':time.time()}))
print('Gateway starting on HTTPS port 18830; PID',process.pid)
