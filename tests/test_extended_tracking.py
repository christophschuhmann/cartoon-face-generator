"""Head-pose conventions, independent gaze/winks and conservative tongue cues."""
import math
import re
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from webcam_mapper.mapping import (Observation, TemporalMapper, head_signals,
    controls_from_signals, controls_to_pose)
from webcam_mapper.tongue import tongue_protrusion
from cartoon_face.renderer import render_svg
from cartoon_face.model import xy, validate_pose


def rotation(pitch=0, yaw=0, roll=0):
    x,y,z=pitch,yaw,roll
    rx=np.array([[1,0,0],[0,math.cos(x),-math.sin(x)],[0,math.sin(x),math.cos(x)]])
    ry=np.array([[math.cos(y),0,math.sin(y)],[0,1,0],[-math.sin(y),0,math.cos(y)]])
    rz=np.array([[math.cos(z),-math.sin(z),0],[math.sin(z),math.cos(z),0],[0,0,1]])
    matrix=np.eye(4);matrix[:3,:3]=rz@ry@rx
    return matrix.tolist()


def test_head_pose_extraction_and_neutral_calibration():
    result=head_signals(rotation(.2,-.3,.15))
    assert result == pytest.approx({'headPitch':.2,'headYaw':-.3,'headRoll':-.15})
    assert head_signals(np.full((4,4),np.nan)) == {}
    mapper=TemporalMapper(smoothing_seconds=0)
    mapper.begin_calibration(3)
    for i in range(3):mapper.update(Observation({},facial_transform=rotation(.2,-.3,.15)),i)
    neutral=mapper.update(Observation({},facial_transform=rotation(.2,-.3,.15)),3)
    assert all(abs(neutral['head_'+axis])<1e-6 for axis in ('pitch','yaw','roll'))
    moved=mapper.update(Observation({},facial_transform=rotation(.3,.1,-.2)),4)
    assert moved['head_yaw']>.39 and moved['head_roll']>.34
    assert mapper.update(None,8)['head_yaw'] < moved['head_yaw']


def test_moderate_wink_closes_only_one_eye():
    a=controls_from_signals({'eyeBlinkLeft':.75,'eyeBlinkRight':.02})
    assert a['eye_open']+a['eye_asym']/2 < .08
    assert a['eye_open']-a['eye_asym']/2 > .95


def test_mesh_can_detect_closed_lid_when_blendshape_is_weak():
    a=controls_from_signals({'eyeBlinkLeft':.15,'eyeRatioLeft':.025,'eyeRatioRight':.23})
    assert a['eye_open']+a['eye_asym']/2 < .08
    assert a['eye_open']-a['eye_asym']/2 > .95


def test_independent_gaze_and_eye_roll_reach_the_rig():
    neutral=controls_to_pose(controls_from_signals({}))
    a=controls_from_signals({'eyeLookOutLeft':.8,'eyeLookOutRight':.8,'eyeLookUpLeft':.7,'eyeLookDownRight':.7})
    pose=controls_to_pose(a)
    assert a['gaze_x_left']>0 and a['gaze_x_right']<0
    assert a['gaze_y_left']<0 and a['gaze_y_right']>0
    left=xy(pose,'left_pupil_center')-xy(neutral,'left_pupil_center')
    right=xy(pose,'right_pupil_center')-xy(neutral,'right_pupil_center')
    assert left[0]>25 and right[0]<-25
    assert left[1]<-15 and right[1]>15
    # A circular trajectory remains continuous rather than selecting gaze presets.
    for angle in np.linspace(0,2*math.pi,20):
        a=controls_from_signals({'gazeXLeft':math.cos(angle)*.7,'gazeYLeft':math.sin(angle)*.7})
        validate_pose(controls_to_pose(a))


def mouth_image(tongue=False, lips=True):
    rgb=np.full((400,600,3),(165,125,105),dtype=np.uint8)
    rgb[201:230,255:345]=(28,16,20)
    if lips:rgb[228:235,255:345]=(180,72,85)
    if tongue:rgb[213:260,284:317]=(215,90,115)
    landmarks=np.zeros((478,3))
    for index,point in {61:(250,210),291:(350,210),13:(300,200),14:(300,223),17:(300,233),152:(300,330)}.items():
        landmarks[index,:2]=np.array(point)/[600,400]
    return rgb,landmarks.tolist()


def test_tongue_heuristic_rejects_lips_skin_and_teeth():
    rgb,mesh=mouth_image()
    assert tongue_protrusion(rgb,mesh,.4)<.1
    rgb[201:225,260:340]=245
    assert tongue_protrusion(rgb,mesh,.4)<.1
    rgb,mesh=mouth_image(tongue=True)
    assert tongue_protrusion(rgb,mesh,.4)>.7
    assert tongue_protrusion(rgb,[],.4)==0


@pytest.mark.parametrize('live',[False,True])
def test_new_gestures_preserve_svg_topology_and_101_ids(live):
    neutral=controls_to_pose(controls_from_signals({}))
    expressive=controls_to_pose(controls_from_signals({'tongueOut':1,'headYaw':.6,'headPitch':-.3,'headRoll':.4,'eyeBlinkLeft':.8}))
    assert len(expressive['keypoints'])==101
    assert expressive['rig']['tongue']['opacity']==1
    assert neutral['rig']['tongue']['opacity']==0
    assert xy(expressive,'tongue_tip')[1] > xy(neutral,'tongue_tip')[1] + 40
    def structure(pose):
        root=ET.fromstring(render_svg(pose,live=live))
        group=root.find("{http://www.w3.org/2000/svg}g[@id='avatar-head']")
        assert group is not None and group.get('transform').startswith('matrix(')
        return [(node.tag,node.get('id'),re.sub(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?','#',node.get('d','')))
                for node in root.iter() if node.tag.endswith(('}path','}ellipse'))]
    assert structure(neutral)==structure(expressive)
