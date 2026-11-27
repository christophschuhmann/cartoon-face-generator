"""Authenticated TLS gateway for the existing local Gemma and Humaneness TTS.

No model is loaded here. Only these bounded OpenAI-compatible endpoints are
exposed; never proxy arbitrary URLs, model downloads or model switching.
"""
import asyncio
import audioop
import base64
import binascii
import hmac
import io
import json
import os
from pathlib import Path
import wave

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

TOKEN_FILE=Path(os.environ.get('ROBBY_API_TOKEN_FILE',str(Path.home()/'.config/robby-api/token')))
LLM='http://127.0.0.1:18826'
TTS='http://127.0.0.1:8792'
LLM_MODEL='gemma-4-26b-a4b-q4'
TTS_MODEL='humaneness-voice-small'
VOICES={'alloy':'emolia_c1699','mira':'emolia_c1699','selma':'emolia_c0542',
        'idris':'anime_088','anton':'k395_age3_bg1','robin':'k91_age5_bg0',
        'osku':'mediathek_0184','cormac':'emolia_c1682','rasmus':'emolia_c2570',
        'nora':'k10_age3_bg1','bela':'k325_age3_bg1','béla':'k325_age3_bg1'}
app=FastAPI(title='Robby local OpenAI-compatible API',docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def authenticate(request,call_next):
    try:expected=TOKEN_FILE.read_text().strip()
    except OSError:return JSONResponse({'error':{'message':'API key unavailable'}},status_code=503)
    value=request.headers.get('authorization','')
    supplied=value[7:] if value.lower().startswith('bearer ') else ''
    if not supplied or not hmac.compare_digest(supplied.encode(),expected.encode()):
        return JSONResponse({'error':{'message':'Invalid API key','type':'authentication_error'}},status_code=401)
    length=request.headers.get('content-length','0') or '0'
    if not length.isdecimal() or int(length)>100000:
        return JSONResponse({'error':{'message':'Request too large'}},status_code=413)
    return await call_next(request)

@app.get('/v1/models')
async def models():
    return {'object':'list','data':[{'id':name,'object':'model','owned_by':'local'} for name in (LLM_MODEL,TTS_MODEL)]}

@app.post('/v1/chat/completions')
async def chat(request:Request):
    try:body=await request.json()
    except (ValueError,UnicodeError):raise HTTPException(400,'Invalid JSON')
    if not isinstance(body,dict) or body.get('model')!=LLM_MODEL:
        raise HTTPException(400,'Use model '+LLM_MODEL)
    if not isinstance(body.get('messages'),list) or not body['messages']:
        raise HTTPException(400,'messages must be a nonempty array')
    if len(json.dumps(body,ensure_ascii=False).encode())>100000:raise HTTPException(413,'Request too large')
    template=body.setdefault('chat_template_kwargs',{})
    if not isinstance(template,dict):raise HTTPException(400,'chat_template_kwargs must be an object')
    template.setdefault('enable_thinking',False)
    client=httpx.AsyncClient(timeout=httpx.Timeout(180,connect=5),trust_env=False)
    try:response=await client.send(client.build_request('POST',LLM+'/v1/chat/completions',json=body),stream=True)
    except httpx.HTTPError:
        await client.aclose();raise HTTPException(503,'Local language model unavailable')
    if response.status_code>=400:
        raw=await response.aread();status=response.status_code;await response.aclose();await client.aclose()
        return Response(raw,status_code=status,media_type='application/json')
    async def stream_response():
        try:
            async for chunk in response.aiter_raw():yield chunk
        finally:await response.aclose();await client.aclose()
    return StreamingResponse(stream_response(),media_type=response.headers.get('content-type','application/json'),
                             headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

class SpeechRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    model:str=TTS_MODEL
    input:str=Field(min_length=1,max_length=1600)
    voice:str='mira'
    response_format:str='mp3'
    stream:bool=False  # Explicit extension: true streams PCM as it is generated.
    instructions:str=Field(default='Gentle, natural and spontaneous.',max_length=400)

def backend_body(body,voice):
    # Ensure instructions are a single line; transcript remains verbatim.
    style=' '.join(body.instructions.split())
    return {'model':'small_rl','input_mode':'manual','format':'structured',
        'message':'GENERAL: '+style+'\nSCRIPT:\n'+body.input,
        'generation':'single','n':1,'streaming':True,'stream_transport':'pcm_f32',
        'live_only':True,'cancel_on_disconnect':True,'chunk_frames':5,'first_chunk_frames':2,
        'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':voice,
        'voice_conversion':False,'align':True}

async def pcm_events(response):
    rate_state=None;finished=False
    async for line in response.aiter_lines():
        if not line.startswith('data: '):continue
        try:event=json.loads(line[6:])
        except json.JSONDecodeError:raise RuntimeError('Invalid TTS event')
        if event.get('event')=='error':raise RuntimeError('Speech generation failed: '+str(event.get('code','unknown')))
        if event.get('event')=='result':finished=True
        if event.get('event')=='audio_chunk':
            if event.get('sample_rate')!=48000 or event.get('channels')!=1:raise RuntimeError('Unexpected TTS audio format')
            try:floats=np.frombuffer(base64.b64decode(event['pcm_f32'],validate=True),dtype='<f4')
            except (KeyError,ValueError,binascii.Error):raise RuntimeError('Invalid TTS audio')
            if not np.isfinite(floats).all():raise RuntimeError('Invalid TTS audio samples')
            pcm=(np.clip(floats,-1.,1.)*32767).astype('<i2').tobytes()
            pcm,rate_state=audioop.ratecv(pcm,2,1,48000,24000,rate_state)
            if pcm:yield pcm
    if not finished:raise RuntimeError('TTS stream ended before completion')

async def ffmpeg_encode(pcm,fmt):
    if fmt=='wav':
        out=io.BytesIO()
        with wave.open(out,'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(pcm)
        return out.getvalue()
    codec=['-codec:a','libmp3lame','-b:a','128k','-f','mp3']
    process=await asyncio.create_subprocess_exec('ffmpeg','-nostdin','-v','error','-f','s16le','-ar','24000',
        '-ac','1','-i','pipe:0',*codec,'pipe:1',stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:out,_=await process.communicate(pcm)
    except BaseException:
        if process.returncode is None:process.kill()
        await process.wait();raise
    if process.returncode:raise HTTPException(502,'Audio encoding failed')
    return out

@app.post('/v1/audio/speech')
async def speech(body:SpeechRequest):
    if body.model!=TTS_MODEL:raise HTTPException(400,'Use model '+TTS_MODEL)
    if not body.input.strip() or len(body.input.split())>120:raise HTTPException(400,'Use nonempty input with at most 120 words')
    fmt=body.response_format.lower();voice=VOICES.get(body.voice.casefold())
    if not voice:raise HTTPException(400,'Unknown voice; choose mira, selma, idris, anton, robin, osku, cormac, rasmus, nora or bela')
    if fmt not in ('pcm','wav','mp3'):raise HTTPException(400,'Use response_format pcm, wav or mp3')
    if body.stream and fmt!='pcm':raise HTTPException(400,'Streaming supports response_format pcm; buffered responses support pcm, wav and mp3')
    client=httpx.AsyncClient(timeout=httpx.Timeout(180,connect=5),trust_env=False)
    try:r=await client.send(client.build_request('POST',TTS+'/api/turn',json=backend_body(body,voice)),stream=True)
    except httpx.HTTPError:
        await client.aclose();raise HTTPException(503,'Local TTS unavailable')
    if r.status_code>=400:
        status=r.status_code;await r.aclose();await client.aclose()
        raise HTTPException(status,'TTS is busy or unavailable; retry later')
    chunks=pcm_events(r)
    try:first=await anext(chunks)
    except (StopAsyncIteration,RuntimeError,httpx.HTTPError):
        await r.aclose();await client.aclose();raise HTTPException(502,'TTS produced no verified speech')
    if body.stream:
        async def generate():
            try:
                yield first
                async for chunk in chunks:yield chunk
            finally:await r.aclose();await client.aclose()
        return StreamingResponse(generate(),media_type='application/octet-stream',
            headers={'X-Audio-Format':'s16le; rate=24000; channels=1','Cache-Control':'no-store','X-Accel-Buffering':'no'})
    try:
        pcm=bytearray(first)
        async for chunk in chunks:
            pcm.extend(chunk)
            if len(pcm)>4_000_000:raise HTTPException(413,'Audio output too long')
        data=bytes(pcm) if fmt=='pcm' else await ffmpeg_encode(bytes(pcm),fmt)
    except RuntimeError:raise HTTPException(502,'Speech generation failed')
    finally:await r.aclose();await client.aclose()
    return Response(data,media_type={'pcm':'application/octet-stream','wav':'audio/wav','mp3':'audio/mpeg'}[fmt],
        headers={'Cache-Control':'no-store'})
