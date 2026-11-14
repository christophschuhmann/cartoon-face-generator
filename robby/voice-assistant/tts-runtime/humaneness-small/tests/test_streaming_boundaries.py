import numpy as np
import pytest
from streaming_boundaries import SpeechBoundaryGate, UnverifiedSpeechError
R=48000
def pcm(seconds):return np.ones(round(seconds*R),np.float32)*.2
def score(words):return {'timestamps':[dict(word=w,start=a,end=b) for w,a,b in words]}
def test_wrong_speech_never_opens_or_falls_back_to_forced_alignment():
    g=SpeechBoundaryGate('Hallo meine Freunde')
    assert not len(g.feed(pcm(2),score([('unrelated',.1,.5),('words',.6,1.)])))
    with pytest.raises(UnverifiedSpeechError):g.finish(pcm(2))
    assert g.emitted==0

def test_first_word_alone_does_not_open_two_word_target():
    g=SpeechBoundaryGate('Hallo meine Freunde')
    assert not len(g.feed(pcm(1),score([('Hallo',.1,.4)])))
    assert g.start is None

def test_fast_worker_outage_and_malformed_response_use_real_fallback(monkeypatch):
    import torch,httpx
    from unittest.mock import Mock
    from streaming_boundaries import BoundaryASR
    import streaming_boundaries
    monkeypatch.setenv('SMALL_BOUNDARY_ASR_URL','http://127.0.0.1:8822')
    reader=BoundaryASR(None)
    words=[{'word':'Hallo','start':.1,'end':.3}]
    reader.reader.transcribe_batch=Mock(return_value=(['Hallo'],[words]))
    client=Mock();monkeypatch.setattr(streaming_boundaries,'boundary_client',lambda url:client)
    for failure in (httpx.ConnectError('offline'),None):
        client.post.side_effect=failure
        client.post.return_value.json.return_value={'results':[]}
        stamps,backend,fallback=reader.transcribe([torch.ones(16000)])
        assert stamps==[words] and fallback and 'v3' in backend
    assert reader.reader.transcribe_batch.call_count==2

def test_fast_worker_cannot_send_private_pcm_to_remote_host(monkeypatch):
    import torch
    from streaming_boundaries import BoundaryASR
    monkeypatch.setenv('SMALL_BOUNDARY_ASR_URL','https://untrusted.example')
    with pytest.raises(ValueError):BoundaryASR(None).transcribe([torch.ones(16000)])

def test_lead_is_removed_fade_and_tail_use_original_coordinates():
    g=SpeechBoundaryGate('Hallo meine Freunde')
    words=[('blah',.1,.4),('Hallo',1.,1.3),('meine',1.4,1.6),('Freunde',1.8,2.1),('blah',2.6,2.9)]
    out=g.feed(pcm(3),score(words))
    assert g.report['start_verified'] and g.report['end_verified']
    assert g.report['removed_leading_seconds']==pytest.approx(.9)
    assert len(out)/R==pytest.approx(1.36,abs=1/R)
    assert out[0]==0 and out[-1]==0 and out[6000]==pytest.approx(.2)
    assert g.done and not len(g.finish())

def test_one_word_sentence_can_open_and_finish():
    g=SpeechBoundaryGate('Tschüss!')
    result=g.feed(pcm(.8),score([('Tschüss',.2,.5)]))
    assert len(result) and g.report['end_verified']

def test_contractions_numbers_and_punctuation_are_normalized():
    g=SpeechBoundaryGate("Mir geht's gut.")
    out=g.feed(pcm(2),score([('Mir',.1,.3),('geht',.3,.5),('es',.5,.7),('gut',.7,1.)]))
    assert len(out) and g.report['end_verified']
    g=SpeechBoundaryGate('Zwei kleine Roboter')
    out=g.feed(pcm(2),score([('2',.1,.3),('kleine',.3,.6),('Roboter',.6,1.)]))
    assert len(out) and g.report['end_verified']

def test_minor_spelling_error_needs_three_exact_adjacent_words():
    g=SpeechBoundaryGate('Christoph ich freue mich sehr')
    out=g.feed(pcm(2),score([('Christof',.1,.4),('ich',.4,.6),('freue',.6,.9),('mich',.9,1.1),('sehr',1.1,1.3)]))
    assert len(out) and g.report['opening_match']=='four_word_spelling_anchor'
    g=SpeechBoundaryGate('Christoph ich freue mich sehr')
    assert not len(g.feed(pcm(2),score([('Christof',.1,.4),('ich',.4,.6)])))

def test_missing_negation_or_unrelated_prefix_cannot_open_gate():
    for words in [[('Das',.1,.3),('ist',.3,.5),('gut',.5,.7)],
                  [('Ganz',.1,.3),('andere',.3,.5),('Worte',.5,.7)]]:
        g=SpeechBoundaryGate('Nicht das ist mein Ziel')
        assert not len(g.feed(pcm(2),score(words)))
        with pytest.raises(UnverifiedSpeechError):g.finish()

def test_continuous_job_retries_without_replaying_other_jobs():
    import queue,threading
    from live_batch import ContinuousBatch,Utterance
    events=[];batch=ContinuousBatch(None,None,queue.Queue(),events.append,threading.Event())
    s=Utterance('bad',{},0,gate=SpeechBoundaryGate('Hello world'),align=True)
    s.gate.feed(pcm(6));batch.complete(s)
    assert events[0]['event']=='speech_retry' and events[0]['attempt']==2
    assert batch.pending[0].id=='bad' and batch.pending[0].attempt==2
    s.attempt=3;batch.complete(s)
    assert events[-1]['event']=='job_error'

def test_silence_and_asr_error_do_not_release_unverified_pcm():
    g=SpeechBoundaryGate('Good morning')
    assert not len(g.feed(np.zeros(R,np.float32),{}))
    assert not len(g.feed(pcm(1),{}))
    assert g.due(final=True)

def test_repeated_ending_does_not_cut_before_complete_sentence():
    g=SpeechBoundaryGate('Hallo du schön dich zu sehen ich freue mich dich zu sehen')
    early=[('Hallo',.1,.3),('du',.3,.5),('schön',.5,.7),('dich',.7,.9),('zu',.9,1.),('sehen',1.,1.3)]
    g.feed(pcm(1.8),score(early))
    assert not g.report['end_verified'] and not g.done

def test_tail_uncertainty_keeps_only_verified_speech():
    g=SpeechBoundaryGate('Das ist eine lange Geschichte')
    out=g.feed(pcm(3),score([('Das',.2,.4),('ist',.4,.6),('eine',.6,.8),('Quatsch',1.,2.)]))
    tail=g.finish()
    assert len(out)+len(tail)<R
    assert not g.report['end_verified'] and tail[-1]==0

def test_no_opening_has_bounded_wait():
    g=SpeechBoundaryGate('Hallo Robbie')
    assert not len(g.feed(pcm(6),{})) and g.done
    with pytest.raises(UnverifiedSpeechError):g.finish()

def test_disabled_is_exact_passthrough():
    x=pcm(.4);g=SpeechBoundaryGate('Hallo Robbie',False)
    assert np.array_equal(g.feed(x,{}),x) and not len(g.finish())

def test_intentional_burst_still_waits_for_words_then_preserves_lead():
    g=SpeechBoundaryGate('Hallo Robbie',preserve_lead=True)
    assert not len(g.feed(pcm(.7),{}))
    out=g.feed(pcm(.7),score([('Hallo',.8,1.),('Robbie',1.,1.2)]))
    assert len(out) and out[0]==pytest.approx(.2) and g.start==0

def test_nonfinite_timestamps_cannot_open_gate():
    g=SpeechBoundaryGate('Hello world')
    assert not len(g.feed(pcm(1),score([('Hello',float('nan'),.2),('world',.3,.5)])))

def test_scheduler_batches_due_asr_and_never_publishes_unverified_opening():
    import queue,threading
    from live_batch import ContinuousBatch,Utterance
    class Reader:
        def __init__(self):self.batches=[]
        def scores(self,gates):
            self.batches.append(len(gates))
            for g in gates:g.last_scan=g.total
            return [score([('Hello',.2,.4),('world',.4,.6)]) for g in gates]
    reader=Reader();events=[]
    batch=ContinuousBatch(None,None,queue.Queue(),events.append,threading.Event(),boundary_asr=reader)
    states=[Utterance(str(i),{},i,gate=SpeechBoundaryGate('Hello world')) for i in range(2)]
    for s in states:
        assert not len(s.gate.feed(pcm(1)))
    batch.check_boundaries(states)
    assert reader.batches==[2]
    assert len(events)==2 and all(e['live_alignment']['start_verified'] for e in events)
    assert all(len(e['_wave']) for e in events)

def test_cancelled_utterance_cannot_emit_held_audio():
    import queue,threading
    from live_batch import ContinuousBatch,Utterance
    events=[]
    batch=ContinuousBatch(None,None,queue.Queue(),events.append,threading.Event())
    s=Utterance('s',{},0,cancelled=True,gate=SpeechBoundaryGate('Hello world'))
    s.gate.feed(pcm(1))
    batch.complete(s)
    assert len(events)==1 and events[0]['event']=='job_done' and events[0]['cancelled']

def test_after_opening_checks_are_throttled_without_releasing_unknown_tail():
    g=SpeechBoundaryGate('Hello world this is a longer sentence')
    g.feed(pcm(1),score([('Hello',.2,.4),('world',.4,.6)]))
    g.last_scan=g.total
    g.feed(pcm(.4))
    assert g.cursor <= int(.66*R)
    assert not g.due()
    g.feed(pcm(.4))
    assert g.due()

def test_large_admission_failure_preserves_working_small(monkeypatch):
    import contextlib
    from types import SimpleNamespace
    import small_app
    from fastapi import HTTPException
    current=SimpleNamespace(model_id='small_rl')
    state={'engine':current,'phase':'ready','error':None}
    monkeypatch.setattr(small_app,'STATE',state)
    monkeypatch.setattr(small_app.torch.cuda,'device',lambda *a:contextlib.nullcontext())
    monkeypatch.setattr(small_app.torch.cuda,'empty_cache',lambda:None)
    monkeypatch.setattr(small_app.torch.cuda,'mem_get_info',lambda:(4*1024**3,24*1024**3))
    with pytest.raises(HTTPException) as error:small_app.switch_acting_model('large17')
    assert error.value.status_code==409
    assert state['engine'] is current and state['phase']=='ready' and state['error'] is None
