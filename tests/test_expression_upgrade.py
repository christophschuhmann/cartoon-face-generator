import copy
import math
import time
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from webcam_mapper.mapping import Observation, TemporalMapper, controls_from_signals, controls_to_pose, NEUTRAL_CONTROLS
from webcam_mapper.expressions import ExpressionMixer, PROTECTED, library, archetype_pose, aligned_face
from webcam_mapper.tongue import tongue_protrusion
from cartoon_face.projection import FaceProjection
from cartoon_face.model import validate_pose, xy, points
from cartoon_face.renderer import render_svg


def test_small_expressions_are_sensitive_and_rest_stays_still():
    assert controls_from_signals({'jawOpen': .009})['mouth_open'] == 0
    for level in (.04, .08, .15, .3):
        a = controls_from_signals({'jawOpen': level, 'browInnerUp': level,
                                  'browOuterUpLeft': level, 'browOuterUpRight': level,
                                  'mouthFrownLeft': level, 'mouthFrownRight': level})
        old = controls_from_signals({'jawOpen': level, 'browInnerUp': level,
                                    'browOuterUpLeft': level, 'browOuterUpRight': level,
                                    'mouthFrownLeft': level, 'mouthFrownRight': level},
                                   sensitivity={'brows': 1, 'frown': 1, 'speech': 1})
        assert a['mouth_open'] > old['mouth_open']
        assert a['brow_raise'] > old['brow_raise']
        assert a['smile'] < old['smile']


def test_short_tongue_and_release_hysteresis():
    # Small central protrusion, with a nearly closed jaw; no saved human image.
    rgb = np.full((400, 600, 3), (165, 125, 105), dtype=np.uint8)
    mesh = np.zeros((478, 3))
    for i, point in {61:(250,210),291:(350,210),13:(300,210),14:(300,214),17:(300,223),152:(300,330)}.items():
        mesh[i,:2] = np.array(point) / [600,400]
    rgb[211:222,255:345] = (28,16,20)
    rgb[220:225,255:345] = (180,72,85)
    assert tongue_protrusion(rgb, mesh, .06) == 0
    rgb[215:232,286:315] = (200,100,120)
    score = tongue_protrusion(rgb, mesh, .06)
    assert score > .25
    mapper = TemporalMapper(smoothing_seconds=.06)
    visible = mapper.update(Observation({}, tongue_out=score), 0)
    assert visible['tongue_out'] > .2
    assert mapper.update(Observation({}, tongue_out=0), .08)['tongue_out'] > .15
    assert mapper.update(Observation({}, tongue_out=0), .4)['tongue_out'] < .02
    mapper.reset()
    assert mapper.update(Observation({}, tongue_out=.08), 1)['tongue_out'] == 0


def test_iris_moves_behind_opening_and_highlights_have_both_clips():
    up = controls_to_pose(controls_from_signals({'eyeLookUpLeft': .9, 'eyeLookUpRight': .9}))
    for side in ('left', 'right'):
        assert xy(up, side + '_pupil_center')[1] < points(up, side + '_eye_upper')[2,1]
    root = ET.fromstring(render_svg(up, live=True))
    parents = {child: parent for parent in root.iter() for child in parent}
    for node in root.iter():
        if node.get('id') in ('left_highlight', 'right_highlight', 'left_secondary_highlight', 'right_secondary_highlight'):
            clips = [parents[node].get('clip-path'), parents[parents[node]].get('clip-path')]
            assert any('pupil_clip' in c for c in clips)
            assert any('eye_clip' in c for c in clips)


def test_curved_projection_has_depth_and_neutral_is_identity():
    points = np.array([[250.,300.], [725.,300.], [1200.,300.]])
    np.testing.assert_allclose(FaceProjection({}).points(points), points)
    turned = FaceProjection({'yaw': .7})
    q = turned.points(points)
    assert abs(np.linalg.norm(q[1]-q[0]) - np.linalg.norm(q[2]-q[1])) > 20
    assert turned.points([725, 400], nose=True)[0] > turned.points([725, 400])[0] + 40
    assert FaceProjection({'pitch': .3}).points([725,375], nose=True)[1] > 375


def test_all_100_archetypes_validate_and_cannot_override_direct_gestures():
    mixer = ExpressionMixer()
    mixer.strength = 1.
    controls = controls_from_signals({'eyeBlinkLeft': .9, 'eyeLookDownRight': .9,
                                      'tongueOut': .8, 'jawOpen': .25, 'headYaw': .6})
    observation = Observation({})
    assert len(library()) == 100
    assert sum(p['taxonomy'] == 'emonet_face_40_v1' for p in library().values()) == 40
    for index, slug in enumerate(library()):
        mixer.manual = slug
        mixed = mixer.update(None, observation, controls, index * .5)
        for key in PROTECTED: assert mixed[key] == controls[key]
        p = controls_to_pose(mixed)
        validate_pose(p)
        assert len(p['keypoints']) == 101
        validate_pose(archetype_pose(slug))
        ET.fromstring(render_svg(p, live=True))
    mixer.configure({'enabled': False})
    assert mixer.update(None, observation, controls, 100) == controls
    mixer.worker.close()


def test_stale_cnn_and_personal_reference_lifecycle():
    mixer = ExpressionMixer()
    mixer.worker.available = False  # Test state transitions without inference.
    mixer.worker.result = {'scores': np.array([0,0,0,1,0,0,0]), 'captured': time.monotonic()-2, 'ms': 4}
    assert mixer.worker.snapshot() is None
    a = controls_from_signals({'mouthSmileLeft': .8, 'mouthSmileRight': .8, 'browInnerUp': .4})
    mixer.learn('amusement')
    for i in range(8): mixer.update(None, Observation({}), a, i * .2)
    assert len(mixer.references['amusement']) == 1
    assert mixer.status['source'] == 'Dein gelerntes Mimikmuster'
    mixer.update(None, None, a, 3)
    assert mixer.status['state'] == 'no_face'
    assert not mixer.blend and mixer.worker.result is None
    assert mixer.references  # Deliberate patterns survive temporary face loss.
    mixer.worker.close()


def test_alignment_rejects_degenerate_and_small_faces():
    assert aligned_face(np.zeros((480,640,3),np.uint8), Observation({}, [(0,0,0)]*478)) is None


def test_brows_move_independently_and_negative_style_really_looks_negative():
    neutral = controls_to_pose(controls_from_signals({}))
    raised = controls_to_pose(controls_from_signals({'browOuterUpLeft': .6}))
    lowered = controls_to_pose(controls_from_signals({'browDownRight': .6}))
    assert points(raised,'left_brow')[:,1].mean() < points(neutral,'left_brow')[:,1].mean() - 15
    np.testing.assert_allclose(points(raised,'right_brow'),points(neutral,'right_brow'))
    assert points(lowered,'right_brow')[-1,1] > points(neutral,'right_brow')[-1,1] + 20
    np.testing.assert_allclose(points(lowered,'left_brow'),points(neutral,'left_brow'))
    mixer=ExpressionMixer();mixer.manual='anger';mixer.strength=.35
    smiling=controls_from_signals({'mouthSmileLeft':.5,'mouthSmileRight':.5})
    for i in range(20): mixed=mixer.update(None,Observation({}),smiling,i*.1)
    assert mixed['smile'] < -.1
    assert mixed['frown_left'] > .2 and mixed['frown_right'] > .2
    pose=controls_to_pose(mixed)
    mouth=points(pose,'mouth_upper')
    assert (mouth[0,1]+mouth[-1,1])/2 > mouth[2,1]
    mixer.strength=0
    assert mixer.update(None,Observation({}),smiling,3)==smiling
    mixer.worker.close()


def test_negative_motion_rejects_false_happy_cnn_and_lip_arc_is_not_tongue():
    mixer=ExpressionMixer(backend='fast');mixer.worker.available=False
    mixer.worker.result={'scores':np.array([.02,.01,.01,.9,.03,.02,.01]),'captured':time.monotonic(),'ms':5}
    a=controls_from_signals({'mouthFrownLeft':.6,'mouthFrownRight':.6,'mouthSmileLeft':.5,'mouthSmileRight':.5,'browDownLeft':.5,'browDownRight':.5})
    mixed=mixer.update(None,Observation({}),a,0)
    assert mixed['smile'] < -.3
    assert mixer.status['cnn']['class'] in ('angry','sad')
    mixer.worker.close()
    rgb=np.full((400,600,3),(165,125,105),np.uint8)
    mesh=np.zeros((478,3))
    for i, point in {61:(250,210),291:(350,210),13:(300,200),14:(300,223),17:(300,230),152:(300,330)}.items():mesh[i,:2]=np.array(point)/[600,400]
    rgb[201:224,255:345]=245  # teeth, with a broad lower red lip below the mesh estimate
    rgb[225:239,255:345]=(200,80,95)
    assert tongue_protrusion(rgb,mesh,.4) < .1
