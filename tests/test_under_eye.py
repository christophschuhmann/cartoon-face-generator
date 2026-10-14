import copy
import numpy as np
import pytest
from cartoon_face.emotion_library import emotion_pose40
from cartoon_face.under_eye import set_under_eye_blend
from cartoon_face.model import validate_pose,landmark_arrays
from cartoon_face.renderer import all_shapes,render_svg
from cartoon_face.animation import interpolate_pose


def test_under_eye_morph_has_permanent_slot_ids_and_continuous_geometry():
    p=emotion_pose40('contentment');original=landmark_arrays(p)[0].copy();last=None
    for phase in np.linspace(0,1,61):
        current=copy.deepcopy(p)
        for side in ('left','right'):set_under_eye_blend(current,side,float(phase))
        validate_pose(current);assert np.array_equal(landmark_arrays(current)[0],original)
        shapes={s['id']:s for s in all_shapes(current)}
        assert all(side+'_hatch_'+str(i) in shapes for side in ('left','right') for i in range(8))
        assert current['rig']['left_under_eye']['opacity']==pytest.approx(1-phase)
        assert current['rig']['left_hatching']['opacity']==pytest.approx(phase)
        if last is not None:
            assert abs(current['rig']['left_hatching']['foldness']-last)<.02
        last=phase
    for phase in (.499999,.500001):
        current=interpolate_pose(p,emotion_pose40('amusement'),phase)
        assert len([s for s in all_shapes(current) if s['id'].startswith('left_hatch_')])==8


def test_under_eye_invalid_phase_and_weights_are_rejected():
    p=emotion_pose40('anger')
    with pytest.raises(ValueError):set_under_eye_blend(p,'left',1.01)
    p['rig']['left_hatching']['slot_weights']=[1,0]
    with pytest.raises(ValueError):validate_pose(p)
