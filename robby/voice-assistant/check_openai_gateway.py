"""Exercise the real gateway/models using synthetic prompts; never print the key."""
import asyncio,json,os,time
from pathlib import Path
import httpx

base='https://'+os.environ['ROBBY_API_HOST']+':18830'
private=Path.home()/'.config/robby-api'
token=(private/'token').read_text().strip()
headers={'Authorization':'Bearer '+token}

async def main():
    async with httpx.AsyncClient(verify=str(private/'server.crt'),timeout=180,trust_env=False) as client:
        r=await client.get(base+'/v1/models');assert r.status_code==401
        r=await client.get(base+'/v1/models',headers=headers);r.raise_for_status()
        print('Authenticated models:',[x['id'] for x in r.json()['data']],flush=True)
        body={'model':'gemma-4-26b-a4b-q4','messages':[{'role':'user','content':'Say hello in a single brief sentence.'}],'max_tokens':32,'temperature':0}
        started=time.monotonic();r=await client.post(base+'/v1/chat/completions',headers=headers,json=body);r.raise_for_status()
        assert r.json()['choices'][0]['message']['content'];print('LLM non-stream OK:',round(time.monotonic()-started,2),'s',flush=True)
        body['stream']=True;seen=0;started=time.monotonic()
        async with client.stream('POST',base+'/v1/chat/completions',headers=headers,json=body) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line.startswith('data: ') and line!='data: [DONE]':
                    event=json.loads(line[6:]);seen+=1
        assert seen>1;print('LLM streaming OK:',seen,'events in',round(time.monotonic()-started,2),'s',flush=True)
        speech={'model':'humaneness-voice-small','input':'Hello, this is a short test.','voice':'mira','response_format':'mp3'}
        started=time.monotonic();r=await client.post(base+'/v1/audio/speech',headers=headers,json=speech);r.raise_for_status()
        assert len(r.content)>1000 and r.headers['content-type'].startswith('audio/mpeg')
        print('TTS non-stream MP3 OK:',len(r.content),'bytes in',round(time.monotonic()-started,2),'s',flush=True)
        speech.update(stream=True,response_format='pcm');started=time.monotonic();size=0;first=None;chunks=0
        async with client.stream('POST',base+'/v1/audio/speech',headers=headers,json=speech) as r:
            r.raise_for_status();assert r.headers.get('x-audio-format','').startswith('s16le')
            async for chunk in r.aiter_bytes():
                if first is None:first=time.monotonic()-started
                size+=len(chunk);chunks+=1
        assert size>48000 and size%2==0;print('TTS streaming PCM OK:',size,'bytes;',chunks,'chunks; first',round(first,2),'s',flush=True)

if __name__=='__main__':asyncio.run(main())
