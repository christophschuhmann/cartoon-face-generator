"""Causal ASR-confirmed TTS edges. All positions refer to original 48-kHz PCM.

No forced transcript can open the gate: the first one/two target words must
actually be decoded. Missing evidence never releases the buffered raw audio.
"""
import difflib
import os
import time
import numpy as np
from metrics import tokens
from functools import lru_cache

RATE = 48000

@lru_cache(maxsize=2)
def boundary_client(url):
    import httpx
    # Reuse loopback connections and avoid constructing a TLS/proxy context
    # for every 400-ms audio check. This endpoint is never an Internet host.
    return httpx.Client(base_url=url,timeout=2.,trust_env=False)

# Orthographic equivalents, not permission to replace intended speech. Keep
# this local to boundary matching: the transcript and the TTS prompt stay intact.
_EXPAND = {"geht's":'geht es', 'gehts':'geht es', "gibt's":'gibt es',
           "ist's":'ist es', "hab's":'habe es', "it's":'it is',
           "i'm":'i am', "you're":'you are', "that's":'that is',
           "let's":'let us', "don't":'do not', "can't":'cannot',
           'okay':'ok'}
_NUMBERS = dict(zip('zero one two three four five six seven eight nine ten eleven twelve'.split(),map(str,range(13))))
_NUMBERS.update(zip('null eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf'.split(),map(str,range(13))))

def boundary_tokens(text):
    return [_NUMBERS.get(part,part) for word in tokens(text)
            for part in _EXPAND.get(word,word).split()]


class UnverifiedSpeechError(RuntimeError):
    pass


class SpeechBoundaryGate:
    def __init__(self, text, enabled=True, *, preserve_lead=False, tail_allow=0.):
        self.words = boundary_tokens(text)
        self.enabled = bool(enabled and self.words)
        self.preserve_lead = preserve_lead
        self.tail_allow = tail_allow
        self.buffer = np.empty(0, np.float32)
        self.total = self.cursor = self.emitted = 0
        self.start = self.verified_end = self.end = None
        self.done = False
        self.defer_opening_limit = False
        self.strict_order = False
        self.confirmed_spans = []
        self.last_scan = 0
        self.fade = .1
        self.hold = .4
        self.sustain_hop = max(.4,min(1.2,float(os.environ.get("SMALL_BOUNDARY_HOP_S",".8"))))
        self.report = dict(enabled=self.enabled, backend='Parakeet v3 target-word gate',
            lead_s=None, cut_s=None, stopped=False, start_verified=False,
            end_verified=False, emitted_seconds=0., fade_in_seconds=self.fade,
            fade_out_seconds=self.fade, lookahead_seconds=self.hold, asr_hop_seconds_after_start=self.sustain_hop, asr_calls=0, asr_ms=0.)

    def due(self, final=False):
        if not self.enabled or self.done or self.end is not None:
            return False
        # Rapid opening confirmation; fewer checks after the gate is open.
        hop=.4 if self.start is None else self.sustain_hop
        return self.total > self.last_scan and (final or
            (self.total >= int(.6*RATE) and self.total-self.last_scan >= int(hop*RATE)))

    def _observe(self, score):
        spans=[]
        for w in score.get('timestamps') or []:
            try:
                a,b=float(w['start']),float(w['end'])
            except (KeyError, TypeError, ValueError):
                continue
            if not np.isfinite([a,b]).all() or not 0 <= a <= b <= self.total/RATE+.08:
                continue
            # Tokenization may split contractions; retain original word times.
            spans.extend((word,a,b) for word in boundary_tokens(w.get('word','')))
        names=[w[0] for w in spans]
        self.report.update(asr_word_count=len(names),target_word_count=len(self.words))
        count=min(2,len(self.words))
        positions=[i for i in range(len(names)-count+1)
                   if names[i:i+count] == self.words[:count]]
        mode='exact_normalized'
        if not positions and len(self.words)>=4:
            # One minor spelling error in a long opening word is allowed only
            # with THREE exact neighbouring target words. No generic fuzzy
            # two-word opening, no omitted negation and no forced alignment.
            for i in range(len(names)-3):
                a=self.words[:4];b=names[i:i+4]
                mismatch=[k for k in range(4) if a[k]!=b[k]]
                if len(mismatch)!=1 or mismatch[0]>1:continue
                k=mismatch[0]
                if min(len(a[k]),len(b[k]))<5:continue
                spelling=difflib.SequenceMatcher(a=a[k],b=b[k],autojunk=False).ratio()
                if spelling<.84 and a[k].replace('ph','f')!=b[k].replace('ph','f'):continue
                names=names.copy();names[i+k]=a[k];positions=[i];mode='four_word_spelling_anchor';break
        if not positions:
            return
        if self.start is None:
            i=positions[0]
            a=spans[i][1]
            self.start=0 if self.preserve_lead else max(0,int((a-self.fade)*RATE))
            self.cursor=self.start
            self.report.update(start_verified=True,lead_s=a,removed_leading_seconds=self.start/RATE,
                               start_confirmation_audio_seconds=score.get('checked_audio_seconds',self.total/RATE),opening_match=mode)
        # Anchor subsequent decodes at the same first words, allowing small ASR
        # timestamp drift. Never jump to a later repetition of the same phrase.
        positions=[i for i in positions if abs(spans[i][1]-self.report['lead_s']) <= .45]
        if not positions:
            return
        i=positions[0]
        heard=names[i:]
        if self.strict_order:
            # Release only the contiguous, actually decoded target prefix.
            # A later common suffix cannot skip an unverified middle/negation.
            prefix=0
            variants=0
            for at,(expected,actual) in enumerate(zip(self.words,heard)):
                if expected!=actual:
                    # ASR sometimes drops a weak German verb ending (summen ->
                    # summ). Accept one such ending only inside a four-word
                    # exact neighbourhood. No skipped words, fuzzy opening,
                    # changed negations, or guessed final word.
                    stem=expected[:-2] if expected.endswith('en') else ''
                    variant=(variants==0 and len(stem)>=4 and actual==stem and at>=2
                        and self.words[at-2:at]==heard[at-2:at]
                        and len(self.words[at+1:at+3])==2
                        and self.words[at+1:at+3]==heard[at+1:at+3]
                        and expected not in {'keinen','niemanden','ohne','nein','nicht','nichts'})
                    if not variant:break
                    variants+=1
                prefix+=1
            self.report.update(ordered_target_words=prefix,target_word_count=len(self.words),
                               contextual_ending_variants=variants)
            if not prefix:return
            if prefix>=len(self.confirmed_spans):
                self.confirmed_spans=[{'word':self.words[k],'start':spans[i+k][1],'end':spans[i+k][2]}
                                      for k in range(prefix)]
            last_time=spans[i+prefix-1][2]
            self.verified_end=max(self.verified_end or 0,int(last_time*RATE))
            if prefix==len(self.words):
                end=int((last_time+.06+self.tail_allow+self.fade)*RATE)
                if end>=self.cursor:
                    self.end=end;self.report.update(end_verified=True,cut_s=end/RATE)
            return
        matcher=difflib.SequenceMatcher(a=self.words,b=heard,autojunk=False)
        blocks=[b for b in matcher.get_matching_blocks() if b.size]
        matched=sum(b.size for b in blocks)
        if not blocks:
            return
        last=blocks[-1]
        last_time=spans[i+last.b+last.size-1][2]
        # Isolated late common words are not sufficient evidence of progress.
        target_progress=last.a+last.size
        if matched/max(1,target_progress) >= .75:
            self.verified_end=max(self.verified_end or 0, int(last_time*RATE))
        tail=min(3,len(self.words))
        suffix_ok=(last.a+last.size==len(self.words) and last.size>=tail
                   and matched/max(1,len(self.words)) >= .8)
        if suffix_ok:
            # Fade starts after the final recognized word, preserving its end.
            end=int((last_time+.06+self.tail_allow+self.fade)*RATE)
            if end >= self.cursor:
                self.end=end
                self.report.update(end_verified=True,cut_s=end/RATE)

    def _release(self, stop):
        stop=max(self.cursor,min(self.total,int(stop)))
        out=self.buffer[self.cursor:stop].copy()
        if not len(out):
            return out
        pos=np.arange(self.cursor,stop)
        if self.start is not None and not self.preserve_lead:
            out*=np.clip((pos-self.start)/(self.fade*RATE),0,1)
        if self.end is not None:
            out*=np.clip((self.end-1-pos)/(self.fade*RATE),0,1)
        self.cursor=stop
        self.emitted+=len(out)
        self.report['emitted_seconds']=self.emitted/RATE
        return out

    def feed(self, chunk, score=None):
        chunk=np.asarray(chunk,dtype=np.float32).reshape(-1)
        if self.done:
            return np.empty(0,np.float32)
        self.total+=len(chunk)
        if not self.enabled:
            self.emitted+=len(chunk)
            return chunk
        self.buffer=np.concatenate((self.buffer,chunk))
        self._observe(score or {})
        if self.start is None:
            if self.total >= 6*RATE and not self.defer_opening_limit:
                self.done=True
                self.report.update(blocked=True,note='Target opening words not recognized within 6 seconds')
            return np.empty(0,np.float32)
        if self.end is not None and self.total>=self.end:
            out=self._release(self.end)
            self.done=True
            self.report['stopped']=True
            return out
        # Never release the unknown tail ahead of the last target-word evidence.
        safe=min(self.total-int(self.hold*RATE),(self.verified_end or self.cursor)+int(.06*RATE))
        return self._release(safe)

    def finish(self, aligned_wave=None):
        # aligned_wave is accepted for legacy callers, but cannot establish ASR
        # evidence or change original sample coordinates after a leading crop.
        if not self.enabled:
            return np.empty(0,np.float32)
        if self.start is None:
            self.report.update(blocked=True,note='No verified target opening; raw audio suppressed')
            raise UnverifiedSpeechError('TTS target opening was not recognized; unverified audio was withheld. Please retry.')
        if self.done:
            return np.empty(0,np.float32)
        end=min(self.total,self.end or ((self.verified_end or self.cursor)+int((.06+self.fade)*RATE)))
        self.end=max(self.cursor,end)
        if not self.report['end_verified']:
            self.report['note']='Incomplete ASR target; faded at last verified target word'
        self.report.update(cut_s=self.end/RATE,stopped=True)
        out=self._release(self.end)
        self.done=True
        return out


class BoundaryASR:
    """Reuse the resident ASR, batch due streams, and never decode per token."""
    def __init__(self, asr):
        from search_scoring import SearchScorer
        self.reader=SearchScorer.__new__(SearchScorer)
        self.reader.asr=asr

    def transcribe(self,waves, *, allow_local_fallback=True):
        """Optional warm independent GPU worker; resident v3 is the fallback."""
        url=os.environ.get('SMALL_BOUNDARY_ASR_URL','').rstrip('/')
        if url:
            from urllib.parse import urlparse
            if urlparse(url).hostname not in ('127.0.0.1','localhost','::1'):
                raise ValueError('Boundary ASR must be loopback-only')
            import base64,httpx
            try:
                stamps=[]
                for at in range(0,len(waves),8):
                    group=waves[at:at+8]
                    payload={'audio':[base64.b64encode(w.numpy().astype('<f4').tobytes()).decode('ascii') for w in group]}
                    response=boundary_client(url).post('/batch/parakeet_ultra',json=payload)
                    response.raise_for_status();rows=response.json()['results']
                    if len(rows)!=len(group) or any(not isinstance(r.get('timestamps'),list) for r in rows):
                        raise ValueError('Invalid boundary timestamp response')
                    stamps.extend(r['timestamps'] for r in rows)
                return stamps,'Parakeet Ultra · Photon native CUDA graphs',False
            except (httpx.HTTPError,ValueError,KeyError,TypeError):
                if not allow_local_fallback:
                    # Do not launch a second CUDA model while the producer may
                    # be capturing a new graph. Retry locally after it exits.
                    raise
        elif not allow_local_fallback:
            raise RuntimeError('Parallel verification needs the private ASR worker')
        _,stamps=self.reader.transcribe_batch(waves)
        return stamps,'Parakeet v3 target-word gate',bool(url)

    def scores(self, gates, *, allow_local_fallback=True):
        import torch
        import torchaudio
        result=[{} for _ in gates]
        active=[];waves=[]
        for i,g in enumerate(gates):
            g.last_scan=g.total
            # Silence is not affirmative evidence. Also prevents silent ASR
            # hallucinations and avoids unnecessary GPU work.
            if len(g.buffer) and float(np.mean(g.buffer**2)) > 1e-8:
                active.append(i)
                waves.append(torchaudio.functional.resample(torch.from_numpy(g.buffer),RATE,16000))
        if not waves:
            return result
        tick=time.perf_counter()
        try:
            if allow_local_fallback:
                stamps,backend,fallback=self.transcribe(waves)
            else:
                stamps,backend,fallback=self.transcribe(waves,allow_local_fallback=False)
            for i,words in zip(active,stamps):
                result[i]={'timestamps':words}
                gates[i].report.update(backend=backend,asr_fallback=fallback)
        except Exception as exc:
            # Fail closed for this check. A later check can recover. An OOM is
            # propagated so normal server error handling can release resources.
            if isinstance(exc,torch.cuda.OutOfMemoryError):
                raise
            for i in active:
                gates[i].report['asr_error']=type(exc).__name__
        elapsed=(time.perf_counter()-tick)*1000
        for i in active:
            gates[i].report['asr_calls']+=1
            gates[i].report['asr_ms']+=round(elapsed,2)
            gates[i].report['asr_batch_size']=len(active)
        return result
