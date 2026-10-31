"""Job API tests: keep a slow analysis alive across short HTTP polls."""
import asyncio,unittest
from unittest.mock import patch
from aiohttp import web,FormData
from aiohttp.test_utils import TestClient,TestServer
import lfm3_jobs as lab

class LabJobs(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  lab.jobs.clear();app=web.Application();app.router.add_post('/jobs',lab.start);app.router.add_get('/jobs',lab.status);app.router.add_delete('/jobs',lab.delete)
  self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):
  await self.client.close();lab.jobs.clear()
 def upload(self):
  data=FormData();data.add_field('media',b'test',filename='x.webm',content_type='video/webm');return data
 async def test_slow_job_poll_conflict_and_deletion(self):
  finish=asyncio.Event()
  async def slow(job,body,content_type):
   await finish.wait();job.update(state='done',content=b'{"segments":[]}',finished=lab.time.monotonic())
  with patch.object(lab,'run_job',slow):
   r=await self.client.post('/jobs',data=self.upload());self.assertEqual(r.status,202)
   token=(await r.json())['job_id'];self.assertGreater(len(token),30);headers={'X-Lab-Token':token}
   self.assertEqual((await (await self.client.get('/jobs',headers=headers)).json())['state'],'running')
   self.assertEqual((await self.client.post('/jobs',data=self.upload())).status,409)
   self.assertEqual((await self.client.get('/jobs')).status,404)
   finish.set();await asyncio.sleep(.01)
   r=await self.client.get('/jobs',headers=headers);self.assertEqual(await r.json(),{'segments':[]});self.assertEqual(r.headers['cache-control'],'no-store')
   await self.client.delete('/jobs',headers=headers);self.assertEqual((await self.client.get('/jobs',headers=headers)).status,404)
 async def test_invalid_upload_and_expiry(self):
  self.assertEqual((await self.client.post('/jobs',data=b'x')).status,415)
  lab.jobs['expired']={'state':'done','finished':lab.time.monotonic()-601}
  self.assertEqual((await self.client.get('/jobs',headers={'X-Lab-Token':'expired'})).status,404)
