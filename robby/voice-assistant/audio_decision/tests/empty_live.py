"""Stopping before the first packet must not invent a zero-filled recording."""
import asyncio,json,requests,aiohttp
from pathlib import Path
async def main():
 base='http://127.0.0.1:8793';s=requests.Session();s.post(base+'/audio-decision/api/session',headers={'X-Audio-Decision':'1'}).raise_for_status()
 cookie='; '.join(k+'='+v for k,v in s.cookies.get_dict().items())
 async with aiohttp.ClientSession() as client,client.ws_connect(base+'/audio-decision/ws',headers={'Origin':base,'Cookie':cookie}) as ws:
  await ws.send_json({'settings':{'taxonomy':'classic','selected_ids':['/m/02fs_r']}})
  first=await ws.receive_json(timeout=20);assert first['type']=='started';await ws.send_json({'type':'stop'})
  final=await ws.receive_json(timeout=120);assert final['type']=='empty',final
 Path(__file__).with_name('empty-live-result.json').write_text(json.dumps({'passed':True,'result_type':final['type']}))
 print('Immediate stop: no audio or model scores invented')
asyncio.run(main())
