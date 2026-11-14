"""Mount this before an existing FastAPI catch-all. Reuses its HTTPS tunnel.

    from integrations.fastapi_proxy import install
    install(app, prefix='/podcast', upstream='http://127.0.0.1:8816')

The podcast process must set PODCAST_ROOT_PATH=/podcast. No GPU work here.
"""
import httpx
from fastapi import Request,HTTPException
from fastapi.responses import StreamingResponse,RedirectResponse

def install(app,prefix='/podcast',upstream='http://127.0.0.1:8816'):
    @app.get(prefix,include_in_schema=False)
    async def redirect():return RedirectResponse(prefix+'/',status_code=307)
    @app.api_route(prefix+'/{path:path}',methods=['GET','HEAD','POST','DELETE'],include_in_schema=False)
    async def proxy(path:str,request:Request):
        if '..' in path or '\\' in path:raise HTTPException(404)
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>512*1024:raise HTTPException(413,'Maximum request: 512 KiB')
        headers={k:v for k,v in request.headers.items() if k.lower() in ('authorization','content-type','cookie','range','if-range','idempotency-key','x-forwarded-proto','cf-connecting-ip')}
        url=upstream+'/'+path
        if request.url.query:url+='?'+request.url.query
        client=httpx.AsyncClient(timeout=60,follow_redirects=False)
        try:source=await client.send(client.build_request(request.method,url,content=bytes(body),headers=headers),stream=True)
        except httpx.HTTPError:
            await client.aclose();raise HTTPException(503,'Podcast API is restarting; retry shortly')
        outgoing={k:v for k,v in source.headers.items() if k.lower() in ('content-type','content-length','cache-control','content-disposition','set-cookie','content-range','accept-ranges','location','retry-after','x-content-type-options')}
        async def stream():
            try:
                async for chunk in source.aiter_raw():yield chunk
            finally:await source.aclose();await client.aclose()
        return StreamingResponse(stream(),status_code=source.status_code,headers=outgoing)
