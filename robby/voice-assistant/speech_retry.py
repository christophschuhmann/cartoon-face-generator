"""Bounded per-sentence recovery. Never replay a sentence after publishing audio."""
import asyncio
import json
import logging
import re
from shared_turn import admitted_turn

log=logging.getLogger('robo.speech_retry')

class SpeechGenerationError(RuntimeError):
    def __init__(self,code,attempts):
        self.code=code;self.attempts=attempts
        super().__init__(f'Speech generation failed ({code}; {attempts} attempt(s))')

def recovery_prompt(body, level):
    """Shorten failed Small RL acting instructions, never the spoken script.

    First retry preserves all inline acting cues. The final retry replaces
    only the initial cue with natural delivery; internal cues/pauses survive.
    Other input formats/checkpoints remain untouched.
    """
    message=body.get('message','')
    if not level or body.get('model')!='small_rl' or body.get('input_mode')!='manual' or body.get('format')!='structured':
        return message
    parts=re.split(r'\nSCRIPT:\s*\n?',message,maxsplit=1)
    if len(parts)!=2 or not parts[0].startswith('GENERAL:'):return message
    script=parts[1]
    if level>=2:script=re.sub(r'^\([A-Za-z_ ,\-]{1,100}\)', '(natural, relaxed)',script,count=1)
    language={'de':'German','en':'English','fr':'French','es':'Spanish','nl':'Dutch'}.get(body.get('language'),'')
    return f'GENERAL: Natural, clear {language} speech in the voice of the reference speaker.\nSCRIPT:\n{script}'

async def speech_events(client,body,on_wait,*,timeout=45.,attempts=3):
    """Only explicit recoverable server failures, or clean empty completion.

    No retry of ambiguous network loss, cancellation, or any published chunk.
    Previous sentences are not resubmitted. Each retry uses a different seed.
    Admission waits for the previous worker to finish its cleanup.
    """
    attempts=max(1,min(3,attempts))
    prompt_level=0
    for attempt in range(attempts):
        request={**body,'seed':(int(body.get('seed',777))+104729*attempt)%2147483647}
        if 'message' in body:request['message']=recovery_prompt(body,prompt_level)
        emitted=False;completed=False;failure=None
        async with admitted_turn(client,request,on_wait,timeout=timeout) as response:
            async for line in response.aiter_lines():
                if not line.startswith('data: '):continue
                event=json.loads(line[6:]);kind=event.get('event')
                if kind=='error':
                    failure=event.get('code','generation_failed')
                    # Compatibility with the previous pinned TTS worker.
                    if failure=='generation_failed' and 'TTS target opening was not recognized' in str(event.get('message','')):
                        failure='unverified_speech'
                    break
                if kind in ('audio_chunk','search_chunk') and (event.get('pcm_f32') or event.get('url')):
                    emitted=True
                if kind=='result':
                    completed=True
                    # Legacy downloadable results may contain audio too.
                    if event.get('candidates'):emitted=True
                yield event
        if failure is None and completed and emitted:return
        if failure is None:failure='empty_audio' if completed else 'incomplete_stream'
        recoverable=failure in ('unverified_speech','empty_audio') or (failure=='cuda_oom' and attempt==0)
        log.warning('sentence failure code=%s attempt=%s audio_published=%s retry=%s',
                    failure,attempt+1,emitted,not emitted and recoverable and attempt+1<attempts)
        if emitted or not recoverable or attempt+1>=attempts:
            raise SpeechGenerationError(failure,attempt+1)
        if failure in ('unverified_speech','empty_audio'):prompt_level+=1
        strategy='compact_direction' if prompt_level==1 else 'natural_delivery' if prompt_level>=2 else 'new_seed'
        yield {'event':'speech_retry','attempt':attempt+2,'max_attempts':attempts,'code':failure,'strategy':strategy}
        await asyncio.sleep(.15 if failure!='cuda_oom' else .5)
