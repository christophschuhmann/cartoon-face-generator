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
from cartoon_face.model import refresh_states, validate_pose, points, set_xy, topology
from cartoon_face.under_eye import set_under_eye_blend


def bounded(value, low=0.0, high=1.0):
    value = float(value)
    return min(high, max(low, value)) if math.isfinite(value) else low


def smoothstep(low, high, value):
    t = bounded((value - low) / (high - low))
    return t * t * (3 - 2 * t)


@dataclass
class Observation:
    blendshapes: dict[str, float]
    landmarks: list[tuple[float, float, float]] = field(default_factory=list)
    width: int = 640
    height: int = 480
    facial_transform: list | None = None
    tongue_out: float = 0.0


def head_signals(matrix):
    if matrix is None:
        return {}
    rotation = np.asarray(matrix, dtype=float)
    if rotation.shape != (4, 4) or not np.isfinite(rotation).all():
        return {}
    rotation = rotation[:3, :3]
    scales = np.linalg.norm(rotation, axis=0)
    if np.any(scales < 1e-6):
        return {}
    rotation = rotation / scales
    return {'headYaw': math.atan2(-rotation[2, 0], math.hypot(rotation[0, 0], rotation[1, 0])),
            'headPitch': math.atan2(rotation[2, 1], rotation[2, 2]),
            'headRoll': -math.atan2(rotation[1, 0], rotation[0, 0])}


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
    # Signed corner height in mouth-local axes. Calibration removes the natural
    # resting curve. Used only with a small lip gap, since speaking moves the
    # mouth centre independently of its corners.
    horizontal = (q[291] - q[61]) / mouth_width
    vertical = np.array([-horizontal[1], horizontal[0]])
    if np.dot(q[152]-q[13], vertical) < 0: vertical *= -1
    mouth_center = (q[0] + q[17]) / 2
    result['mouthCornerDrop'] = float(np.dot((q[61]+q[291])/2-mouth_center, vertical) / mouth_width)
    for side, outer, inner, top, bottom, iris in (
        ("Left", 263, 362, 386, 374, 473),
        ("Right", 33, 133, 159, 145, 468),
    ):
        eye_width = max(distance(outer, inner), 1.0)
        openness = distance(top, bottom) / eye_width
        result['eyeRatio' + side] = openness
        result["eyeBlink" + side] = bounded(1 - openness / .23)
        horizontal = (q[outer] - q[inner]) / eye_width
        if horizontal[0] < 0: horizontal = -horizontal
        vertical = np.array([-horizontal[1], horizontal[0]])
        brow_indices = [283, 282, 285] if side == 'Left' else [53, 52, 55]
        # Eye corners stay stable during squinting; the upper lid does not.
        eye_center = (q[outer] + q[inner]) / 2
        result['browHeight' + side] = float(np.dot(eye_center-q[brow_indices].mean(axis=0), vertical) / eye_width)
        for part, index in (('Inner', 285 if side=='Left' else 55), ('Outer', 283 if side=='Left' else 53)):
            result['brow'+part+'Height'+side] = float(np.dot(eye_center-q[index], vertical) / eye_width)
        if len(q) > iris:
            center = (q[outer] + q[inner]) / 2
            horizontal = (q[outer] - q[inner]) / eye_width
            if horizontal[0] < 0: horizontal = -horizontal
            vertical = np.array([-horizontal[1], horizontal[0]])
            # Measure relative to the eye axes, so head roll is not eye roll.
            result["gazeX" + side] = bounded(np.dot(q[iris] - center, horizontal) / eye_width * 5, -1, 1)
            result["gazeY" + side] = bounded(np.dot(q[iris] - (q[top] + q[bottom]) / 2, vertical) / eye_width * 5, -1, 1)
    return result


def signals_from_observation(observation):
    signals = mesh_signals(observation)
    for name, score in observation.blendshapes.items():
        if name != "_neutral":
            signals[name] = bounded(score)
    signals.update(head_signals(observation.facial_transform))
    signals['tongueOut'] = bounded(observation.tongue_out)
    return signals


DEFAULT_SENSITIVITY = {'brows': 1.80, 'frown': 2.10, 'speech': 1.60, 'gaze': 1.45, 'tongue': 1.0, 'squint': 1.70}


def controls_from_signals(signals, calibration=None, sensitivity=None):
    calibration = calibration or {}
    gains = DEFAULT_SENSITIVITY | (sensitivity or {})
    def s(name, deadband=.025):
        # Noise deadband prevents a resting face from generating tiny mouth gaps.
        return bounded((bounded(signals.get(name, 0)) - bounded(calibration.get(name, 0)) - deadband) / (1 - deadband))
    def responsive(value, gain):
        return 1 - (1 - bounded(value)) ** gain
    def pair(name):
        return s(name + "Left"), s(name + "Right")
    smile_l, smile_r = pair("mouthSmile")
    frown_l, frown_r = s('mouthFrownLeft', .008), s('mouthFrownRight', .008)
    frown_l, frown_r = [responsive(v, gains['frown'] * 1.65) for v in (frown_l, frown_r)]
    if 'mouthCornerDrop' in signals and 'mouthCornerDrop' in calibration and signals.get('lipPart', 0) < .36:
        drop = signals['mouthCornerDrop'] - calibration.get('mouthCornerDrop', 0.)
        geometric_frown = bounded((drop - .005) * 15 * gains['frown'] / 2.1)
        frown_l, frown_r = max(frown_l, geometric_frown), max(frown_r, geometric_frown)
    # Negative mouth evidence takes priority over spurious smile coactivation.
    negative = max(frown_l, frown_r)
    smile_l *= 1 - bounded(negative * 2.2)
    smile_r *= 1 - bounded(negative * 2.2)
    down_l, down_r = pair("browDown")
    down_l, down_r = [responsive(v, gains['brows'] * 1.5) for v in (down_l, down_r)]
    outer_l, outer_r = pair("browOuterUp")
    outer_l, outer_r = [responsive(v, gains['brows'] * 1.35) for v in (outer_l, outer_r)]
    squint_l, squint_r = pair("eyeSquint")
    squint_l, squint_r = [responsive(v, gains['squint']) for v in (squint_l, squint_r)]
    wide_l, wide_r = pair("eyeWide")
    blink_l, blink_r = pair("eyeBlink")
    # A wink often produces a moderate score rather than a perfect 1.0.
    blink_l, blink_r = smoothstep(.06, .70, blink_l), smoothstep(.06, .70, blink_r)
    for side in ('Left', 'Right'):
        if 'eyeRatio' + side in signals:
            resting = max(.12, calibration.get('eyeRatio' + side, .23))
            closure = smoothstep(.25, .80, 1 - signals['eyeRatio' + side] / resting)
            narrow = smoothstep(.08, .58, 1 - signals['eyeRatio' + side] / resting)
            if side == 'Left':blink_l = max(blink_l, closure); squint_l = max(squint_l, narrow)
            else:blink_r = max(blink_r, closure); squint_r = max(squint_r, narrow)
    inner = responsive(s("browInnerUp"), gains['brows'])
    smile = (smile_l + smile_r) / 2
    frown = (frown_l + frown_r) / 2
    pucker = responsive(max(s("mouthPucker", .015), .75*s("mouthFunnel", .015)), 1.8)
    pout = max(pucker, responsive(s('mouthShrugLower', .015), 1.9) * (1-s('jawOpen')))
    openness_l = bounded((1 - .965 * blink_l) * (1 - .70 * squint_l) + .32 * wide_l, .035, 1.45)
    openness_r = bounded((1 - .965 * blink_r) * (1 - .70 * squint_r) + .32 * wide_r, .035, 1.45)
    if any(name.startswith("eyeLook") for name in signals):
        # Positive screen x is subject left on an unmirrored frontal image.
        gaze_x = (s("eyeLookOutLeft") + s("eyeLookInRight") - s("eyeLookInLeft") - s("eyeLookOutRight")) * .8
        gaze_y = (s("eyeLookDownLeft") + s("eyeLookDownRight") - s("eyeLookUpLeft") - s("eyeLookUpRight")) * .8
        gaze_left_x = gains['gaze'] * (s('eyeLookOutLeft') - s('eyeLookInLeft'))
        gaze_right_x = gains['gaze'] * (s('eyeLookInRight') - s('eyeLookOutRight'))
        gaze_left_y = gains['gaze'] * (s('eyeLookDownLeft') - s('eyeLookUpLeft'))
        gaze_right_y = gains['gaze'] * (s('eyeLookDownRight') - s('eyeLookUpRight'))
    else:
        gaze_x = sum(signals.get("gazeX" + side, 0) - calibration.get("gazeX" + side, 0) for side in ("Left", "Right")) / 2
        gaze_y = sum(signals.get("gazeY" + side, 0) - calibration.get("gazeY" + side, 0) for side in ("Left", "Right")) / 2
        gaze_left_x = signals.get('gazeXLeft', 0) - calibration.get('gazeXLeft', 0)
        gaze_right_x = signals.get('gazeXRight', 0) - calibration.get('gazeXRight', 0)
        gaze_left_y = signals.get('gazeYLeft', 0) - calibration.get('gazeYLeft', 0)
        gaze_right_y = signals.get('gazeYRight', 0) - calibration.get('gazeYRight', 0)
    a = copy.deepcopy(resolve_emotion("neutral")["actions"])
    a.update(
        brow_raise=bounded(.70 * inner + .45 * (outer_l + outer_r) / 2 - .18 * (down_l + down_r) / 2, -.18, 1),
        brow_inner=bounded(.7 * inner), brow_outer=bounded(.5 * (outer_l + outer_r) / 2),
        brow_asym=bounded(.8 * (outer_l - outer_r) - .55 * (down_l - down_r), -.8, .8),
        frown=bounded(.65 * (down_l + down_r) / 2),
        eye_open=(openness_l + openness_r) / 2, eye_asym=openness_l - openness_r,
        squint=bounded((squint_l + squint_r) / 2),
        squint_left=squint_l, squint_right=squint_r,
        lip_pout=pout, mouth_pucker=pucker,
        lid_curve=bounded(.30 * smile), gaze_x=bounded(gaze_x, -.8, .8), gaze_y=bounded(gaze_y, -.55, .55),
        mouth_width=bounded(.77 + .28 * smile - .32 * pucker + .08 * (s("mouthStretchLeft") + s("mouthStretchRight")), .42, 1.18),
        smile=bounded(.97 * smile - 1.65 * frown - .18 * pout, -1.1, 1.05),
        mouth_open=bounded(.78 * responsive(max(s("jawOpen", .010), .7 * s("lipPart", .012)), gains['speech']), 0, .8),
        mouth_asym=bounded(.65 * (smile_l - smile_r) - .5 * (frown_l - frown_r), -.65, .65),
        mouth_tension=bounded(.3 * (s("mouthPressLeft") + s("mouthPressRight"))),
        cheek_lift=bounded(.4 * smile + .2 * (squint_l + squint_r) / 2),
        nose_lift=bounded(.4 * (s("noseSneerLeft") + s("noseSneerRight")) / 2),
        under_eye_blend=bounded(.12 + .28 * smile + .20 * (squint_l + squint_r) / 2, .12, .60),
        pupil_scale=1.0, warmth=.50,
        head_yaw=bounded(signals.get('headYaw', 0) - calibration.get('headYaw', 0), -.85, .85),
        head_pitch=bounded(signals.get('headPitch', 0) - calibration.get('headPitch', 0), -.55, .55),
        head_roll=bounded(signals.get('headRoll', 0) - calibration.get('headRoll', 0), -.55, .55),
        tongue_out=bounded(signals.get('tongueOut', 0) * gains['tongue']),
        gaze_x_left=bounded(gaze_left_x, -1, 1), gaze_x_right=bounded(gaze_right_x, -1, 1),
        gaze_y_left=bounded(gaze_left_y, -1, 1), gaze_y_right=bounded(gaze_right_y, -1, 1),
    )
    a['mouth_open'] = max(a['mouth_open'], .22 * a['tongue_out'])
    for side, outer, down in (('left', outer_l, down_l), ('right', outer_r, down_r)):
        key = 'browHeight' + side.title()
        mesh_up = mesh_down = 0.
        if key in signals and key in calibration:
            delta = signals[key] - calibration[key]
            mesh_up = bounded((delta-.009)/.13 * gains['brows']/1.8)
            mesh_down = bounded((-delta-.012)/.11 * gains['brows']/1.8)
        up = max(outer, mesh_up)
        contraction = max(down, mesh_down)
        # Disambiguate MediaPipe's ONE inner-up coefficient with per-side mesh.
        ikey = 'browInnerHeight' + side.title()
        side_inner = inner
        if ikey in signals and ikey in calibration:
            side_inner = bounded((signals[ikey]-calibration[ikey]-.008)/.13)
        elif abs(outer_l-outer_r) > .12:
            side_inner *= bounded((outer+.03)/(max(outer_l,outer_r)+.03))
        a['brow_raise_' + side] = bounded(.45*side_inner + 1.10*up - .40*contraction, -.4, 1.4)
        a['brow_inner_' + side] = bounded(.90*side_inner + .12*mesh_up)
        a['brow_outer_' + side] = bounded(.95*up)
        a['frown_' + side] = bounded(.95*contraction)
    a['frown'] = (a['frown_left'] + a['frown_right'])/2
    for key in ('brow_raise', 'brow_inner', 'brow_outer'):
        a[key] = (a[key+'_left']+a[key+'_right'])/2
    a['brow_asym'] = bounded((a['brow_raise_left']-a['brow_raise_right'])/2, -.8, .8)
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
        self.sensitivity = DEFAULT_SENSITIVITY.copy()
        self.tongue_active = False
        self.tongue_last_seen = -math.inf
        self.tongue_last_value = 0.

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
        self.tongue_active = False
        self.tongue_last_seen = -math.inf
        self.tongue_last_value = 0.

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
            target = controls_from_signals(signals, self.calibration, self.sensitivity)
            # Hysteresis bridges one missed mouth crop; release stays fast enough
            # for speech. Never calibrate tongue presence away as a rest offset.
            tongue = target['tongue_out']
            if tongue >= (.10 if self.tongue_active else .20):
                self.tongue_active = True
                self.tongue_last_seen = timestamp_seconds
                self.tongue_last_value = tongue
            elif timestamp_seconds - self.tongue_last_seen > .16:
                self.tongue_active = False
            target['tongue_out'] = max(tongue, self.tongue_last_value * .85) if self.tongue_active else 0.
            target['mouth_open'] = max(target['mouth_open'], .22 * target['tongue_out'])
            # Iris positions during a blink are unreliable. Retain each eye's
            # last gaze independently until that lid opens again.
            for side, sign in (('left', 1), ('right', -1)):
                if target['eye_open'] + sign * target['eye_asym'] / 2 < .15:
                    for axis in ('x', 'y'):
                        key = 'gaze_' + axis + '_' + side
                        target[key] = self.controls[key]
            tau = self.smoothing_seconds
        else:
            if self.last_seen is not None and timestamp_seconds - self.last_seen <= self.hold_seconds:
                return copy.deepcopy(self.controls)
            target, tau = NEUTRAL_CONTROLS, self.decay_seconds
        for name, value in target.items():
            # Eyelid closure reacts faster than the other expressive motion.
            local_tau = min(tau, .025) if tracking and name in ("eye_open", "eye_asym") else min(tau, .035) if tracking and name.startswith('gaze_') else max(tau, .09) if name.startswith('head_') else tau
            if tracking and name in ('mouth_open', 'mouth_width', 'mouth_asym', 'mouth_tension', 'lip_pout', 'mouth_pucker', 'smile'):
                local_tau = min(tau, .015 if value < self.controls[name] else .022)
            if tracking and name == 'tongue_out': local_tau = min(tau, .045)
            if tracking and name == 'head_pitch': local_tau = max(tau, .14)
            if tracking and (name.startswith('brow_') or name.startswith('frown')): local_tau = min(tau, .045)
            alpha = 1.0 if local_tau == 0 else -math.expm1(-dt / local_tau)
            self.controls[name] += alpha * (value - self.controls[name])
        return copy.deepcopy(self.controls)


def controls_to_pose(controls):
    profile = resolve_emotion("neutral")
    profile["slug"] = "webcam_expression"
    # Keep the same soft identity/decorations across frames. No taxonomy labels.
    profile["options"].update(mouth="open", under_eye="continuous", tongue="none", highlight="round")
    p = build_pose(profile, controls, finalize=False)
    # Keep tongue topology present at rest; animate opacity AND its six anchors.
    tongue = bounded(controls.get('tongue_out', 0))
    root = points(p, 'mouth_upper')[2]
    anchors = points(p, 'tongue')
    anchors[:, 1] = root[1] + 2 + (anchors[:, 1] - root[1] - 2) * (.12 + .88 * tongue)
    anchors[:, 1] = np.clip(anchors[:, 1], 7, 743)
    for name, position in zip(topology()['components']['tongue']['anchors'], anchors):set_xy(p, name, position)
    set_xy(p, 'tongue_crease_tip', [root[0] + 8, min(743, root[1] + 12 + 38 * tongue)])
    p['rig']['tongue']['opacity'] = tongue
    p['rig']['tongue_crease']['opacity'] = tongue
    p['head_pose'] = {axis: float(controls.get('head_' + axis, 0)) for axis in ('yaw', 'pitch', 'roll')}
    p['head_pose']['projection'] = 'curved_perspective_v2'
    openness = smoothstep(.002, .035, controls["mouth_open"])
    p["rig"]["mouth_upper"]["fill_opacity"] = openness
    p["rig"]["mouth_lower"]["opacity"] = max(openness, controls.get('lip_pout', 0))
    corner = smoothstep(.20, .50, controls["smile"])
    p["rig"]["mouth_upper"]["corner_accent"] = [corner, corner]
    p["rig"]["mouth_upper"].update(corner_size=16, corner_width=5)
    for side in ("left", "right"):
        set_under_eye_blend(p, side, controls["under_eye_blend"])
    p.pop("emotion", None)
    p.pop("expression", None)
    p["provenance"] = {
        "kind": "human_blendshape_semantic_retargeting", "mapper_version": "2.0.0",
        "base_pose": "smile", "identity": "fixed_soft_cartoon", "human_recognition": "unmeasured",
        "mapping_note": "Authored continuous motion cues; no emotion-class prediction and no human contour tracing.",
    }
    p["webcam_controls"] = {name: float(value) for name, value in controls.items()}
    refresh_states(p)
    validate_pose(p)
    return p
