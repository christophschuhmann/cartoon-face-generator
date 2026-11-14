"""Threading/safety unit tests: scripted readers here are never production ASR."""
import threading
import numpy as np
import pytest
from streaming_boundaries import SpeechBoundaryGate,UnverifiedSpeechError,RATE
from parallel_boundaries import ParallelBoundaryStream

def pcm(s):return np.full(round(s*RATE),.2,np.float32)
def words(*items):return [{'word':w,'start':a,'end':b} for w,a,b in items]

class Reader:
    def __init__(self,transcript):self.transcript=transcript;self.calls=[]
    def scores(self,gates,**kwargs):
        self.calls.append((len(gates[0].buffer),kwargs))
        gates[0].report.update(asr_calls=1,asr_ms=1.,backend='unit-test reader')
        return [{'timestamps':self.transcript}]

def test_producer_continues_while_asr_is_blocked_and_can_outrun_six_seconds():
    entered=threading.Event();release=threading.Event();output=[]
    class Slow(Reader):
        def scores(self,gates,**kw):entered.set();assert release.wait(3);return super().scores(gates,**kw)
    g=SpeechBoundaryGate('Hello world');r=Slow(words(('Hello',.1,.3),('world',.3,.5)))
    p=ParallelBoundaryStream(g,r,lambda x,meta:output.append(x))
    try:
        assert p.feed(pcm(.72)) is False;assert entered.wait(2)
        assert p.feed(pcm(8)) is False  # neither blocks nor rejects unexamined PCM
        assert not output and not g.done
        release.set();p.finish()
        assert g.report['start_verified'] and g.report['end_verified']
        x=np.concatenate(output);assert len(x)/RATE==pytest.approx(.66,abs=1/RATE)
        assert x[0]==0 and x[-1]==0
    finally:release.set();p.close()

def test_cancellation_discards_late_asr_and_pending_audio():
    entered=threading.Event();release=threading.Event();output=[]
    class Slow(Reader):
        def scores(self,gates,**kw):entered.set();release.wait(3);return super().scores(gates,**kw)
    p=ParallelBoundaryStream(SpeechBoundaryGate('Hello world'),Slow(words(('Hello',.1,.3),('world',.3,.5))),lambda x,m:output.append(x))
    p.feed(pcm(1));assert entered.wait(2)
    closer=threading.Thread(target=p.close);closer.start()
    with p.condition:assert p.cancelled
    release.set();closer.join(3);assert not closer.is_alive() and not output

def test_wrong_audio_fails_closed_even_when_generation_has_completed():
    out=[];p=ParallelBoundaryStream(SpeechBoundaryGate('Hello world'),Reader(words(('other',.1,.3),('speech',.4,.6))),lambda x,m:out.append(x))
    try:
        p.feed(pcm(8))
        with pytest.raises(UnverifiedSpeechError):p.finish()
        assert not out
    finally:p.close()

def test_missing_middle_word_cannot_release_the_later_suffix():
    g=SpeechBoundaryGate('Please do not open the door');out=[]
    p=ParallelBoundaryStream(g,Reader(words(('Please',.1,.3),('do',.3,.5),('open',.5,.8),('the',.8,1.),('door',1.,1.2))),lambda x,m:out.append(x))
    try:
        p.feed(pcm(2));p.finish()
        assert not g.report['end_verified'] and g.report['ordered_target_words']==2
        assert len(np.concatenate(out))/RATE<=.66
        assert g.report['resume_safe'] and g.report['remaining_text']=='not open the door'
    finally:p.close()

def test_resume_does_not_split_an_original_contraction():
    g=SpeechBoundaryGate("Hello friend, don't open the door.");g.strict_order=True
    g.feed(pcm(2),{'timestamps':words(('Hello',.1,.3),('friend',.3,.5),('do',.5,.7),('open',.7,.9))})
    g.finish()
    assert not g.report.get('resume_safe')  # "do" is inside don't: ambiguous boundary

def test_resume_preserves_unheard_negation_and_written_punctuation():
    g=SpeechBoundaryGate('Bitte die Tür nicht öffnen!');g.strict_order=True
    g.feed(pcm(2),{'timestamps':words(('Bitte',.1,.3),('die',.3,.5),('Tür',.5,.7),('öffnen',.7,.9))})
    g.finish()
    assert g.report['remaining_text']=='nicht öffnen!'

def test_final_fallback_is_only_allowed_after_producer_completion():
    entered=threading.Event();release=threading.Event()
    class Flaky(Reader):
        def scores(self,gates,**kw):
            if not kw['allow_local_fallback']:
                self.calls.append((len(gates[0].buffer),kw));entered.set();release.wait(3)
                gates[0].report.update(asr_error='ConnectError');return [{}]
            return super().scores(gates,**kw)
    r=Flaky(words(('Hello',.1,.3),('world',.3,.5)));p=ParallelBoundaryStream(SpeechBoundaryGate('Hello world'),r,lambda x,m:None)
    try:
        p.feed(pcm(1));assert entered.wait(2)
        # No additional PCM after the failure: final fallback must still run.
        release.set();p.finish()
        assert r.calls[0][1]['allow_local_fallback'] is False
        assert r.calls[-1][1]['allow_local_fallback'] is True
        assert p.gate.report['end_verified']
        assert 'asr_error' not in p.gate.report
    finally:release.set();p.close()

def test_persistent_reader_error_does_not_spin_forever():
    class Failed(Reader):
        def scores(self,gates,**kw):self.calls.append(kw);gates[0].report['asr_error']='Failure';return [{}]
    r=Failed([]);p=ParallelBoundaryStream(SpeechBoundaryGate('Hello world'),r,lambda x,m:None,window_seconds=2)
    try:
        p.feed(pcm(8))
        with pytest.raises(UnverifiedSpeechError):p.finish()
        assert len(r.calls)<=2
    finally:p.close()

def test_audio_limit_is_bounded():
    p=ParallelBoundaryStream(SpeechBoundaryGate('Hello world'),Reader([]),lambda x,m:None,max_seconds=1)
    try:
        with pytest.raises(ValueError,match='limit'):p.feed(pcm(2))
    finally:p.close()

def test_weak_ending_requires_two_exact_words_on_each_side():
    text='Meine kleinen Schaltkreise summen voller Freude'
    for ending,tail,expected in [('summ',['voller','Freude'],True),('summ',['laut','Freude'],False),('schreien',['voller','Freude'],False)]:
        sequence=['Meine','kleinen','Schaltkreise',ending]+tail
        g=SpeechBoundaryGate(text);g.strict_order=True
        g.feed(pcm(4),{'timestamps':words(*[(w,.2+i*.4,.5+i*.4) for i,w in enumerate(sequence)])})
        assert g.report['end_verified']==expected

def test_negation_and_last_word_cannot_use_ending_variant():
    for target,heard in [('Ich kenne keinen lieben Menschen','Ich kenne kein lieben Menschen'),
                         ('Die Schaltkreise können summen','Die Schaltkreise können summ')]:
        g=SpeechBoundaryGate(target);g.strict_order=True
        g.feed(pcm(4),{'timestamps':words(*[(w,.2+i*.4,.5+i*.4) for i,w in enumerate(heard.split())])})
        assert not g.report['end_verified']

@pytest.mark.parametrize('dropped_boundary_words',[0,1,2])
def test_long_utterance_uses_overlapping_windows_without_skipping_words(dropped_boundary_words):
    # PCM encodes a clock only for this scripted-reader unit test.
    global_words=words(*[(f'word{i}',.2+i*.6,.5+i*.6) for i in range(45)])
    class WindowReader(Reader):
        def scores(self,gates,**kw):
            wave=gates[0].buffer;offset=round(float(wave[0])*100,3)
            end=offset+len(wave)/RATE
            self.transcript=[{**w,'start':w['start']-offset,'end':w['end']-offset}
                for w in global_words if w['start']>=offset and w['end']<=end]
            if offset>0:self.transcript=self.transcript[dropped_boundary_words:]
            return super().scores(gates,**kw)
    reader=WindowReader([]);gate=SpeechBoundaryGate(' '.join(x['word'] for x in global_words));out=[]
    p=ParallelBoundaryStream(gate,reader,lambda x,m:out.append(x))
    try:
        p.feed((np.arange(28*RATE,dtype=np.float32)/(RATE*100)).astype(np.float32));p.finish()
        assert gate.report['end_verified'] and gate.report['ordered_target_words']==45
        assert len(reader.calls)>=3 and max(n for n,_ in reader.calls)<=12*RATE
        assert len(np.concatenate(out))/RATE==pytest.approx(global_words[-1]['end']+.16-.1,abs=1/RATE)
    finally:p.close()
