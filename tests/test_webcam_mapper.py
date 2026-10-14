"""Semantic retargeting and the separate local browser API; no webcam required."""
import copy
import io
import math
import threading
import time
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from PIL import Image
from webcam_mapper.mapping import (
    Observation, TemporalMapper, controls_from_signals, controls_to_pose,
    mesh_signals, NEUTRAL_CONTROLS,
)
from cartoon_face.model import topology, validate_pose
from cartoon_face.renderer import render_svg


def test_cues_preserve_identity_and_stable_ids():
    rng = np.random.default_rng(144)
    names = ["eyeBlinkLeft", "eyeBlinkRight", "eyeWideLeft", "eyeWideRight", "eyeSquintLeft", "eyeSquintRight",
             "jawOpen", "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft", "mouthFrownRight", "mouthPucker",
             "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "browDownLeft", "browDownRight"]
    expected = {k["name"]: k["id"] for k in topology()["keypoints"]}
    for values in [np.zeros(len(names)), np.ones(len(names)), *rng.uniform(0, 1, (20, len(names)))]:
        pose = controls_to_pose(controls_from_signals(dict(zip(names, values))))
        validate_pose(pose)
        assert {name: k["id"] for name, k in pose["keypoints"].items()} == expected
        assert len(pose["keypoints"]) == 101
        assert "emotion" not in pose and "expression" not in pose
        assert pose["provenance"]["human_recognition"] == "unmeasured"
        ET.fromstring(render_svg(pose))


def test_subject_left_wink_is_independent():
    controls = controls_from_signals({"eyeBlinkLeft": 1})
    left = controls["eye_open"] + controls["eye_asym"] / 2
    right = controls["eye_open"] - controls["eye_asym"] / 2
    assert left == pytest.approx(.035)
    assert right == pytest.approx(1)
    controls = controls_from_signals({"eyeBlinkRight": 1})
    assert controls["eye_asym"] > 0


def test_calibration_removes_resting_offsets_with_median():
    mapper = TemporalMapper(smoothing_seconds=0)
    mapper.begin_calibration(3)
    for i, jaw in enumerate((.2, .21, .8)):
        mapper.update(Observation({"jawOpen": jaw, "mouthSmileLeft": .2, "mouthSmileRight": .2}), i * .2)
    controls = mapper.update(Observation({"jawOpen": .21, "mouthSmileLeft": .2, "mouthSmileRight": .2}), .8)
    assert mapper.calibration["jawOpen"] == pytest.approx(.21)
    assert controls["mouth_open"] == 0
    assert controls["smile"] == pytest.approx(.08)
    mapper.reset()
    assert mapper.calibration == {}


def test_temporal_filter_hold_decay_and_monotonic_time():
    mapper = TemporalMapper()
    excited = mapper.update(Observation({"jawOpen": 1}), 0)
    assert 0 < excited["mouth_open"] < .78
    assert mapper.update(None, .3) == excited
    decaying = mapper.update(None, 1)
    assert 0 < decaying["mouth_open"] < excited["mouth_open"]
    assert mapper.update(None, 10)["mouth_open"] < 1e-8
    with pytest.raises(ValueError, match="monotonic"):
        mapper.update(None, 9)
    with pytest.raises(ValueError, match="finite"):
        mapper.update(None, math.nan)


def test_mesh_ratios_respect_image_aspect():
    landmarks = np.zeros((478, 3))
    landmarks[61, :2] = [.2, .5]
    landmarks[291, :2] = [.8, .5]
    landmarks[13, :2] = [.5, .45]
    landmarks[14, :2] = [.5, .55]
    normal = mesh_signals(Observation({}, landmarks.tolist(), 400, 400))
    wide = mesh_signals(Observation({}, landmarks.tolist(), 800, 400))
    assert wide["jawOpen"] == pytest.approx(normal["jawOpen"] / 2)


def test_nonfinite_blendshape_scores_cannot_escape_pose_contract():
    controls = controls_from_signals({"jawOpen": math.inf, "mouthSmileLeft": math.nan, "browDownRight": -100})
    assert all(math.isfinite(value) for value in controls.values())
    validate_pose(controls_to_pose(controls))


def test_mouth_visibility_changes_continuously_near_rest():
    a, b = copy.deepcopy(NEUTRAL_CONTROLS), copy.deepcopy(NEUTRAL_CONTROLS)
    a["mouth_open"], b["mouth_open"] = .0149, .0151
    pa, pb = controls_to_pose(a), controls_to_pose(b)
    assert abs(pa["rig"]["mouth_upper"]["fill_opacity"] - pb["rig"]["mouth_upper"]["fill_opacity"]) < .02
    assert abs(pa["rig"]["mouth_lower"]["opacity"] - pb["rig"]["mouth_lower"]["opacity"]) < .02


def test_under_eye_uses_shared_continuous_field_with_fixed_variant():
    poses = [controls_to_pose(controls_from_signals({"mouthSmileLeft": value, "mouthSmileRight": value})) for value in (.4, .401)]
    for p in poses:
        assert p["geometry"]["under_eye_transition"] == "stroke_bank_v1"
        for side in ("left", "right"):
            assert p["variants"][side + "_under_eye"] == "continuous"
            h, u = p["rig"][side + "_hatching"], p["rig"][side + "_under_eye"]
            assert len(h["slot_weights"]) == 8
            assert h["opacity"] + u["opacity"] == pytest.approx(1)
    assert abs(poses[0]["rig"]["left_hatching"]["foldness"] - poses[1]["rig"]["left_hatching"]["foldness"]) < .001


def test_local_web_api_and_export():
    from webcam_mapper.app import Pipeline, create_app
    class Detector:
        def detect(self, rgb, timestamp):
            return Observation({"jawOpen": .3}, [(0., 0., 0.)] * 478, rgb.shape[1], rgb.shape[0])
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.detector = Detector()
    pipeline.mapper = TemporalMapper()
    pipeline.fps = 5
    pipeline.lock = threading.Lock()
    pipeline.start = time.monotonic()
    client = create_app(pipeline).test_client()
    assert client.get("/").status_code == 200
    assert client.get("/healthz").json["cpu"]
    assert client.post("/api/frame", data=b"bad", content_type="text/plain").status_code == 415
    assert client.post("/api/frame", data=b"bad", content_type="image/jpeg").status_code == 400
    assert client.post("/api/reset", headers={"Origin": "https://example.org"}).status_code == 403
    frame = io.BytesIO()
    Image.new("RGB", (640, 480), "white").save(frame, "JPEG")
    response = client.post("/api/frame", data=frame.getvalue(), content_type="image/jpeg")
    assert response.status_code == 200
    assert response.json["landmark_count"] == 478
    ET.fromstring(response.json["svg"])
    assert client.post("/api/calibrate").json["frames"] == 8
    assert client.post("/api/reset").json["ok"]
    assert client.get("/api/avatar.svg").mimetype == "image/svg+xml"
    validate_pose(client.get("/api/pose").json)
