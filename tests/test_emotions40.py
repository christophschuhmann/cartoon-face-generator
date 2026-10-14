import copy,json
from pathlib import Path
import numpy as np
import pytest
from cartoon_face.emotion_library import catalog,emotion_pose40,mix_emotions,resolve_emotion,compatibility
from cartoon_face.emotion_validation import cue_checks,geometric_features
from cartoon_face.model import validate_pose,save_pose,load_pose,landmark_arrays,topology
from cartoon_face.renderer import render_svg,rasterize,shape_xml
from cartoon_face.components import render_eye,eye_opening

SLUGS=[p['slug'] for p in catalog()['profiles']]


def test_exact_published_taxonomy_order_and_stable_ids():
    source=catalog()['source']
    assert len(SLUGS)==40 and len(set(SLUGS))==40
    assert [p['id'] for p in catalog()['profiles']]==list(range(1,41))
    assert [p['label'] for p in catalog()['profiles']]==source['labels']
    assert len(source['source_commit'])==40 and len(source['source_sha256'])==64
    assert resolve_emotion('neutral')['id'] is None

@pytest.mark.parametrize('slug',SLUGS)
def test_archetypes_and_variations_keep_authoring_cues(slug):
    for seed in (None,7,42):
        p=emotion_pose40(slug,seed,.85);validate_pose(p)
        check=cue_checks(p);assert check['passed'],check['failures']
        xy,states=landmark_arrays(p);assert xy.shape==(101,2) and states.shape==(101,)
        assert p['emotion']['weights'][resolve_emotion(slug)['id']-1]==1
        assert p['emotion']['human_validated'] is False
        for side in ('left','right'):
            assert p['rig'][side+'_eye_upper']['opacity']==1
            assert p['rig'][side+'_moustache']['opacity']==1
    assert render_svg(emotion_pose40(slug,42))==render_svg(emotion_pose40(slug,42))


def test_svg_roundtrip_and_arrays_ignore_json_key_order(tmp_path):
    p=emotion_pose40('envy',12);save_pose(p,tmp_path/'envy.json')
    assert render_svg(p)==render_svg(load_pose(tmp_path/'envy.json'))
    a,v=landmark_arrays(p);p['keypoints']=dict(reversed(list(p['keypoints'].items())))
    b,w=landmark_arrays(p);assert np.array_equal(a,b) and np.array_equal(v,w)
    p['canvas']={'width':2900,'height':1500};pixels,_=landmark_arrays(p,pixels=True)
    assert np.allclose(pixels,a*[2900,1500])


def test_variations_differ_but_stay_within_same_target():
    a=emotion_pose40('sadness',1);b=emotion_pose40('sadness',2)
    assert not np.allclose(landmark_arrays(a)[0],landmark_arrays(b)[0])
    assert a['emotion']['weights']==b['emotion']['weights']
    assert cue_checks(a)['passed'] and cue_checks(b)['passed']


def test_mixture_soft_labels_and_geometry_endpoints():
    from cartoon_face.animation import interpolate_pose
    a=emotion_pose40('gratitude');b=emotion_pose40('affection')
    for t in np.linspace(0,1,31):
        p=mix_emotions('gratitude','affection',float(t));validate_pose(p)
        assert sum(p['emotion']['weights'])==pytest.approx(1)
        assert p['emotion']['weights'][4]==pytest.approx(1-t)
        assert p['emotion']['weights'][5]==pytest.approx(t)
    assert np.array_equal(landmark_arrays(mix_emotions('gratitude','affection',0))[0],landmark_arrays(a)[0])
    assert np.array_equal(landmark_arrays(mix_emotions('gratitude','affection',1))[0],landmark_arrays(b)[0])
    p=interpolate_pose(a,b,.4);assert len(p['emotion']['weights'])==40
    assert p['recipe']['kind']=='interpolation'
    assert compatibility('anger','elation')['kind']=='ambivalent'


def test_intensity_zero_is_neutral_geometry_and_zero_label_vector():
    neutral=emotion_pose40('neutral');zero=emotion_pose40('anger',intensity=0)
    assert np.array_equal(landmark_arrays(neutral)[0],landmark_arrays(zero)[0])
    assert sum(zero['emotion']['weights'])==0


def test_rotated_pupil_stays_inside_stationary_lid_clip():
    # Regression: rotating the ellipse used to rotate the mask too, creating
    # triangular pupil fragments outside narrow eyelids.
    p=emotion_pose40('contentment');side='left';p['rig'][side+'_pupil']['angle']=45
    pupil=next(s for s in render_eye(p,side) if s['id']==side+'_pupil')
    opening=eye_opening(p,side)
    prefix='<svg xmlns="http://www.w3.org/2000/svg" width="725" height="375" viewBox="0 0 1450 750"><rect width="1450" height="750" fill="white"/>'
    clipped=prefix+f'<defs><clipPath id="left_eye_clip"><path d="{opening}"/></clipPath></defs>'+shape_xml(pupil)+'</svg>'
    aperture=prefix+f'<path d="{opening}" fill="black"/></svg>'
    iris=np.asarray(rasterize(clipped).convert('L'))<80;mask=np.asarray(rasterize(aperture).convert('L'))<230
    assert iris.sum()>300
    assert np.sum(iris&~mask)<3
