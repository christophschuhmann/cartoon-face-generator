"""Bounded per-sentence recovery. Never replay a sentence after publishing audio."""
import asyncio
import json
import logging
import re
import httpx
from shared_turn import admitted_turn

log=logging.getLogger('robo.speech_retry')

class SpeechGenerationError(RuntimeError):
    def __init__(self,code,attempts,*,remaining_text=None,audio_published=False):
        self.code=code;self.attempts=attempts
        self.remaining_text=remaining_text;self.audio_published=audio_published
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

    Network failures before any PCM can retry after worker-idle admission.
    Published audio is never replayed automatically: only an explicit exact
    unspoken suffix from the verifier may resume after a clean terminal result.
    """
    attempts=max(1,min(3,attempts))
    prompt_level=0
    oom_fallback=False
    current=dict(body);any_emitted=False;remaining_text=None
    for attempt in range(attempts):
        request={**current,'seed':(int(body.get('seed',777))+104729*attempt)%2147483647}
        if oom_fallback:request.update(generation='single',batch_size=1)
        # The last unheard retry changes the generation strategy, not just its
        # seed. Use the already available Small RL candidate selector.
        if attempt==2 and not oom_fallback and request.get('model')=='small_rl' and request.get('align',True):
            request.update(generation='search_asr',n=3,batch_size=3,search_n=3,search_chunk_frames=12,search_seconds=30.)
        if 'message' in current:request['message']=recovery_prompt(current,prompt_level)
        emitted=False;completed=False;failure=None;resume=None
        try:
            async with admitted_turn(client,request,on_wait,timeout=timeout) as response:
                async for line in response.aiter_lines():
                    if not line.startswith('data: '):continue
                    event=json.loads(line[6:]);kind=event.get('event')
                    if kind=='error':
                        failure=event.get('code','generation_failed')
                        if failure=='generation_failed' and 'TTS target opening was not recognized' in str(event.get('message','')):
                            failure='unverified_speech'
                        break
                    if kind in ('audio_chunk','search_chunk') and (event.get('pcm_f32') or event.get('url')):
                        emitted=True;any_emitted=True
                    if kind=='result':
                        completed=True
                        if event.get('candidates'):emitted=True;any_emitted=True
                        report=event.get('live_stream') or {}
                        if (report.get('enabled') or report.get('verification_mode')=='candidate_search') and report.get('start_verified') and not report.get('end_verified'):
                            failure='incomplete_verified_speech'
                            if report.get('resume_safe') and isinstance(report.get('remaining_text'),str):
                                resume=report['remaining_text'].strip()
                    yield event
        except (httpx.TransportError,ConnectionError,TimeoutError) as exc:
            failure='transport_before_audio' if not emitted else 'transport_after_audio'
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (408,429,500,502,503,504):raise
            failure='temporary_http_failure'
        if failure is None and completed and emitted:return
        if failure is None:failure='empty_audio' if completed else 'incomplete_stream'
        recoverable=failure in ('unverified_speech','empty_audio','transport_before_audio','temporary_http_failure','incomplete_stream') or (failure=='cuda_oom' and attempt==0)
        if resume:
            remaining_text=resume
            current={**current,'message':'GENERAL: Natural, clear speech in the voice of the reference speaker.\nSCRIPT:\n(natural, relaxed) '+resume}
            prompt_level=1
        elif emitted:
            remaining_text=None  # Position after an interrupted stream is unknown.
        can_retry=(bool(resume) or not emitted and recoverable) and attempt+1<attempts
        log.warning('sentence failure code=%s attempt=%s audio_published=%s retry=%s',
                    failure,attempt+1,emitted,can_retry)
        if not can_retry:
            raise SpeechGenerationError(failure,attempt+1,remaining_text=remaining_text,audio_published=any_emitted)
        if failure in ('unverified_speech','empty_audio'):prompt_level+=1
        if failure=='cuda_oom' and body.get('generation')=='search_asr':oom_fallback=True
        strategy='verified_suffix' if resume else 'single_stream_after_oom' if oom_fallback else 'compact_direction' if prompt_level==1 else 'natural_delivery' if prompt_level>=2 else 'new_seed'
        yield {'event':'speech_retry','attempt':attempt+2,'max_attempts':attempts,'code':failure,'strategy':strategy,'continuation':bool(resume)}
        await asyncio.sleep(.15 if failure!='cuda_oom' else .5)


async def retained_speech_events(*args,**kwargs):
    """Let the conversation finish collecting text when audio recovery fails."""
    try:
        async for event in speech_events(*args,**kwargs):yield event
    except SpeechGenerationError as exc:
        yield {'event':'speech_unavailable','code':exc.code,'attempts':exc.attempts,
               'remaining_text':exc.remaining_text,'audio_published':exc.audio_published}
