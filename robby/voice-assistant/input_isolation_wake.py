"""Bounded raw-audio wake recovery. No ordinary unknown speech reaches the LLM.

Necessary because an enrolled-voice separator can erase a new person's wake
phrase. Runs only beside an active filter, after a neural speech pause. It uses
the existing recognizer and CPU ECAPA, not another permanent GPU model.
"""
import asyncio,time
import numpy as np

class RawWakeRecovery:
    def __init__(self,owner):
        self.owner=owner;self.vad=None;self.start=None;self.end=0.;self.task=None
        self.epoch=0;self.checks=0;self.recovered=0;self.busy_skips=0;self.last_ms=None;self.error=None
    def reset(self):
        self.epoch+=1;self.vad=None;self.start=None
        if self.task:self.task.cancel()
    async def feed(self,x,end,playback):
        o=self.owner;s=getattr(o.c,'sentence_stream',None)
        if not s or o.phase!='active' or not o.references:
            self.start=None;self.vad=None;return
        from pause_vad import SpeechClock
        if self.vad is None:self.vad=SpeechClock()
        if playback:
            # Never build a new voice reference from bot echo or a mixed barge.
            self.start=None;self.vad=None;return
        before=self.vad.last_speech
        await asyncio.to_thread(self.vad.feed,x,end)
        if self.vad.last_speech>before:
            if self.start is None:self.start=max(0,end-len(x)/16000-.16)
            self.end=self.vad.last_speech
        # Enrollment is not a low-latency stop detector. A 400-ms pause after
        # "Hey Robby" often precedes the name; keep that introduction together.
        # The primary turn/stop path retains the user's own pause setting.
        if self.start is None or end-self.end<max(1.,s.pause_ms/1000):return
        start,stop=self.start,min(end,self.end+.12);self.start=None
        if stop-start<.8:return
        if self.task and not self.task.done():self.busy_skips+=1;return
        # A bounded completed utterance, not an endlessly queued rolling decode.
        if stop-start>24:
            self.error='Raw wake utterance exceeds 24 s; say Hey Robby in a shorter introduction.';return
        audio=o.raw_audio(start,stop)
        if audio is None or len(audio)<12800:return
        self.task=o.task(self.check(start,stop,audio,self.epoch))
    async def check(self,start,end,audio,epoch):
        o=self.owner;s=o.c.sentence_stream;admission=s.admission_epoch;t=time.perf_counter();self.checks+=1
        try:
            if o.duplicate(start,end,'raw_isolation_wake'):return
            from speaker_teacher import get_cached_teacher,enrollment_reference
            vector=await asyncio.to_thread(get_cached_teacher().embed,enrollment_reference(audio))
            ranking=sorted([(max((float(vector@v) for v in u.get('vectors',[])),default=-1.),sid)
                            for sid,u in s.memory.users.items()],reverse=True)
            if (ranking and ranking[0][1] in o.references and ranking[0][0]>=.55
                and (len(ranking)==1 or ranking[0][0]>=ranking[1][0]+.12) and o.output_ratio(start,end,audio)>=.6):
                return  # Already represented by a filter; don't duplicate its normal ASR.
            if s.asr.selected=='nemotron':
                rows=await asyncio.wait_for(asyncio.to_thread(o.c.ears.service.engine.asr.transcribe,[audio.copy()]),12)
                result={'text':rows[0],'model':'nemotron'}
            else:result=await asyncio.wait_for(s.asr.transcribe(s.asr.selected,audio),12)
            text=' '.join(result.get('text','').split())
            if epoch!=self.epoch or o.closed or o.selected=='off' or admission!=s.admission_epoch or not text:return
            if o.duplicate(start,end,'raw_isolation_wake'):return
            if not o.admit(text,vector):return
            if o.duplicate(start,end,'raw_isolation_wake'):return
            # Re-enter the normal, serialized turn/identity path. It decides the
            # profile, name, reply and wake ownership; this side path never does.
            done=asyncio.create_task(asyncio.sleep(0));await done
            asr={**result,'input_start_s':start,'input_end_s':end,'input_source':'raw_isolation_wake',
                 'endpoint_reason':'raw_wake_neural_speech_pause','speech_pause_ms':s.pause_ms}
            cached={'task':done,'embedding':vector,'compute_ms':0.}
            s.queue.put_nowait((text,audio,end,time.perf_counter(),cached,asr,None,admission,None))
            self.recovered+=1;self.error=None
        except asyncio.CancelledError:raise
        except Exception as exc:self.error=type(exc).__name__+' in raw wake recovery; original microphone and normal filter path remain available.'
        finally:
            self.last_ms=round((time.perf_counter()-t)*1000,1)
            await o.notice(True)
    def state(self):
        return {'checks':self.checks,'recovered':self.recovered,'busy_skips':self.busy_skips,'last_ms':self.last_ms,'error':self.error}
