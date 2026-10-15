"""CPU expression evidence and optional authored-archetype interpolation.

Seven-class CNN evidence is separate from 40 EmoNet and 60 social STYLE recipes.
Recipe distance and personal-reference distance are similarities, not calibrated
emotion probabilities. Webcam images only live in the bounded worker slot.
"""
import copy
from functools import lru_cache
import math
from pathlib import Path
import threading
import time
import cv2
import numpy as np
from . import paths  # noqa
from .mapping import NEUTRAL_CONTROLS, bounded
from .empathic import EmpathicWorker, model_ready
from cartoon_face.emotion_library import catalog, resolve_emotion, emotion_pose40
from cartoon_face.social_expressions import social_catalog, social_profile, social_pose

CLASSES = ('angry', 'disgust', 'fearful', 'happy', 'neutral', 'sad', 'surprised')
LABELS = ('Verärgert', 'Angewidert', 'Ängstlich', 'Fröhlich', 'Neutral', 'Traurig', 'Überrascht')
CNN_ARCHETYPES = ('anger', 'disgust', 'fear', 'amusement', 'neutral', 'sadness', 'surprise')
FEATURES = {'brow_raise': 1.1, 'brow_inner': .8, 'brow_outer': .6, 'brow_asym': .8,
            'frown': 1.2, 'eye_open': 1., 'eye_asym': .8, 'squint': .5,
            'smile': 1.5, 'mouth_open': .5, 'mouth_width': .7, 'mouth_asym': .9,
            'nose_lift': .5, 'tongue_out': 1.8, 'gaze_x_left': .3,
            'gaze_x_right': .3, 'gaze_y_left': .4, 'gaze_y_right': .4}
KEYS = tuple(FEATURES)
WEIGHTS = np.array(list(FEATURES.values()))
PROTECTED = {'eye_open', 'eye_asym', 'mouth_open', 'tongue_out', 'gaze_x', 'gaze_y',
             'squint_left', 'squint_right', 'lip_pout', 'mouth_pucker',
             'gaze_x_left', 'gaze_x_right', 'gaze_y_left', 'gaze_y_right',
             'head_yaw', 'head_pitch', 'head_roll'}


@lru_cache(maxsize=1)
def library():
    result = {}
    for taxonomy, profiles in (('emonet_face_40_v1', catalog()['profiles']),
                               ('cartoon_social_60_v1', social_catalog()['profiles'])):
        for source in profiles:
            p = resolve_emotion(source['slug']) if taxonomy.startswith('emonet') else social_profile(source['slug'])[0]
            a = copy.deepcopy(NEUTRAL_CONTROLS)
            a.update(p['actions'])
            constraints = p.get('social_constraints', {})
            opens = {s: a['eye_open'] + sign * a['eye_asym'] / 2 for s, sign in (('left', 1), ('right', -1))}
            for side in constraints.get('closed_eyes', []): opens[side] = .055
            a['eye_open'] = (opens['left'] + opens['right']) / 2
            a['eye_asym'] = opens['left'] - opens['right']
            for axis in ('x', 'y'):
                key = 'gaze_' + axis
                a[key] = max(constraints.get(key + '_min', -1), min(constraints.get(key + '_max', 1), a[key]))
            for side, sign in (('left', -1), ('right', 1)):
                a['gaze_x_' + side] = a['gaze_x'] + sign * a.get('gaze_convergence', 0)
                a['gaze_y_' + side] = a['gaze_y']
            a['tongue_out'] = float(p['options']['tongue'] == 'out')
            a['under_eye_blend'] = .7 if p['options'].get('under_eye') == 'hatching' else .18
            result[p['slug']] = {'slug': p['slug'], 'label': p['label_de'], 'taxonomy': taxonomy,
                                  'family': p['family'], 'actions': a}
    return result


def vector(controls):
    return np.array([controls.get(k, NEUTRAL_CONTROLS.get(k, 0.)) for k in KEYS], dtype=float)


def archetype_pose(slug):
    item = library()[slug]
    return emotion_pose40(slug, variation=0) if item['taxonomy'].startswith('emonet') else social_pose(slug, variation=0)


def aligned_face(rgb, observation):
    """Five-point similarity fit to the model's documented 112px alignment."""
    if observation is None or len(observation.landmarks) < 468: return None
    q = np.asarray(observation.landmarks)[:, :2] * [observation.width, observation.height]
    src = np.array([(q[33] + q[133]) / 2, (q[263] + q[362]) / 2, q[1], q[61], q[291]])
    if not np.isfinite(src).all() or np.linalg.norm(src[0] - src[1]) < 18: return None
    dst = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]])
    rows, target = [], []
    for (x, y), (u, v) in zip(src, dst):
        rows.extend(([x, -y, 1, 0], [y, x, 0, 1])); target.extend((u, v))
    a, b, tx, ty = np.linalg.lstsq(rows, target, rcond=None)[0]
    return cv2.warpAffine(rgb, np.array([[a, -b, tx], [b, a, ty]]), (112, 112), borderMode=cv2.BORDER_REPLICATE)


class ExpressionWorker:
    """Single latest-crop slot: no accumulated frames and no main-loop wait."""
    def __init__(self, model=None):
        self.path = Path(model or Path(__file__).parent / 'models/expression_mobilefacenet.onnx')
        self.available = self.path.is_file()
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.pending = self.result = None
        self.generation = 0
        self.last_submit = -math.inf
        self.closed = False
        self.error = None
        self.thread = None

    def submit(self, rgb, observation):
        now = time.monotonic()
        if not self.available or self.closed or now - self.last_submit < .4: return
        crop = aligned_face(rgb, observation)
        if crop is None: return
        self.last_submit = now
        with self.lock:
            self.pending = (crop, now, self.generation)
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name='expression-cpu', daemon=True)
                self.thread.start()
        self.event.set()

    def _run(self):
        try:
            net = cv2.dnn.readNet(str(self.path))
            net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            while not self.closed:
                self.event.wait(.5)
                with self.lock:
                    item, self.pending = self.pending, None
                    self.event.clear()
                if item is None: continue
                crop, captured, generation = item
                started = time.perf_counter()
                blob = cv2.dnn.blobFromImage(crop, 1 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=False)
                net.setInput(blob)
                logits = net.forward().reshape(-1).astype(float)
                if logits.size != 7 or not np.isfinite(logits).all(): raise ValueError('Invalid expression output')
                scores = np.exp((logits - logits.max()) / 1.5)
                scores /= scores.sum()
                result = {'scores': scores, 'captured': captured, 'ms': (time.perf_counter() - started) * 1000}
                with self.lock:
                    if generation == self.generation and not self.closed: self.result = result
        except Exception as error:
            self.error = str(error)
            self.available = False

    def snapshot(self):
        with self.lock:
            if self.result and time.monotonic() - self.result['captured'] < 1.4: return dict(self.result)
        return None

    def clear(self):
        with self.lock:
            self.generation += 1
            self.pending = self.result = None

    def close(self):
        self.closed = True
        self.clear()
        self.event.set()
        if self.thread: self.thread.join(timeout=2)


class ExpressionMixer:
    def __init__(self, backend='motion'):
        self.enabled = True
        self.strength = .35
        self.social_enabled = True
        self.manual = ''
        self.worker = ExpressionWorker()
        self.empathic = EmpathicWorker()
        self.backend = backend
        self.empathic_result = None
        self.probabilities = None
        self.last_result = None
        self.last_time = None
        self.blend = {}
        self.references = {}
        self.learning = None
        self.status = {}
        self.items = list(library().values())
        self.templates = np.stack([vector(p['actions']) for p in self.items])

    def reset(self):
        self.worker.clear()
        self.empathic.clear()
        self.empathic_result = None
        self.probabilities = self.last_result = self.last_time = None
        self.blend = {}
        self.learning = None
        self.status = {}

    def settings(self):
        return {'enabled': self.enabled, 'strength': self.strength, 'social': self.social_enabled,
                'manual': self.manual, 'cnn_available': self.worker.available,
                'backend': self.backend, 'empathic_available': model_ready(),
                'variant': self.empathic.variant,
                'empathic_variants': {v:model_ready(v) for v in ('small','large')},
                'cnn_error': self.worker.error, 'reference_count': sum(map(len, self.references.values()))}

    def configure(self, data):
        if 'enabled' in data and not isinstance(data['enabled'], bool): raise ValueError('enabled must be boolean')
        if 'social' in data and not isinstance(data['social'], bool): raise ValueError('social must be boolean')
        strength = float(data.get('strength', self.strength))
        if not math.isfinite(strength) or not 0 <= strength <= 1: raise ValueError('strength must be 0..1')
        manual = data.get('manual', self.manual)
        if manual and manual not in library(): raise ValueError('Unknown archetype')
        backend=data.get('backend',self.backend)
        variant=data.get('variant',self.empathic.variant)
        if variant not in ('small','large'):raise ValueError('Unknown Empathic variant')
        if backend not in ('motion','fast','empathic'):raise ValueError('Unknown expression backend')
        if backend=='empathic' and not model_ready(variant):raise ValueError('40-Kategorien-Modell ist noch nicht eingerichtet.')
        self.enabled = data.get('enabled', self.enabled)
        self.social_enabled = data.get('social', self.social_enabled)
        self.strength, self.manual = strength, manual
        self.backend=backend
        self.empathic.set_variant(variant)
        if backend!='empathic' or manual:self.empathic.close()
        if backend!='fast':self.worker.clear()
        if not self.enabled:
            self.reset()
            self.empathic.close()

    def learn(self, slug):
        if slug not in library(): raise ValueError('Choose an expression first')
        self.learning = {'slug': slug, 'samples': []}

    def update(self, rgb, observation, controls, now):
        dt = .1 if self.last_time is None else max(0, now - self.last_time)
        self.last_time = now
        if observation is None:
            self.reset()
            self.status = {'enabled': self.enabled, 'state': 'no_face', 'candidates': []}
            return controls
        if self.learning is not None:
            self.learning['samples'].append(vector(controls))
            if len(self.learning['samples']) >= 8:
                slug = self.learning['slug']
                self.references.setdefault(slug, []).append(np.median(self.learning['samples'], axis=0))
                self.references[slug] = self.references[slug][-8:]
                self.learning = None
        if not self.enabled:
            self.status = {'enabled': False, 'state': 'off', 'candidates': [], 'learning_remaining': 8 - len(self.learning['samples']) if self.learning else 0}
            return controls
        # The unreliable seven-class model is opt-in legacy only. In particular
        # it must not silently run as a fallback while Empathic is loading.
        if self.backend=='fast' and not self.manual: self.worker.submit(rgb, observation)
        if self.backend=='empathic' and not self.manual:self.empathic.submit(rgb,observation,vector(controls).tolist())
        deep_result=self.empathic.snapshot() if self.backend=='empathic' else None
        result = self.worker.snapshot() if self.backend=='fast' else None
        if result and result['captured'] != self.last_result:
            self.last_result = result['captured']
            self.probabilities = result['scores'] if self.probabilities is None else .48 * result['scores'] + .52 * self.probabilities
        probabilities = self.probabilities if result else None
        negative_mouth = bounded((-controls['smile'] - .015) * 3.5)
        angry_brows = bounded((controls['frown'] - .07) * 4.)
        negative_evidence = max(negative_mouth, angry_brows)
        cue_note = ''
        if probabilities is not None and negative_evidence > .08:
            probabilities = probabilities.copy()
            # Visual negative cues must not be overwritten by a confident but
            # contradictory happy classifier. These are motion-based priors.
            probabilities[3] *= (1 - negative_evidence) ** 3
            probabilities[4] *= 1 - .6 * negative_evidence
            probabilities[0] += angry_brows * .9
            probabilities[5] += negative_mouth * (1 - .65 * angry_brows) * .9
            probabilities /= probabilities.sum()
            cue_note = 'Mundwinkel/Brauen berücksichtigt'
        v = vector(controls)
        distances = np.sqrt(np.mean((self.templates - v) ** 2 * WEIGHTS, axis=1))
        nearest = sorted(range(len(self.items)), key=lambda i: distances[i])
        candidates = [{'slug': self.items[i]['slug'], 'label': self.items[i]['label'],
                       'similarity': round(float(math.exp(-distances[i] * 4)), 3),
                       'taxonomy': self.items[i]['taxonomy']} for i in nearest[:3]]
        target, source, cnn = {}, 'Mimikähnlichkeit', None
        if probabilities is not None:
            index = int(np.argmax(probabilities))
            confidence = float(probabilities[index])
            entropy = -float(np.sum(probabilities * np.log(np.maximum(probabilities, 1e-9)))) / math.log(7)
            certainty = bounded((confidence - .28) / .5) * (1 - entropy) ** .5
            cnn = {'label': LABELS[index], 'class': CLASSES[index], 'score': round(confidence, 3),
                       'ms': round(result['ms'], 1), 'scores': dict(zip(CLASSES, map(float, probabilities))),
                       'cue_adjustment': cue_note}
            # Blend several basic estimates, attenuating uncertain observations.
            for slug, score in zip(CNN_ARCHETYPES, probabilities):
                if slug != 'neutral' and score > .10: target[slug] = float(score) * certainty
            source = 'CNN + Cartoon-Archetyp'
        deep_status={'state':'waiting' if self.empathic.state=='active' else self.empathic.state,'error':self.empathic.error}
        if deep_result is not None:
            scores=deep_result['scores']
            ordered=sorted(scores,key=lambda slug:scores[slug]['adjusted'],reverse=True)
            top=[{'slug':slug,'label':library()[slug]['label'],**scores[slug]} for slug in ordered[:5]]
            activation={slug:bounded((scores[slug]['adjusted']-.3)/2.5) for slug in ordered[:3]}
            activation_sum=sum(activation.values())
            if activation_sum:
                peak=max(activation.values())
                # Slow estimates should fade when the face has visibly changed
                # since capture, rather than impose an expression from seconds ago.
                signature=deep_result.get('signature')
                agreement=math.exp(-8*float(np.sqrt(np.mean((np.asarray(signature)-v)**2*WEIGHTS)))) if signature is not None else 1.
                age_after_inference=max(0.,deep_result['age_seconds']-deep_result['inference_ms']/1000)
                peak*=agreement*math.exp(-age_after_inference/5)
                target={slug:value/activation_sum*peak for slug,value in activation.items() if value>0}
            else:target={}
            source='Empathic '+self.empathic.variant.title()+' · 40 Kategorien'
            deep_status.update(state='active',top=top,scores=scores,age_seconds=deep_result['age_seconds'],
                               inference_ms=deep_result['inference_ms'],calibrating=self.empathic.calibrate_after is not None)
        # All 100 recipes can contribute a modest stylistic prior when the
        # measured motion is close. This is explicitly similarity, not a new
        # 100-way emotion classifier. A confident neutral CNN suppresses it.
        activity = float(np.sqrt(np.mean((vector(NEUTRAL_CONTROLS) - v) ** 2 * WEIGHTS)))
        allowed = [i for i in nearest if self.social_enabled or self.items[i]['taxonomy'].startswith('emonet')][:3]
        if allowed and activity > .10 and distances[allowed[0]] < .27 and (probabilities is None or probabilities[4] < .65):
            amount = .20 * bounded((activity - .10) / .20) * bounded(1 - distances[allowed[0]] / .35)
            weights = np.exp(-np.array([distances[i] for i in allowed]) * 12)
            weights /= weights.sum()
            for i, weight in zip(allowed, weights):
                slug = self.items[i]['slug']
                target[slug] = target.get(slug, 0) + amount * float(weight)
            if deep_result is None:source = 'CNN + Mimikähnlichkeit' if probabilities is not None else 'Mimikähnlichkeit'
        # Social style is only admitted when an observable cue supports it.
        social_slug, social_weight = self.social_cue(controls) if self.social_enabled else ('', 0.)
        if social_slug in library() and social_weight > 0:
            target = {k: weight * (1 - .65 * social_weight) for k, weight in target.items()}
            target[social_slug] = .65 * social_weight
            source = 'Sichtbare Geste + Cartoon-Archetyp'
        if negative_evidence > .1 and not self.manual:
            for slug in list(target):
                if library()[slug]['actions']['smile'] > .2: target[slug] *= (1-negative_evidence)**3
            slug = 'anger' if angry_brows > negative_mouth*.6 else 'sadness'
            target[slug] = max(target.get(slug,0), negative_evidence*.65)
        # A voluntarily taught expression is a CPU nearest-neighbour in motion
        # features. It never compares human photos to cartoon image embeddings.
        if self.references:
            matches = [(float(np.sqrt(np.mean((reference - v) ** 2 * WEIGHTS))), slug)
                       for slug, refs in self.references.items() for reference in refs]
            distance, slug = min(matches)
            neutral_distance = float(np.sqrt(np.mean((vector(NEUTRAL_CONTROLS) - v) ** 2 * WEIGHTS)))
            if distance < .11 and neutral_distance > .07:
                target, source = {slug: bounded(1 - distance / .18)}, 'Dein gelerntes Mimikmuster'
        if self.manual: target, source = {self.manual: 1.}, 'Manuell gewählter Archetyp'
        alpha = -math.expm1(-min(dt, .3) / .28)
        for slug in set(target) | set(self.blend):
            self.blend[slug] = self.blend.get(slug, 0.) + alpha * (target.get(slug, 0.) - self.blend.get(slug, 0.))
        self.blend = {k: v for k, v in self.blend.items() if v > .001}
        total = sum(self.blend.values())
        mixed = dict(controls)
        if total:
            amount = self.strength * min(1., total)
            for key in controls:
                if key in PROTECTED: continue
                authored = sum(library()[slug]['actions'].get(key, controls[key]) * weight for slug, weight in self.blend.items()) / total
                # Keep speech width/asymmetry predominantly direct, even at 100%.
                influence = amount * (.35 if key.startswith('mouth_') else 1.)
                mixed[key] = controls[key] * (1 - influence) + authored * influence
            # Preserve the sign and strength of a deliberately downturned mouth
            # and contracted brow even when the active style is cheerful.
            if controls['smile'] < .02: mixed['smile'] = min(mixed['smile'], controls['smile'])
            if controls['frown'] > .08: mixed['frown'] = max(mixed['frown'], controls['frown'])
            for key in ('brow_raise', 'brow_inner', 'brow_outer', 'frown'):
                # A small common stylistic offset may accompany the emotion,
                # but cannot erase the independently tracked left/right motion.
                delta = mixed[key]-controls[key]
                for side in ('left','right'):
                    name=key+'_'+side
                    if name in controls:mixed[name]=controls[name]+delta
            negative_share = sum(weight for slug,weight in self.blend.items()
                                 if slug in ('anger','sadness','disgust','distress','disappointment','bitterness')) / total
            if negative_share > .55 and self.strength > 0:
                # Resolve a contradictory smiling mouth when a negative style
                # dominates. The guard fades continuously with the user's mix
                # and leaves the zero-strength endpoint exactly unchanged.
                conflict = bounded(self.strength * 4 * negative_share)
                negative_curve = sum(min(-.18,library()[slug]['actions']['smile']) * weight
                                     for slug,weight in self.blend.items()
                                     if slug in ('anger','sadness','disgust','distress','disappointment','bitterness')) / (total*negative_share)
                mixed['smile'] = min(mixed['smile'], controls['smile']*(1-conflict)+negative_curve*conflict)
        dominant = max(self.blend, key=self.blend.get) if self.blend else ''
        self.status = {'enabled': True, 'state': 'active' if total > .05 else 'uncertain',
                       'source': source, 'cnn': cnn, 'candidates': candidates,
                       'archetype': library()[dominant]['label'] if dominant else '',
                       'archetype_slug': dominant, 'effective_strength': round(self.strength * min(1, total), 3),
                       'weights': dict(self.blend), 'cnn_error': self.worker.error,
                       'backend': self.backend, 'empathic': deep_status if self.backend=='empathic' else None,
                       'learning_remaining': 8 - len(self.learning['samples']) if self.learning else 0,
                       'reference_count': sum(map(len, self.references.values()))}
        return mixed

    @staticmethod
    def social_cue(a):
        left, right = a['eye_open'] + a['eye_asym'] / 2, a['eye_open'] - a['eye_asym'] / 2
        if a['tongue_out'] > .20: return 'tongue_tease', a['tongue_out']
        if min(left, right) < .18 and max(left, right) > .65: return 'knowing_wink', .9
        if a['gaze_x_left'] < -.35 and a['gaze_x_right'] > .35: return 'cross_eyed_goof', .9
        if a['gaze_y_left'] < -.45 and a['gaze_y_right'] < -.45: return 'playful_eye_roll', .7
        if abs(a['gaze_y_left'] - a['gaze_y_right']) > .8: return 'wandering_eyes', .8
        if min(left, right) < .18 and a['smile'] > .35: return 'double_wink', .8
        if a['smile'] > .38 and abs(a['gaze_x_left'] + a['gaze_x_right']) > 1.:
            return 'mischievous_side_eye', .6
        return '', 0.
