"""Start/status/stop only this loopback lab. Does not control Robby or its tunnel."""
import json,os,signal,subprocess,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parent.parent
ASSETS=Path(os.getenv('AUDIO_DECISION_ASSETS','/mnt/nvme/robby-audio-decision'))
PID=ASSETS/'service.pid';LOG=ASSETS/'service.log'
PYTHON=os.getenv('ROBBY_PYTHON','/home/c4r33u19/moss15v2/.venv/bin/python')
def owned():
 try:
  pid=int(PID.read_text());command=Path(f'/proc/{pid}/cmdline').read_bytes()
  return pid if b'audio_decision.service:app' in command else None
 except (FileNotFoundError,ValueError,ProcessLookupError):return None
command=sys.argv[1] if len(sys.argv)>1 else 'status'
if command=='restart':
 pid=owned()
 if pid:
  os.kill(pid,signal.SIGTERM)
  for _ in range(400):
   if not owned():break
   time.sleep(.1)
  else:raise SystemExit('Still shutting down; not starting a duplicate process')
 command='start'
if command=='start':
 if owned():print('Already running:',owned());sys.exit(0)
 env=os.environ.copy();env['PYTHONPATH']=str(ASSETS/'env')+':'+str(BASE);env['HF_HUB_OFFLINE']='1';env['TRANSFORMERS_OFFLINE']='1'
 with LOG.open('ab') as log:
  p=subprocess.Popen([PYTHON,'-m','uvicorn','audio_decision.service:app','--host','127.0.0.1','--port','8815','--no-access-log','--ws-max-size','64008'],cwd=BASE,env=env,stdout=log,stderr=log,start_new_session=True)
 PID.write_text(str(p.pid));LOG.chmod(0o600);print('Started loopback lab:',p.pid)
 import urllib.request
 for _ in range(90):
  if p.poll() is not None:raise SystemExit('Startup failed; inspect '+str(LOG))
  try:
   with urllib.request.urlopen('http://127.0.0.1:8815/api/status',timeout=1) as response:
    if response.status==200:print('HTTP service ready');break
  except Exception:time.sleep(1)
 else:raise SystemExit('Readiness timed out; inspect '+str(LOG))
elif command=='stop':
 pid=owned()
 if pid:os.kill(pid,signal.SIGTERM);print('Requested graceful shutdown:',pid)
 else:print('Not running')
elif command=='status':print('Running PID '+str(owned()) if owned() else 'Not running')
else:raise SystemExit('Use start, restart, stop, or status')
