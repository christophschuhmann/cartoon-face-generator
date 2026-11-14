"""Additive aiohttp routes for the existing Robby/Cloudflare origin."""
import asyncio
import aiohttp
from aiohttp import web

UPSTREAM='http://127.0.0.1:8815'
async def redirect(request):raise web.HTTPTemporaryRedirect('/audio-decision/')
async def proxy(request):
    path=request.match_info['path']
    if path.startswith('internal') or '..' in path or '\\' in path:raise web.HTTPNotFound()
    chunks=[];size=0
    async for chunk in request.content.iter_chunked(65536):
        size+=len(chunk)
        if size>32*1024**2:raise web.HTTPRequestEntityTooLarge(max_size=32*1024**2,actual_size=size)
        chunks.append(chunk)
    headers={k:v for k,v in request.headers.items() if k.lower() in ('host','origin','cookie','content-type','range','if-range','x-audio-decision','x-filename','x-forwarded-proto')}
    url=UPSTREAM+'/'+path
    if request.query_string:url+='?'+request.query_string
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=65),auto_decompress=False) as client:
            async with client.request(request.method,url,data=b''.join(chunks),headers=headers,allow_redirects=False) as source:
                outgoing={k:v for k,v in source.headers.items() if k.lower() in ('content-type','content-length','content-encoding','cache-control','set-cookie','content-range','accept-ranges','content-disposition','location','x-content-type-options')}
                response=web.StreamResponse(status=source.status,headers=outgoing);await response.prepare(request)
                async for chunk in source.content.iter_chunked(65536):await response.write(chunk)
                await response.write_eof();return response
    except aiohttp.ClientError:raise web.HTTPServiceUnavailable(text='Audio decision lab is restarting. Try again shortly.')

async def live(request):
    if request.headers.get('origin','').split('://',1)[-1]!=request.host:raise web.HTTPForbidden()
    ws=web.WebSocketResponse(max_msg_size=64008,heartbeat=20);await ws.prepare(request)
    headers={k:v for k,v in request.headers.items() if k.lower() in ('host','origin','cookie')}
    try:
        async with aiohttp.ClientSession() as client,client.ws_connect(UPSTREAM+'/ws',headers=headers,max_msg_size=2*1024**2,heartbeat=20) as upstream:
            async def pump(source,target):
                async for message in source:
                    if message.type==aiohttp.WSMsgType.TEXT:await target.send_str(message.data)
                    elif message.type==aiohttp.WSMsgType.BINARY:await target.send_bytes(message.data)
                    elif message.type in (aiohttp.WSMsgType.ERROR,aiohttp.WSMsgType.CLOSE):break
            tasks=[asyncio.create_task(pump(ws,upstream)),asyncio.create_task(pump(upstream,ws))]
            try:await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
    except (aiohttp.ClientError,ConnectionError):pass
    finally:await ws.close()
    return ws

def install(app):
    app.router.add_get('/audio-decision',redirect)
    app.router.add_get('/audio-decision/ws',live)
    app.router.add_route('*','/audio-decision/{path:.*}',proxy)
