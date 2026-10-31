"""Request-scoped lab jobs: short HTTP polls, bounded in-memory retention."""
import asyncio,secrets,time
import httpx
from aiohttp import web

jobs={}
TTL=600
MAX_JOBS=4

def expire():
 now=time.monotonic()
 for token,job in list(jobs.items()):
  if job.get('finished') and now-job['finished']>=TTL:jobs.pop(token,None)

async def run_job(job,body,content_type):
 try:
  async with httpx.AsyncClient(timeout=httpx.Timeout(3600.,connect=10.)) as client:
   response=await client.post('http://127.0.0.1:8810/analyze',content=body,headers={'Content-Type':content_type})
  if response.status_code==200:job.update(state='done',content=response.content)
  else:job.update(state='failed',error=response.text[:300])
 except asyncio.CancelledError:
  job.update(state='failed',error='Analysis stopped because the server restarted.')
  raise
 except httpx.HTTPError:
  job.update(state='failed',error='The audio/video analysis service did not respond.')
 finally:
  job['finished']=time.monotonic()
  asyncio.get_running_loop().call_later(TTL,expire)

async def start(request):
 if not request.content_type.startswith('multipart/'):
  raise web.HTTPUnsupportedMediaType(text='Expected a recording upload')
 expire()
 if any(j['state']=='running' for j in jobs.values()):raise web.HTTPConflict(text='Another analysis is running; please retry when it finishes.')
 if len(jobs)>=MAX_JOBS:raise web.HTTPTooManyRequests(text='Too many recent analyses; please try again shortly.')
 body=await request.read()
 if len(body)>25*1024*1024:raise web.HTTPRequestEntityTooLarge(max_size=25*1024*1024,actual_size=len(body))
 if any(j['state']=='running' for j in jobs.values()):raise web.HTTPConflict(text='Another analysis is running; please retry when it finishes.')
 token=secrets.token_urlsafe(32);job={'state':'running','started':time.monotonic()};jobs[token]=job
 task=asyncio.create_task(run_job(job,body,request.headers['Content-Type']))
 job['task']=task
 task.add_done_callback(lambda _:job.pop('task',None))
 return web.json_response({'job_id':token,'state':'running'},status=202,headers={'Cache-Control':'no-store'})

async def status(request):
 expire();job=jobs.get(request.headers.get('X-Lab-Token',''))
 if job is None:raise web.HTTPNotFound(text='Analysis not found or expired; please start it again.')
 headers={'Cache-Control':'no-store'}
 if job['state']=='done':return web.Response(body=job['content'],content_type='application/json',headers=headers)
 if job['state']=='failed':return web.json_response({'state':'failed','error':job['error']},headers=headers)
 return web.json_response({'state':'running','elapsed_s':round(time.monotonic()-job['started'],1)},headers=headers)

async def delete(request):
 token=request.headers.get('X-Lab-Token','');job=jobs.get(token)
 if job and job['state']!='running':jobs.pop(token,None)
 return web.Response(status=204,headers={'Cache-Control':'no-store'})
