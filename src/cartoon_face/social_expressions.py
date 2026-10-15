"""Social performance recipes resolved through the same emotion/101-point rig.

These sixty labels are authored situations. They never extend or renumber the
official forty EmoNet labels, and do not imply measured human recognition.
"""
from functools import lru_cache
from pathlib import Path
import copy,json
import numpy as np
from .emotion_library import resolve_emotion,sample_actions,build_pose
from .model import points,topology,set_xy,refresh_states,validate_pose


@lru_cache(maxsize=1)
def social_catalog():
    return json.loads((Path(__file__).parent/'emotions/social_catalog.json').read_text(encoding='utf-8'))


def resolve_social(name):
    key=str(name).strip().casefold()
    for p in social_catalog()['profiles']:
        if key in (p['slug'].casefold(),p['label_de'].casefold(),str(p['id'])):return copy.deepcopy(p)
    raise ValueError(f'Unknown social expression: {name}')


def social_profile(name):
    target=resolve_social(name);p=resolve_emotion(target['base_emotion'])
    p.update(id=target['id'],slug=target['slug'],label=target['label'],label_de=target['label_de'],family=target['family'])
    p['actions'].update(warmth=.50,gaze_convergence=0.)
    p['actions'].update(target['actions']);p['options'].update(target['options'])
    p['variation'].update(strength=.24,asymmetry=.20,gaze=.28,mouth=.20)
    p['social_constraints']=target['constraints'];return p,target


def social_pose(name,seed=None,variation=.85):
    profile,target=social_profile(name);a,latents=sample_actions(profile,seed,variation)
    c=target['constraints'];opens={'left':a['eye_open']+a['eye_asym']/2,'right':a['eye_open']-a['eye_asym']/2}
    for side in c.get('closed_eyes',[]):opens[side]=.055
    a['eye_open']=(opens['left']+opens['right'])/2;a['eye_asym']=opens['left']-opens['right']
    for axis in ('x','y'):
        field='gaze_'+axis
        if field+'_min' in c:a[field]=max(c[field+'_min'],a[field])
        if field+'_max' in c:a[field]=min(c[field+'_max'],a[field])
    p=build_pose(profile,a)
    # Convergence is an intentional bilateral gaze cue, not independent jitter.
    for side in ('left','right'):
        delta=np.array([(-1 if side=='left' else 1)*a.get('gaze_convergence',0)*45,0.])
        for component in ('pupil','highlight','secondary_highlight'):
            name_=side+'_'+component
            for anchor,q in zip(topology()['components'][name_]['anchors'],points(p,name_)):
                set_xy(p,anchor,q+delta)
    p['name']=target['slug']+(f'_seed{seed}' if seed is not None else '_archetype')
    p['provenance'].update(kind='procedural_social',base_emotion=target['base_emotion'],
       geometry_recipe_version=p['provenance'].get('recipe_version'),recipe_version=social_catalog()['recipe_version'])
    p['expression']={'catalog_id':social_catalog()['catalog_id'],'category_id':target['id'],'slug':target['slug'],
        'label_de':target['label_de'],'label_kind':'intended_social_performance','human_validated':False,
        'weights':[float(i==target['id']-1) for i in range(60)]}
    p['recipe']={'version':social_catalog()['recipe_version'],'catalog_id':social_catalog()['catalog_id'],'seed':seed,
        'variation':float(variation) if seed is not None else 0.,'actions':a,'latents':latents,'options':profile['options'],
        'constraints':copy.deepcopy(c)}
    refresh_states(p);validate_pose(p);return p


def social_cue_checks(p):
    """Protected wink/gaze/tongue cues; no semantic recognition is inferred."""
    c=p['recipe'].get('constraints',{});a=p['recipe']['actions'];failures=[]
    for side in c.get('closed_eyes',[]):
        if p['rig'][side+'_pupil']['openness']>=.08:failures.append(side+' closure lost')
    for axis in ('x','y'):
        f='gaze_'+axis
        if f+'_min' in c and a[f]<c[f+'_min']:failures.append(f+' minimum cue lost')
        if f+'_max' in c and a[f]>c[f+'_max']:failures.append(f+' maximum cue lost')
    if p['recipe']['options']['tongue']!='none' and p['rig']['tongue']['opacity']<=.9:failures.append('tongue cue lost')
    return {'passed':not failures,'failures':failures,'kind':'protected authoring cues, not human recognition'}
