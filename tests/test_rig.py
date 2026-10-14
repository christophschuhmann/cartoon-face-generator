import copy,json
from pathlib import Path
import numpy as np
import pytest
from cartoon_face.model import topology,load_pose,save_pose,validate_pose,points,refresh_states
from cartoon_face.reference import ROOT,NAMES
from cartoon_face.renderer import render_svg,rasterize
from cartoon_face.animation import interpolate_pose
from cartoon_face.expressions import emotion_pose,apply_controls,set_variant,EMOTIONS
from cartoon_face.geometry import outline_cubics

@pytest.mark.parametrize('name',NAMES)
def test_pose_roundtrip_exact_svg(name,tmp_path):
    p=load_pose(ROOT/f'poses/{name}.json');save_pose(p,tmp_path/'pose.json')
    assert render_svg(p)==render_svg(load_pose(tmp_path/'pose.json'))
    assert [k['id'] for k in p['keypoints'].values()]==list(range(101))
    assert len(p['keypoints'])==len(topology()['keypoints'])

@pytest.mark.parametrize('name',NAMES)
def test_anatomical_left_right(name):
    p=load_pose(ROOT/f'poses/{name}.json')
    for side,sign in [('left',1),('right',-1)]:
        upper=points(p,side+'_eye_upper');lower=points(p,side+'_eye_lower');brow=points(p,side+'_brow')
        assert sign*(upper[-1,0]-upper[0,0])>150
        assert sign*(lower[-1,0]-lower[0,0])>150
        assert sign*(brow[0,0]-brow[-1,0])>150

@pytest.mark.parametrize('name',EMOTIONS)
def test_novel_emotions_have_finite_visible_core(name):
    p=emotion_pose(name);validate_pose(p);svg=render_svg(p)
    assert 'nan' not in svg.lower() and 'inf' not in svg.lower()
    for side in ('left','right'):
        assert p['rig'][side+'_eye_upper']['opacity']==1
        assert p['rig'][side+'_moustache']['opacity']==1
    a=np.asarray(rasterize(svg).convert('L'))
    assert .02<np.mean(a<128)<.18
    if name in ('wink','sleepy'):
        assert p['keypoints']['left_pupil_center']['state']=='occluded'

@pytest.mark.parametrize('pair',[('smile','tongue'),('tense','love'),('cheeky','skeptical')])
def test_interpolation_fixed_labels_and_smooth_steps(pair):
    a,b=[load_pose(ROOT/f'poses/{n}.json') for n in pair];last=None
    for t in np.linspace(0,1,32):
        p=interpolate_pose(a,b,t);validate_pose(p)
        arr=np.array([k['xy'] for k in p['keypoints'].values()])
        assert list(p['keypoints'])==list(a['keypoints'])
        if last is not None:assert np.linalg.norm(arr-last,axis=1).max()<.035
        last=arr
        for side in ('left','right'):
            r=p['rig'][side+'_moustache'];s=outline_cubics(points(p,side+'_moustache'),r['widths'],r['tangent_scales'])
            assert np.isfinite(s).all()
            assert np.max(np.linalg.norm(s[:-1,3]-s[1:,0],axis=1))<1e-5
            assert np.linalg.norm(s[-1,3]-s[0,0])<1e-5


def test_discrete_interior_fades_through_zero():
    a,b=[load_pose(ROOT/f'poses/{n}.json') for n in ('tense','love')]
    assert interpolate_pose(a,b,.5)['rig']['mouth_upper']['fill_opacity']==0
    assert interpolate_pose(a,b,.499)['rig']['mouth_upper']['fill_opacity']<.01
    assert interpolate_pose(a,b,.501)['rig']['mouth_upper']['fill_opacity']<.01


def test_validation_rejects_corrupt_ids_and_nonfinite():
    p=load_pose(ROOT/'poses/smile.json');p['keypoints']['left_pupil_center']['id']=900
    with pytest.raises(ValueError):validate_pose(p)
    p=load_pose(ROOT/'poses/smile.json');p['rig']['left_moustache']['widths'][0]=float('nan')
    with pytest.raises(ValueError):validate_pose(p)


def test_render_resolution_corresponds_to_normalized_labels():
    p=load_pose(ROOT/'poses/smile.json');p['canvas']={'width':768,'height':432}
    svg=render_svg(p);im=rasterize(svg)
    assert im.size==(768,432)
    assert 'preserveAspectRatio="none"' in svg
    assert tuple(np.asarray(im)[0,0])==(255,255,255)


def test_modes_toggle_only_fixed_components():
    p=load_pose(ROOT/'poses/smile.json');keys=list(p['keypoints'])
    set_variant(p,'left_under_eye','hatching')
    assert p['rig']['left_under_eye']['opacity']==0 and p['rig']['left_hatching']['opacity']==1
    assert p['keypoints']['left_under_eye_center']['state']=='absent'
    assert list(p['keypoints'])==keys


@pytest.mark.parametrize('name',NAMES)
def test_hatching_stays_on_its_anatomical_side(name):
    p=load_pose(ROOT/f'poses/{name}.json')
    assert np.all(points(p,'left_hatching')[:,0]>725)
    assert np.all(points(p,'right_hatching')[:,0]<725)


def test_squint_alone_deforms_both_lids():
    p=load_pose(ROOT/'poses/smile.json');q=apply_controls(p,{'left_squint':.7})
    assert not np.allclose(points(p,'left_eye_upper'),points(q,'left_eye_upper'))
    assert not np.allclose(points(p,'left_eye_lower'),points(q,'left_eye_lower'))


def test_absent_reflex_stays_absent_during_blink():
    p=load_pose(ROOT/'poses/smile.json');q=apply_controls(p,{'left_eye_openness':0})
    assert q['keypoints']['left_pupil_center']['state']=='occluded'
    assert q['keypoints']['left_secondary_highlight_center']['state']=='absent'


def test_reflex_center_outside_pupil_is_occluded():
    from cartoon_face.model import set_xy,xy
    p=load_pose(ROOT/'poses/smile.json')
    set_xy(p,'left_highlight_center',xy(p,'left_pupil_center')+[130,0]);refresh_states(p)
    assert p['keypoints']['left_highlight_center']['state']=='occluded'


@pytest.mark.parametrize('name',NAMES)
def test_reconstruction_quality_against_real_reference(name):
    from PIL import Image
    from cartoon_face.evaluation import metrics
    p=load_pose(ROOT/f'poses/{name}.json')
    m=metrics(Image.open(ROOT/f'output/references/{name}.png'),rasterize(render_svg(p)))
    assert m['foreground_iou']>.82
    assert m['dice']>.90


def test_dataset_seed_is_reproducible(tmp_path):
    from cartoon_face.dataset import generate_dataset
    a=generate_dataset(2,42,tmp_path/'a');b=generate_dataset(2,42,tmp_path/'b')
    assert [e['sha256_svg'] for e in a['samples']]==[e['sha256_svg'] for e in b['samples']]
    assert a['all_valid']
