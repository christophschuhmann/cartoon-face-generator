import copy
import json
from pathlib import Path
import numpy as np
import pytest
from webcam_mapper.audio_timeline import group_words,loudness_envelope,audible_words
from webcam_mapper.audio_animation import PATTERNS,canonical_scores,performance_controls,prepare_performance,expression_mix
from webcam_mapper.mapping import controls_from_signals,controls_to_pose
from cartoon_face.emotion_library import catalog
from cartoon_face.model import points,validate_pose

def raw_scores(slug):
    # Test all official names, including the audio-specific 'and Envy' spelling.
    names=json.loads((Path(__file__).parents[1]/'webcam_mapper/models/ears/training_normalization.json').read_text())['score_names'][:40]
    raw=dict.fromkeys(names,0.)
    for name in raw:
        test=dict(raw);test[name]=3.2
        if canonical_scores(test)[slug]>0:raw[name]=3.2;break
    return raw

def test_word_groups_preserve_timestamps_and_never_cross_pauses():
    words=[{'word':str(i),'start':s,'end':s+.15} for i,s in enumerate([1,1.2,1.4,1.6,3,3.2])]
    actual,segments=group_words({'segments':[{'words':words}]},4)
    assert actual==words
    assert [len(s['words']) for s in segments]==[3,1,2]
    assert segments[0]['start']==1 and segments[2]['start']==3

def test_audio_silence_and_relative_loudness():
    wave=np.r_[np.zeros(16000),np.ones(16000)*.02,np.ones(16000)*.2,np.zeros(16000)]
    env=loudness_envelope(wave)
    assert env['values'][10]==env['values'][160]==0
    assert 0<env['values'][70]<env['values'][120]
    assert not audible_words([{'start':0.,'end':.9}],env)

def test_exact_40_coverage_and_distinct_authored_patterns():
    assert set(PATTERNS)=={p['slug'] for p in catalog()['profiles']}
    assert len(set(PATTERNS.values()))==40
    for slug in PATTERNS:
        c,pattern,ranked,_,intensity=performance_controls({'scores_raw':raw_scores(slug),'arousal':.75,'valence':0})
        assert ranked[0]==slug and intensity>.5 and c['mouth_open']==0
        validate_pose(controls_to_pose(c))

def test_subtle_frown_squint_and_unilateral_brow_are_readable():
    neutral=controls_to_pose(controls_from_signals({}))
    f=controls_from_signals({'mouthFrownLeft':.08,'mouthFrownRight':.08,'mouthSmileLeft':.06})
    assert f['smile']<-.2
    m=points(controls_to_pose(f),'mouth_upper');assert (m[0,1]+m[-1,1])/2>m[2,1]+12
    s=controls_from_signals({'eyeSquintLeft':.5});assert s['eye_open']+s['eye_asym']/2<.60
    assert s['eye_open']-s['eye_asym']/2>.95
    a=controls_from_signals({'browOuterUpLeft':.4,'browInnerUp':.45},
      {'browHeightLeft':.5,'browHeightRight':.5,'browInnerHeightLeft':.5,'browInnerHeightRight':.5})
    assert a['brow_raise_left']>a['brow_raise_right']+.4
    pout=controls_from_signals({'mouthPucker':.6,'mouthShrugLower':.6})
    assert pout['lip_pout']>.5 and pout['tongue_out']==0

def test_negative_audio_archetype_cannot_become_friendly_from_valence_bias():
    for slug in ('anger','sadness','disgust'):
        c,*_=performance_controls({'scores_raw':raw_scores(slug),'arousal':.8,'valence':1.})
        assert c['smile']<0


def scored_segment(scores,styles=None):
    values=dict.fromkeys(PATTERNS,0.);values.update(scores)
    return dict(scores_raw=dict(values),scores_z=values,arousal=.8,valence=.37,
                styles={key:{'z':value} for key,value in (styles or {}).items()})


def test_aggressive_delivery_survives_overlapping_elation_and_triumph():
    # Regression for the conflicting scores measured on 7108.mp3: anger was
    # previously discarded before speaking style could influence the expression.
    segment=scored_segment(dict(triumph=3.71,elation=2.92,hope=2.55,anger=1.77,impatience=2.16),
                           dict(ranting=1.75,tension=2.75,attack=3.36))
    original=copy.deepcopy(segment)
    c,_,ranked,_,_=performance_controls(segment)
    assert segment==original and ranked[0]=='triumph'  # Keep measured scores honest.
    assert c['smile']<-.3 and c['brow_inner_left']<-.28
    assert c['frown_left']>.6 and c['eye_open']<.8 and c['cheek_lift']<.1
    assert expression_mix(segment)['negative']>.8
    for opening in (0.,.3,.6):
        pose=controls_to_pose(dict(c,mouth_open=opening))
        m=points(pose,'mouth_upper')
        assert (m[0,1]+m[-1,1])/2>m[2,1]+12  # Downturned even while talking.


def test_happy_ranting_and_loudness_alone_do_not_create_anger():
    segment=scored_segment(dict(triumph=3.7,elation=2.9,hope=2.5),
                           dict(ranting=3,tension=4,attack=4))
    c,*_=performance_controls(segment)
    assert expression_mix(segment)['aggression']==0
    assert c['smile']>.7 and c['frown_left']<.1
    calm=performance_controls(dict(segment,styles={}))[0]
    assert all(c[key]==calm[key] for key in ('smile','frown_left','brow_inner_left','eye_open'))
    assert c['eye_open']>.9 and c['cheek_lift']>.5


def test_sadness_fear_and_disgust_keep_distinct_negative_expressions():
    controls={slug:performance_controls(scored_segment({slug:3.4}))[0]
              for slug in ('sadness','fear','disgust','anger')}
    sad,fear,disgust,angry=(controls[k] for k in ('sadness','fear','disgust','anger'))
    assert sad['smile']<-.6 and sad['brow_inner_left']>.7
    assert fear['brow_inner_left']>.7 and fear['eye_open']>1.2 and fear['smile']<-.3
    assert disgust['nose_lift']>.7 and disgust['squint_left']>.2
    assert angry['brow_inner_left']<-.4 and angry['eye_open']<.8


def test_prepared_performance_keeps_model_scores_and_explains_acting_mix():
    segment=scored_segment(dict(triumph=3.71,elation=2.92,hope=2.55,anger=1.77,impatience=2.16),
                           dict(ranting=1.75,tension=2.75,attack=3.36))
    result=prepare_performance({'segments':[segment]})['segments'][0]
    assert result['dominant']=='triumph' and result['model_label']=='Triumph'
    assert result['performance_dominant'] in ('anger','impatience')
    assert result['affect']['aggression']>.45
    assert len(result['poses'])==2 and len(result['scores'])==40


def test_redux_uses_q8_and_separate_silero_and_normalizes_words(monkeypatch):
    from webcam_mapper import audio_inference
    from types import SimpleNamespace
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=0,stdout=json.dumps({'words':[{'w':'Hallo','start':.4,'end':.8}]}))
    monkeypatch.setattr(audio_inference.subprocess,'run',run)
    result=audio_inference.transcribe_redux(Path('test.wav'),8.)
    command,options=calls[0]
    assert Path(command[command.index('--model')+1]).name=='redux-q8.gguf'
    assert Path(command[command.index('--vad-model')+1]).name=='redux-bundle.gguf'
    assert '--component' not in command
    assert options['env']['PARAKEET_DEVICE']=='cpu'
    assert result['segments'][0]['words']==[{'word':'Hallo','start':.4,'end':.8}]


def test_audio_readiness_requires_successful_runtime_verification(monkeypatch,tmp_path):
    from webcam_mapper import audio_jobs
    monkeypatch.setattr(audio_jobs,'ROOT',tmp_path)
    jobs=audio_jobs.AudioJobs()
    for name in jobs.readiness()['missing']:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
    assert not jobs.readiness()['ready']
    marker=tmp_path/'webcam_mapper/models/audio_runtime_verified.json'
    marker.write_text(json.dumps({'runtime':'redux-q8-ears-script-v1'}))
    assert jobs.readiness()['ready']
    medium=tmp_path/'webcam_mapper/models/ears/medium';medium.mkdir(parents=True)
    for name in ('scores_cpu.pt','runtime_verification.json','speech_reference.json'):(medium/name).touch()
    (medium/'inference_verified.json').write_text('{}')
    assert not jobs.readiness()['variants']['medium']
    (medium/'inference_verified.json').write_text(json.dumps({'runtime':'redux-q8-ears-script-v1','normalization':'medium-speech-80265-mean-std'}))
    assert jobs.readiness()['variants']['medium']
    (tmp_path/'webcam_mapper/models/parakeet-redux/redux-q8.gguf').unlink()
    assert not jobs.readiness()['ready']
    assert not jobs.readiness()['variants']['medium']


def test_reference_normalization_promotes_distinctive_anger_over_high_baseline_interest():
    from webcam_mapper.audio_scores import normalize_scores,medium_reference
    root=Path(__file__).parents[1]/'webcam_mapper/models/ears'
    reference=medium_reference()
    scores={key:row['mean'] for key,row in reference.items() if row.get('mean') is not None}
    scores['emo_Anger']+=2*reference['emo_Anger']['std']
    scores['vn_S_RANT_reg']+=2.5*reference['vn_S_RANT_reg']['std']
    display=json.loads((root/'display_normalization.json').read_text())
    segment=normalize_scores(scores,display,'medium')
    assert segment['scores_raw']['emo_Anger']<segment['scores_raw']['emo_Interest']
    assert segment['scores_z']['emo_Anger']==pytest.approx(2)
    assert segment['styles']['ranting']['z']==pytest.approx(2.5)
    controls,pattern,ranked,*_=performance_controls(segment)
    assert ranked[0]=='anger' and controls['smile']<0
    calmer=copy.deepcopy(segment);calmer['styles']['ranting']['z']=0
    assert pattern[1]>performance_controls(calmer)[1][1]


def test_eye_position_uses_both_eyes_without_expression_state():
    from webcam_mapper.viewer import eye_position
    from webcam_mapper.mapping import Observation
    landmarks=np.zeros((478,3));landmarks[[33,133,362,263],:2]=[.7,.3]
    assert eye_position(Observation({},landmarks.tolist()))=={'x':.7,'y':.3}
    assert eye_position(None) is None
