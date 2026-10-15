"""Small mouth-only SVG morph basis for browser-side speech bridging."""
import copy
from cartoon_face.emotion_library import _mouth, resolve_emotion
from cartoon_face.components import render_mouth
from cartoon_face.projection import FaceProjection


def mouth_basis(pose, controls):
    result = []
    for openness in (0., .6):
        p = copy.deepcopy(pose)
        p['_live_preview'] = True
        p['_projection'] = FaceProjection(p.get('head_pose', {}))
        options = dict(resolve_emotion('neutral')['options'], mouth='open', tongue='none')
        _mouth(p, dict(controls, mouth_open=openness), options)
        result.append({s['id']: {'d':s['d'], 'opacity':s.get('opacity',1.)}
                       for s in render_mouth(p) if s['id'] in ('mouth_fill','mouth_upper','mouth_lower')})
    return {'closed':result[0], 'open':result[1], 'range':.6}
