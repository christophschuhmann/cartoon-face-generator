"""Bounded producer/consumer verification of actual incremental TTS PCM.

Only this consumer mutates the gate. The GPU producer never waits for an ASR
call; it appends PCM and reads a stop flag. One ASR job, no unbounded job queue.
Audio and transcripts exist only in request RAM. This is not forced alignment.
"""
from collections import deque
from types import SimpleNamespace
import threading
import time
import numpy as np
from streaming_boundaries import RATE,boundary_tokens


class ParallelBoundaryStream:
    def __init__(self,gate,reader,emit,check_cancel=lambda:None,*,window_seconds=12.,max_seconds=70.,first_scan_seconds=.6):
        self.gate=gate;self.reader=reader;self.emit=emit;self.check_cancel=check_cancel
        self.window_samples=round(window_seconds*RATE);self.max_samples=round(max_seconds*RATE)
        self.condition=threading.Condition();self.pending=deque()
        self.received=0;self.producer_done=False;self.stopped=False;self.cancelled=False
        self.error=None;self.evidence=[];self.checked_until=0;self.calls=0
        self.last_failed=False
        self.first_scan_samples=round(first_scan_seconds*RATE)
        self.gate.defer_opening_limit=True
        self.gate.strict_order=True
        self.gate.hold=.12
        self.gate.report.update(verification_mode='parallel',asr_window_max_seconds=window_seconds,
            verification_queue_limit=1,verification_wait_ms=0.,lookahead_seconds=.12,strict_word_order=True)
        self.gate.report['first_scan_min_seconds']=first_scan_seconds
        self.thread=threading.Thread(target=self._run,name='tts-word-verification',daemon=True)
        self.thread.start()

    def feed(self,chunk):
        self.check_cancel()
        chunk=np.asarray(chunk,np.float32).reshape(-1)
        if not np.isfinite(chunk).all():raise ValueError('Nonfinite TTS PCM')
        with self.condition:
            if self.error:raise self.error
            if self.stopped or self.cancelled:return True
            if self.producer_done:raise RuntimeError('Audio after producer completion')
            if self.received+len(chunk)>self.max_samples:raise ValueError('Verification audio limit exceeded')
            self.received+=len(chunk);self.pending.append(chunk.copy());self.condition.notify()
        return False

    def finish(self):
        started=time.perf_counter()
        with self.condition:self.producer_done=True;self.condition.notify_all()
        self.thread.join()
        self.gate.report['verification_wait_ms']=round((time.perf_counter()-started)*1000,2)
        self.check_cancel()
        if self.error:raise self.error

    def close(self):
        with self.condition:self.cancelled=True;self.pending.clear();self.condition.notify_all()
        # Remote requests have a bounded timeout. Retain model ownership until
        # a possible final resident-ASR fallback has actually completed.
        self.thread.join()

    def _publish(self,chunk):
        self.check_cancel()
        with self.condition:
            if self.cancelled:return
            if len(chunk):self.emit(chunk,dict(self.gate.report))

    def _snapshot(self):
        g=self.gate
        # Keep several seconds of overlap with the last confirmed word. Never
        # jump across an unverified middle just to catch up to the newest PCM.
        offset=max(0,int((g.verified_end or 0)-4*RATE)) if g.start is not None else 0
        offset=min(offset,max(0,g.total-self.window_samples))
        # Place the overlap boundary before an already recognized word, not
        # through its middle (which would remove it from both transcript parts).
        for word in self.evidence:
            if word['start']<=offset/RATE<word['end']+.08:
                offset=max(0,int((word['start']-.08)*RATE));break
        end=min(g.total,offset+self.window_samples)
        return offset,end,SimpleNamespace(buffer=g.buffer[offset:end].copy(),total=end-offset,
            last_scan=0,report={'asr_calls':0,'asr_ms':0.})

    def _check(self,final):
        offset,end,snapshot=self._snapshot()
        g=self.gate;before=time.perf_counter()
        result=self.reader.scores([snapshot],allow_local_fallback=final)[0]
        self.check_cancel()
        with self.condition:
            if self.cancelled:return
        self.calls+=1
        g.report['asr_calls']+=snapshot.report.get('asr_calls',0)
        g.report['asr_ms']+=snapshot.report.get('asr_ms',0.)
        for key in ('backend','asr_fallback','asr_error','asr_batch_size'):
            if key in snapshot.report:g.report[key]=snapshot.report[key]
        g.report.update(verification_last_request_ms=round((time.perf_counter()-before)*1000,2),
            verified_window_start_seconds=offset/RATE,verified_window_end_seconds=end/RATE)
        if 'asr_error' in snapshot.report:
            # One terminal failure remains fail-closed; no busy retry loop.
            g.last_scan=end;self.checked_until=end;self.last_failed=True
            return
        self.last_failed=False
        g.report.pop('asr_error',None)
        current=[]
        for word in result.get('timestamps',[]):
            try:
                a,b=float(word['start']),float(word['end'])
                if not np.isfinite([a,b]).all() or not 0<=a<=b<=(end-offset)/RATE+.08:continue
                current.extend({'word':token,'start':a+offset/RATE,'end':b+offset/RATE}
                               for token in boundary_tokens(word.get('word','')))
            except (ValueError,TypeError,KeyError):continue
        self.evidence=self._merge(current,offset/RATE)
        g.last_scan=end;self.checked_until=end
        self._publish(g.feed([],{'timestamps':self.evidence,'checked_audio_seconds':end/RATE}))
        if g.start is None and end>=6*RATE:
            g.done=True;g.report.update(blocked=True,note='No target opening in six seconds of checked audio')

    def _merge(self,current,offset):
        # ASR word timestamps are coarse. Cropping at a reported word boundary
        # can omit part of that word in the new decode. Retain the independently
        # confirmed prefix, then splice at an exact, time-consistent overlap.
        # An anchor must be INSIDE that prefix: never skip unverified words.
        confirmed=self.gate.confirmed_spans
        n=min(3,len(confirmed));names=[w['word'] for w in current]
        if n>=2:
            for end in range(len(confirmed),n-1,-1):
                anchor=confirmed[end-n:end]
                if anchor[0]['start']<offset:continue
                words=[w['word'] for w in anchor]
                for at in range(len(current)-n+1):
                    if names[at:at+n]==words and abs(current[at+n-1]['end']-anchor[-1]['end'])<=.64:
                        self.gate.report['overlap_anchors']=self.gate.report.get('overlap_anchors',0)+1
                        return confirmed[:end]+current[at+n:]
        if not offset:return current
        self.gate.report['overlap_unconfirmed']=self.gate.report.get('overlap_unconfirmed',0)+1
        return list(self.evidence)

    def _run(self):
        try:
            while True:
                self.check_cancel()
                with self.condition:
                    if self.cancelled:return
                    chunks=list(self.pending);self.pending.clear();final=self.producer_done
                for chunk in chunks:self._publish(self.gate.feed(chunk))
                g=self.gate
                if g.done:break
                scan_ready=final or g.start is not None or g.total>=self.first_scan_samples
                if scan_ready and (g.due(final=final) or final and self.last_failed) and (self.checked_until<g.total or final and self.last_failed):
                    _,end,_=self._snapshot()
                    if end<=self.checked_until and not self.last_failed:
                        g.report['note']='Verification stopped at the last supported word; no progress in bounded window'
                        self._publish(g.finish());break
                    self._check(final)
                    if g.done:break
                    if not self.last_failed and self.checked_until<g.total:continue
                if final:
                    self._publish(g.finish());break
                with self.condition:
                    if not self.pending and not self.producer_done and not self.cancelled:self.condition.wait(.1)
            self.check_cancel()
            if not self.cancelled and self.gate.start is None:self.gate.finish()
        except BaseException as exc:
            self.error=exc
        finally:
            with self.condition:self.stopped=True;self.condition.notify_all()
