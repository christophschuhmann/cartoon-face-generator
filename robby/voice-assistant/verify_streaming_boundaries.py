"""Real loopback TTS/ASR boundary smoke; saves synthetic audio and measured timings."""
import asyncio,base64,json,time,urllib.request
from pathlib import Path
import aiohttp
import numpy as np
import soundfile as sf
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'logs'/'streaming-boundaries';OUT.mkdir(exist_ok=True)

async def case(client,text,language,align,transport='continuous'):
    start=time.perf_counter();first=None;waves=[];events=[]
    prompt='GENERAL: Very genuine, very authentic, gentle, natural and spontaneous conversation.\nSCRIPT:\n(gentle, natural) '+text
    def record(e):
        nonlocal first
        if e.get('pcm_f32'):
            if first is None:first=time.perf_counter()-start
            waves.append(np.frombuffer(base64.b64decode(e['pcm_f32']),dtype='<f4').copy())
        events.append({k:v for k,v in e.items() if k not in ('pcm_f32','audio','audio_base64')})
    if transport=='continuous':
        async with client.ws_connect('http://127.0.0.1:8792/api/live-speech') as ws:
            await ws.send_json({'type':'start','model':'small_rl','max_active':2,'temperature':.8})
            ready=await ws.receive_json();assert ready['event']=='ready',ready
            await ws.send_json({'type':'submit','id':'test','order':0,'message':prompt,'language':language,'align':align})
            await ws.send_json({'type':'finish'})
            async for msg in ws:
                e=json.loads(msg.data);record(e)
                if e['event'] in ('error','session_done'):break
    else:
        body={'model':'small_rl','input_mode':'manual','format':'structured','message':prompt,
              'generation':'single','n':1,'streaming':True,'live_only':True,'stream_transport':'pcm_f32','align':align,
              'chunk_frames':5,'first_chunk_frames':2,'temperature':.8,'guidance':2.,'seed':777,
              'voice_mode':'profile','voice_profile':'emolia_c1699','voice_conversion':False,
              'speaker':{'method':'off'},'ranking':{'mode':'legacy'}}
        async with client.post('http://127.0.0.1:8792/api/turn',json=body) as r:
            assert r.status==200,await r.text()
            async for raw in r.content:
                if raw.startswith(b'data: '):record(json.loads(raw[6:]))
    wave=np.concatenate(waves) if waves else np.zeros(0,np.float32)
    name=f'{transport}-{language}-{int(align)}'
    if len(wave):sf.write(OUT/(name+'.wav'),wave,48000)
    result={'transport':transport,'language':language,'target':text,'align':align,
        'first_audio_ms':None if first is None else round(first*1000,1),'wall_ms':round((time.perf_counter()-start)*1000,1),
        'audio_seconds':len(wave)/48000,'chunks':len(waves),'events':events,
        'passed':bool(len(wave)) and not any(e['event']=='error' for e in events)}
    (OUT/(name+'.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in result.items() if k!='events'},ensure_ascii=False),flush=True)
    return result

async def main():
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as client:
        for _ in range(900):
            async with client.get('http://127.0.0.1:8792/api/state') as r:state=await r.json()
            if state.get('error'):raise RuntimeError(state['error'])
            if state.get('ready') and not state.get('busy'):break
            await asyncio.sleep(2)
        else:raise TimeoutError('TTS not ready')
        results=[]
        for lang,text in [('de','Hallo, schön dich zu sehen. Heute können wir gemeinsam etwas Neues entdecken.'),
                          ('en','Hello, nice to see you. We can discover something new together today.')]:
            for aligned in (False,True):results.append(await case(client,text,lang,aligned))
        results.append(await case(client,'Guten Morgen! Ich freue mich auf unser Gespräch.','de',True,'classic'))
        (OUT/'summary.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
        if not all(r['passed'] for r in results):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
