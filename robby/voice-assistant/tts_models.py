"""One shared TTS GPU; asynchronous swaps do not hold a tunnel request open."""
import asyncio
import time
import httpx
from aiohttp import web

MODELS=[{'id':'small_rl','label':'Humaneness Small · 1.1 Alpha RL'},
        {'id':'large17','label':'Humaneness Large · 1.7 BF16'}]


def snapshot(bridge):
    return {'models':MODELS,'selected':bridge.tts_model,'loading':bridge.tts_loading,
            'error':bridge.tts_error,'failed_model':getattr(bridge,'tts_failed_model',None),'switch_seconds':getattr(bridge,'tts_switch_seconds',None)}


async def status(request):
    return web.json_response(snapshot(request.app['bridge']),headers={'Cache-Control':'no-store'})


async def select(request):
    bridge=request.app['bridge']
    try:choice=(await request.json())['model']
    except Exception:raise web.HTTPBadRequest(text='Expected a model ID')
    if choice not in {m['id'] for m in MODELS}:raise web.HTTPBadRequest(text='Unknown TTS model')
    if bridge.active or bridge.tts_loading:raise web.HTTPConflict(text='Wait for the current reply or model swap.')
    if choice==bridge.tts_model and not bridge.tts_error:return await status(request)
    bridge.tts_loading=choice;bridge.tts_error=None;bridge.tts_failed_model=None;bridge.tts_ready.clear()
    async def swap():
        started=time.perf_counter()
        try:
            async with httpx.AsyncClient(base_url=bridge.base,timeout=900) as client:
                response=await client.post('/api/models/select',json={'model':choice})
                response.raise_for_status()
            bridge.tts_model=choice
            bridge.ack=None  # Do not replay an acknowledgment from the previous checkpoint.
            bridge.tts_switch_seconds=round(time.perf_counter()-started,2)
        except httpx.HTTPStatusError as exc:
            bridge.tts_failed_model=choice
            detail=f'The voice service returned HTTP {exc.response.status_code}.'
            if exc.response.status_code==409:
                try: reason=exc.response.json().get('detail')
                except (AttributeError,ValueError): reason=None
                if isinstance(reason,str) and reason: detail=reason[:240]
            bridge.tts_error=detail
        except Exception as exc:
            bridge.tts_failed_model=choice
            bridge.tts_error='Voice switch could not finish ('+type(exc).__name__+').'
        finally:bridge.tts_loading=None;bridge.tts_ready.set()
    task=asyncio.create_task(swap());request.app['tasks'].append(task)
    return web.json_response(snapshot(bridge),status=202)
