"""Regression checks for real curve joins and backward-compatible SVG geometry."""
import copy
import numpy as np
import pytest
from cartoon_face.emotion_library import emotion_pose40
from cartoon_face.geometry import outline_cubics,mouth_curves
from cartoon_face.model import points,load_pose,validate_pose
from cartoon_face.renderer import render_svg
from cartoon_face.animation import interpolate_pose
from cartoon_face.reference import ROOT


def join_angles(segments):
    incoming=segments[:,3]-segments[:,2]
    outgoing=np.roll(segments[:,1]-segments[:,0],-1,axis=0)
    na=np.linalg.norm(incoming,axis=1);nb=np.linalg.norm(outgoing,axis=1)
    valid=(na>1e-5)&(nb>1e-5)
    dot=(incoming*outgoing).sum(axis=1)/np.maximum(na*nb,1e-10)
    return np.rad2deg(np.arccos(np.clip(dot[valid],-1,1)))


@pytest.mark.parametrize('component',['left_brow','right_brow','nose','left_moustache','left_eye_upper'])
def test_smooth_outline_removes_cap_kinks_without_moving_anchors(component):
    p=emotion_pose40('anger');r=p['rig'][component];anchors=points(p,component)
    old=outline_cubics(anchors,r['widths'],r['tangent_scales'])
    smooth=outline_cubics(anchors,r['widths'],r['tangent_scales'],smoothing=1)
    assert join_angles(old).max()>5
    assert join_angles(smooth).max()<.001
    assert np.max(np.linalg.norm(smooth[:-1,3]-smooth[1:,0],axis=1))<1e-8
    assert np.linalg.norm(smooth[-1,3]-smooth[0,0])<1e-8
    assert np.isfinite(smooth).all()


@pytest.mark.parametrize('slug',['surprise','awe','relief','fatigue','sourness'])
def test_o_mouth_upper_and_lower_curves_meet_tangentially(slug):
    p=emotion_pose40(slug);r=p['rig']['mouth_upper'];lr=p['rig']['mouth_lower']
    u,l,_,_=mouth_curves(points(p,'mouth_upper'),points(p,'mouth_lower'),r['tangent_scales'],[1,*lr['tangent_scales'],1],1)
    # Only the two shared corners are in scope here. Both directions match,
    # including asymmetric puckers; internal points keep their fixed identity.
    loop=np.concatenate([u,l[::-1,::-1]])
    a=loop[[3,7],3]-loop[[3,7],2];b=loop[[4,0],1]-loop[[4,0],0]
    assert np.allclose(a[:,0],0) and np.allclose(b[:,0],0)
    assert np.all((a*b).sum(axis=1)>0)


def test_zero_smoothing_keeps_legacy_svg_byte_identical():
    p=load_pose(ROOT/'poses/smile.json');q=copy.deepcopy(p)
    q['geometry']={'version':'smooth_v1','ribbon_smoothing':0.,'mouth_rounding':0.}
    assert render_svg(p)==render_svg(q)


def test_old_and_new_geometry_styles_interpolate_in_both_directions():
    old=load_pose(ROOT/'poses/smile.json');new=emotion_pose40('anger')
    for a,b in ((old,new),(new,old)):
        for t in (0.,.001,.5,.999,1.):
            p=interpolate_pose(a,b,t);validate_pose(p)
            expected=t if 'geometry' in b else 1-t
            assert p['geometry']['ribbon_smoothing']==pytest.approx(expected)
        for t,endpoint in ((0.,a),(1.,b)):
            p=interpolate_pose(a,b,t);p['name']=endpoint['name']
            assert render_svg(p)==render_svg(endpoint)


def test_geometry_contract_rejects_invalid_style_values():
    p=emotion_pose40('fear');p['geometry']['mouth_rounding']=1.1
    with pytest.raises(ValueError,match='Invalid geometry'):validate_pose(p)
