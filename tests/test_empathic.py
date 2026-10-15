import numpy as np
import pytest
from webcam_mapper.empathic import HeadBank, model_ready, EXTRA_HEADS
from webcam_mapper.expressions import ExpressionMixer, library, vector
from webcam_mapper.mapping import Observation, controls_from_signals


def test_result_from_before_reset_cannot_reactivate_old_expression():
    import queue
    from webcam_mapper.empathic import EmpathicWorker
    worker=EmpathicWorker()
    worker.outgoing=queue.Queue()
    worker.clear()
    worker.outgoing.put({'state':'active','generation':worker.generation-1})
    assert worker.snapshot() is None
    assert worker.state!='active'


def test_neutral_capture_is_preserved_while_slow_encoder_is_busy(monkeypatch):
    import queue
    import time
    from webcam_mapper.empathic import EmpathicWorker
    worker=EmpathicWorker()
    from types import SimpleNamespace
    worker.process=SimpleNamespace(is_alive=lambda:True)
    worker.incoming,worker.outgoing=queue.Queue(1),queue.Queue(1)
    monkeypatch.setattr(worker,'start',lambda:None)
    observation=Observation({},[(.1,.1,0),(.9,.9,0)]*234,64,64)
    worker.last_submit=time.monotonic()
    worker.calibrate()
    worker.submit(np.zeros((64,64,3),dtype=np.uint8),observation)
    frozen=worker.incoming.get_nowait()
    assert worker.calibration_queued
    worker.submit(np.full((64,64,3),255,dtype=np.uint8),observation)
    assert worker.incoming.empty()
    worker.outgoing.put({'state':'active','generation':worker.generation,'captured':frozen[1],
                         'inference_ms':1.,'scores':{'anger':{'raw':.5,'std':1.}}})
    assert worker.snapshot()['scores']['anger']['adjusted']==0
    assert not worker.calibration_queued
    worker.last_submit=0
    worker.submit(np.full((64,64,3),255,dtype=np.uint8),observation)
    assert np.all(worker.incoming.get_nowait()[0]==255)


def test_each_of_the_forty_model_outputs_can_drive_its_matching_archetype(monkeypatch):
    controls=controls_from_signals({})
    slugs=[slug for slug,item in library().items() if item['taxonomy']=='emonet_face_40_v1']
    mixer=ExpressionMixer(backend='empathic')
    monkeypatch.setattr(mixer.worker,'submit',lambda *args:None)
    monkeypatch.setattr(mixer.worker,'snapshot',lambda:None)
    monkeypatch.setattr(mixer.empathic,'submit',lambda *args:None)
    for slug in slugs:
        mixer.reset()
        scores={name:{'raw':3.3 if name==slug else 0.,'adjusted':3.3 if name==slug else 0.,
                      'standardized':3.3 if name==slug else 0.,'std':1.} for name in slugs}
        result={'scores':scores,'age_seconds':1.,'inference_ms':1000.,'signature':vector(controls).tolist()}
        monkeypatch.setattr(mixer.empathic,'snapshot',lambda result=result:result)
        mixer.update(None,Observation({}),controls,1.)
        assert mixer.status['archetype_slug']==slug
        assert len(mixer.status['empathic']['scores'])==40
        assert mixer.status['effective_strength']>0


@pytest.mark.parametrize('variant',['small','large'])
def test_installed_head_banks_have_exact_taxonomy_and_finite_scores(variant):
    if not model_ready(variant):pytest.skip('Optional model not installed')
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=1):
        bank=HeadBank(variant)
        embedding=np.random.default_rng(91).normal(size=1152).astype(np.float32)
        embedding/=np.linalg.norm(embedding)
        result=bank.infer(embedding)
    expected={s for s,i in library().items() if i['taxonomy']=='emonet_face_40_v1'}
    assert set(result)==expected
    assert set(result).isdisjoint(EXTRA_HEADS)
    assert all(np.isfinite(s['raw']) for s in result.values())
    with pytest.raises(ValueError):bank.infer(np.full(1152,np.nan))


def test_stale_estimate_loses_influence_if_current_expression_has_changed(monkeypatch):
    controls=controls_from_signals({})
    mixer=ExpressionMixer(backend='empathic')
    monkeypatch.setattr(mixer.worker,'submit',lambda *args:None)
    monkeypatch.setattr(mixer.worker,'snapshot',lambda:None)
    monkeypatch.setattr(mixer.empathic,'submit',lambda *args:None)
    scores={s:{'raw':3.3 if s=='amusement' else 0.,'adjusted':3.3 if s=='amusement' else 0.,
               'standardized':0.,'std':1.} for s,i in library().items() if i['taxonomy']=='emonet_face_40_v1'}
    result={'scores':scores,'age_seconds':12.,'inference_ms':12000.,'signature':vector(controls).tolist()}
    monkeypatch.setattr(mixer.empathic,'snapshot',lambda:result)
    mixer.update(None,Observation({}),controls,1.)
    matching=mixer.status['effective_strength']
    mixer.reset()
    result['signature']=(vector(controls)+1).tolist()
    mixer.update(None,Observation({}),controls,2.)
    assert mixer.status['effective_strength']<matching*.1

