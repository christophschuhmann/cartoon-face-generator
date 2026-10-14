"""Bounded semantic retargeting, never direct tracing of human geometry.

MediaPipe *Left/*Right are the subject's left/right, matching the rig names.
Inputs must be unmirrored; mirroring is only a browser preview presentation.
No blendshape or procedural recipe is an emotion-recognition label.
"""
from dataclasses import dataclass, field
import copy
import math
import numpy as np
from . import paths  # noqa: F401: shared renderer import path
from cartoon_face.emotion_library import resolve_emotion, build_pose
from cartoon_face.model import refresh_states, validate_pose
from cartoon_face.under_eye import set_under_eye_blend


def bounded(value, low=0.0, high=1.0):
    value = float(value)
    return float(np.clip(value, low, high)) if math.isfinite(value) else low


def smoothstep(low, high, value):
    t = bounded((value - low) / (high - low))
    return t * t * (3 - 2 * t)


@dataclass
class Observation:
    blendshapes: dict[str, float]
    landmarks: list[tuple[float, float, float]] = field(default_factory=list)
    width: int = 640
    height: int = 480


def mesh_signals(observation):
    """Fallback ratios use pixels, so non-square image aspect is respected.

    Index definitions follow MediaPipe's canonical mesh/iris topology. These are
    ratios for missing blendshapes, not human-to-cartoon point correspondences.
    """
    if len(observation.landmarks) < 468:
        return {}
    q = np.asarray(observation.landmarks, dtype=float)[:, :2] * [observation.width, observation.height]
    if not np.isfinite(q).all():
        return {}
    distance = lambda a, b: float(np.linalg.norm(q[a] - q[b]))
    mouth_width = max(distance(61, 291), 1.0)
    result = {"jawOpen": bounded(distance(13, 14) / mouth_width / .55)}
    result["lipPart"] = result["jawOpen"]
    for side, outer, inner, top, bottom, iris in (
        ("Left", 263, 362, 386, 374, 473),
        ("Right", 33, 133, 159, 145, 468),
    ):
        eye_width = max(distance(outer, inner), 1.0)
        openness = distance(top, bottom) / eye_width
        result["eyeBlink" + side] = bounded(1 - openness / .23)
        if len(q) > iris:
            center = (q[outer] + q[inner]) / 2
            result["gazeX" + side] = bounded((q[iris, 0] - center[0]) / eye_width * 5, -1, 1)
            result["gazeY" + side] = bounded((q[iris, 1] - (q[top, 1] + q[bottom, 1]) / 2) / eye_width * 5, -1, 1)
    return result


def signals_from_observation(observation):
    signals = mesh_signals(observation)
    for name, score in observation.blendshapes.items():
        if name != "_neutral":
            signals[name] = bounded(score)
    return signals


def controls_from_signals(signals, calibration=None):
    calibration = calibration or {}
    def s(name):
        # Noise deadband prevents a resting face from generating tiny mouth gaps.
        return max(0.0, bounded(signals.get(name, 0)) - bounded(calibration.get(name, 0)) - .025) / .975
    def pair(name):
        return s(name + "Left"), s(name + "Right")
    smile_l, smile_r = pair("mouthSmile")
    frown_l, frown_r = pair("mouthFrown")
    down_l, down_r = pair("browDown")
    outer_l, outer_r = pair("browOuterUp")
    squint_l, squint_r = pair("eyeSquint")
    wide_l, wide_r = pair("eyeWide")
    blink_l, blink_r = pair("eyeBlink")
    inner = s("browInnerUp")
    smile = (smile_l + smile_r) / 2
    frown = (frown_l + frown_r) / 2
    pucker = max(s("mouthPucker"), s("mouthFunnel"))
    openness_l = bounded(1 - .965 * blink_l + .32 * wide_l - .2 * squint_l, .035, 1.45)
    openness_r = bounded(1 - .965 * blink_r + .32 * wide_r - .2 * squint_r, .035, 1.45)
    if any(name.startswith("eyeLook") for name in signals):
        # Positive screen x is subject left on an unmirrored frontal image.
        gaze_x = (s("eyeLookOutLeft") + s("eyeLookInRight") - s("eyeLookInLeft") - s("eyeLookOutRight")) * .8
        gaze_y = (s("eyeLookDownLeft") + s("eyeLookDownRight") - s("eyeLookUpLeft") - s("eyeLookUpRight")) * .8
    else:
        gaze_x = sum(signals.get("gazeX" + side, 0) - calibration.get("gazeX" + side, 0) for side in ("Left", "Right")) / 2
        gaze_y = sum(signals.get("gazeY" + side, 0) - calibration.get("gazeY" + side, 0) for side in ("Left", "Right")) / 2
    a = copy.deepcopy(resolve_emotion("neutral")["actions"])
    a.update(
        brow_raise=bounded(.70 * inner + .45 * (outer_l + outer_r) / 2 - .18 * (down_l + down_r) / 2, -.18, 1),
        brow_inner=bounded(.7 * inner), brow_outer=bounded(.5 * (outer_l + outer_r) / 2),
        brow_asym=bounded(.8 * (outer_l - outer_r) - .55 * (down_l - down_r), -.8, .8),
        frown=bounded(.65 * (down_l + down_r) / 2),
        eye_open=(openness_l + openness_r) / 2, eye_asym=openness_l - openness_r,
        squint=bounded((squint_l + squint_r) / 2),
        lid_curve=bounded(.30 * smile), gaze_x=bounded(gaze_x, -.8, .8), gaze_y=bounded(gaze_y, -.55, .55),
        mouth_width=bounded(.77 + .28 * smile - .32 * pucker + .08 * (s("mouthStretchLeft") + s("mouthStretchRight")), .42, 1.18),
        smile=bounded(.08 + .97 * smile - .85 * frown - .10 * pucker, -.7, 1.05),
        mouth_open=bounded(.78 * max(s("jawOpen"), .6 * s("lipPart")) + .09 * pucker, 0, .8),
        mouth_asym=bounded(.65 * (smile_l - smile_r) - .5 * (frown_l - frown_r), -.65, .65),
        mouth_tension=bounded(.3 * (s("mouthPressLeft") + s("mouthPressRight"))),
        cheek_lift=bounded(.4 * smile + .2 * (squint_l + squint_r) / 2),
        nose_lift=bounded(.4 * (s("noseSneerLeft") + s("noseSneerRight")) / 2),
        under_eye_blend=bounded(.12 + .28 * smile + .20 * (squint_l + squint_r) / 2, .12, .60),
        pupil_scale=1.0, warmth=.50,
    )
    return a


NEUTRAL_CONTROLS = controls_from_signals({})


class TemporalMapper:
    """Time-based filtering, explicit neutral calibration, and lost-face decay."""
    def __init__(self, smoothing_seconds=.12, hold_seconds=.6, decay_seconds=.35):
        for value in (smoothing_seconds, hold_seconds, decay_seconds):
            if not math.isfinite(value) or value < 0:
                raise ValueError("Smoothing/hold/decay must be finite and nonnegative")
        self.smoothing_seconds = smoothing_seconds
        self.hold_seconds = hold_seconds
        self.decay_seconds = decay_seconds
        self.calibration = {}
        self.calibration_samples = []
        self.calibration_remaining = 0
        self.last_timestamp = None
        self.last_seen = None
        self.last_signals = None
        self.controls = copy.deepcopy(NEUTRAL_CONTROLS)

    def begin_calibration(self, frames=8):
        if not 1 <= frames <= 100:
            raise ValueError("Calibration frames must be 1..100")
        self.calibration_samples = []
        self.calibration_remaining = frames

    def reset(self):
        self.calibration = {}
        self.calibration_samples = []
        self.calibration_remaining = 0
        self.controls = copy.deepcopy(NEUTRAL_CONTROLS)
        self.last_timestamp = self.last_seen = self.last_signals = None

    def update(self, observation, timestamp_seconds):
        timestamp_seconds = float(timestamp_seconds)
        if not math.isfinite(timestamp_seconds):
            raise ValueError("Timestamp must be finite")
        if self.last_timestamp is not None and timestamp_seconds < self.last_timestamp:
            raise ValueError("Timestamps must be monotonic")
        dt = .2 if self.last_timestamp is None else timestamp_seconds - self.last_timestamp
        self.last_timestamp = timestamp_seconds
        tracking = observation is not None
        if tracking:
            self.last_seen = timestamp_seconds
            signals = signals_from_observation(observation)
            self.last_signals = signals
            if self.calibration_remaining:
                self.calibration_samples.append(signals)
                self.calibration_remaining -= 1
                if not self.calibration_remaining:
                    names = set().union(*(sample.keys() for sample in self.calibration_samples))
                    self.calibration = {name: float(np.median([sample.get(name, 0) for sample in self.calibration_samples])) for name in names}
                    self.controls = copy.deepcopy(NEUTRAL_CONTROLS)
            target = controls_from_signals(signals, self.calibration)
            tau = self.smoothing_seconds
        else:
            if self.last_seen is not None and timestamp_seconds - self.last_seen <= self.hold_seconds:
                return copy.deepcopy(self.controls)
            target, tau = NEUTRAL_CONTROLS, self.decay_seconds
        for name, value in target.items():
            # Eyelid closure reacts faster than the other expressive motion.
            local_tau = min(tau, .035) if tracking and name in ("eye_open", "eye_asym") else tau
            alpha = 1.0 if local_tau == 0 else -math.expm1(-dt / local_tau)
            self.controls[name] += alpha * (value - self.controls[name])
        return copy.deepcopy(self.controls)


def controls_to_pose(controls):
    profile = resolve_emotion("neutral")
    profile["slug"] = "webcam_expression"
    # Keep the same soft identity/decorations across frames. No taxonomy labels.
    profile["options"].update(mouth="open", under_eye="continuous", tongue="none", highlight="round")
    p = build_pose(profile, controls)
    openness = smoothstep(.002, .035, controls["mouth_open"])
    p["rig"]["mouth_upper"]["fill_opacity"] = openness
    p["rig"]["mouth_lower"]["opacity"] = openness
    corner = smoothstep(.20, .50, controls["smile"])
    p["rig"]["mouth_upper"]["corner_accent"] = [corner, corner]
    p["rig"]["mouth_upper"].update(corner_size=16, corner_width=5)
    for side in ("left", "right"):
        set_under_eye_blend(p, side, controls["under_eye_blend"])
    p.pop("emotion", None)
    p.pop("expression", None)
    p["provenance"] = {
        "kind": "human_blendshape_semantic_retargeting", "mapper_version": "1.0.0",
        "base_pose": "smile", "identity": "fixed_soft_cartoon", "human_recognition": "unmeasured",
        "mapping_note": "Authored continuous motion cues; no emotion-class prediction and no human contour tracing.",
    }
    p["webcam_controls"] = {name: float(value) for name, value in controls.items()}
    refresh_states(p)
    validate_pose(p)
    return p
