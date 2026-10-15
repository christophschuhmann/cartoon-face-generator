"""Authored performance patterns for the ORIGINAL 40 cartoon archetypes.

Tempo, aperture, articulation width, lip rounding, roll, nod and sway differ
between styles. These are animation choices, not psychological measurements.
"""
import math
from .mapping import NEUTRAL_CONTROLS, controls_to_pose, bounded
from .speech import mouth_basis
from .empathic import ALIASES
from cartoon_face.emotion_library import resolve_emotion
from cartoon_face.renderer import render_svg

# syllables/s, aperture gain, width gain, pucker, roll degrees, nod px, sway Hz
PATTERNS = {
 'affection':(2.5,.75,.98,.10,2.0,3,.30),
 'amusement':(3.8,1.10,1.10,0,3.2,6,.75),
 'anger':(4.5,1.28,1.05,0,1.4,7,1.15),
 'surprise':(3.5,1.25,.82,.35,1.2,6,.60),
 'awe':(2.1,1.04,.84,.30,1.5,3,.25),
 'bitterness':(2.8,.73,.96,.08,1.3,2,.45),
 'concentration':(3.0,.70,.90,.12,.7,2,.35),
 'confusion':(2.7,.83,.93,.16,3.4,3,.48),
 'contemplation':(2.0,.65,.88,.18,2.1,2,.20),
 'contempt':(2.6,.65,.96,.08,2.2,2,.37),
 'contentment':(2.3,.72,1.02,.04,1.9,2,.26),
 'disappointment':(2.2,.69,.92,.10,1.4,4,.27),
 'disgust':(2.8,.85,1.04,.12,2.8,4,.55),
 'distress':(4.1,1.16,.93,.04,2.5,6,.90),
 'doubt':(2.5,.74,.94,.12,3.0,2,.40),
 'elation':(4.3,1.30,1.14,0,4.2,8,.95),
 'embarrassment':(2.9,.70,.89,.14,2.7,4,.48),
 'numbness':(1.8,.50,.90,.02,.3,1,.14),
 'fatigue':(1.7,.64,.94,.06,1.1,4,.18),
 'fear':(4.4,1.03,.88,.16,1.8,5,1.10),
 'helplessness':(2.4,.85,.90,.08,2.2,4,.32),
 'hope':(3.5,1.04,1.06,.04,2.5,5,.65),
 'impatience':(4.6,.92,.98,.04,2.1,5,1.20),
 'infatuation':(2.6,.79,1.02,.17,3.5,3,.33),
 'interest':(3.2,.88,1.00,.06,1.8,4,.52),
 'intoxication':(2.3,1.03,1.03,.10,5.0,5,.30),
 'envy':(2.8,.72,.94,.06,1.7,2,.42),
 'longing':(2.1,.79,.91,.20,2.5,3,.24),
 'malice':(3.0,.79,1.04,.04,2.8,3,.58),
 'pain':(3.5,1.20,.94,.08,2.4,6,.80),
 'pleasure_ecstasy':(2.8,1.10,1.05,.15,3.5,5,.50),
 'pride':(2.7,.84,1.07,.02,1.6,3,.40),
 'relief':(2.2,.90,1.03,.12,2.0,5,.28),
 'sadness':(1.9,.68,.90,.06,1.5,3,.22),
 'lust':(2.4,.83,.96,.22,2.8,3,.31),
 'shame':(2.0,.59,.87,.08,1.2,3,.23),
 'sourness':(2.7,.72,.82,.32,2.0,3,.46),
 'teasing':(3.4,.95,1.08,.08,4.0,4,.67),
 'gratitude':(2.6,.84,1.05,.04,2.4,5,.39),
 'triumph':(4.0,1.23,1.12,0,3.0,7,.82),
}

def canonical_scores(raw):
    scores={}
    for name,value in raw.items():
        slug=name.removeprefix('emo_').lower()
        slug=ALIASES.get(slug,slug)
        if slug=='jealousy_and_envy':slug='envy'
        if slug not in PATTERNS:raise ValueError('Unmapped audio emotion: '+name)
        value=float(value)
        if not math.isfinite(value):raise ValueError('Invalid emotion score')
        scores[slug]=value
    if set(scores)!=set(PATTERNS):raise ValueError('Expected all 40 audio emotions')
    return scores

UPBEAT = frozenset(('affection','amusement','contentment','elation','hope','infatuation',
                   'pleasure_ecstasy','pride','relief','lust','teasing','gratitude','triumph'))
HOSTILE = frozenset(('anger','impatience','bitterness','contempt','disgust','malice','sourness'))


def expression_mix(segment):
    """Resolve compatible acting cues, keeping the model's scores unmodified.

    Ears heads are simultaneous regression scores, not exclusive probabilities.
    Excited delivery can elevate triumph/elation alongside anger. Require actual
    anger/irritability evidence before tense or ranting delivery suppresses the
    upbeat recipes; loudness, arousal and a speaking style alone never do this.
    """
    scores=canonical_scores(segment.get('scores_z',segment['scores_raw']))
    ranked=sorted(scores,key=scores.get,reverse=True)
    normalized='scores_z' in segment
    threshold=.5 if normalized else .15
    active={k:max(0.,min(4.,v)-threshold)**1.3 for k,v in scores.items()}
    peak=max(active.values(),default=0)
    strength={k:bounded((v-threshold)/(2.5 if normalized else 3.)) for k,v in scores.items()}
    styles=segment.get('styles',{})
    style=lambda key:bounded((styles.get(key,{}).get('z',0)-.5)/2.5)
    delivery=max(style('ranting'),math.sqrt(style('tension')*style('attack')))
    hostility=max(strength['anger'],.82*strength['impatience'])
    aggression=max(.65*strength['anger'],hostility*(.30+.70*delivery))
    priority=bounded((aggression-.18)/.44)
    priority=priority*priority*(3-2*priority)
    for key in active:
        if key in UPBEAT:active[key]*=1-.95*priority
        elif key in HOSTILE:active[key]*=1+.75*priority
    selected=sorted(active,key=lambda k:(active[k],scores[k]),reverse=True)[:3]
    active={k:active[k] for k in selected}
    total=sum(active.values())
    weights={k:v/total for k,v in active.items()} if total else {}
    negative=sum(w for k,w in weights.items() if resolve_emotion(k)['actions']['smile']<-.1)
    return dict(scores=scores,ranked=ranked,weights=weights,peak=peak,
                aggression=aggression,negative=max(negative,aggression))


def performance_controls(segment, mix=None):
    mix=expression_mix(segment) if mix is None else mix
    scores,ranked,weights=mix['scores'],mix['ranked'],mix['weights']
    arousal=bounded(segment['arousal']);valence=bounded(segment['valence'],-1,1)
    intensity=bounded(mix['peak']/(2.6 if 'scores_z' in segment else 3.8))*(.65+.35*arousal)
    aggression=mix['aggression']*intensity
    negative=mix['negative']*intensity
    controls=dict(NEUTRAL_CONTROLS)
    for key in resolve_emotion('neutral')['actions']:
        target=sum(resolve_emotion(k)['actions'][key]*w for k,w in weights.items()) if weights else controls[key]
        controls[key]+=(target-controls[key])*intensity
    # Valence gives a bounded bias without turning a clearly negative archetype
    # into a smile. Loudness subsequently changes only articulation magnitude.
    controls['smile']+=valence*.10*(1-negative)
    if negative>.15:controls['smile']=min(controls['smile'],-.42*negative)
    if aggression>.10:
        controls['smile']=min(controls['smile'],-.70*aggression)
        controls['brow_inner']=min(controls['brow_inner'],-.62*aggression)
        controls['brow_raise']=min(controls['brow_raise'],-.16*aggression)
        controls['brow_asym']*=1-.65*aggression
        controls['frown']=max(controls['frown'],.95*aggression)
        controls['eye_open']=min(controls['eye_open'],1-.48*aggression)
        controls['squint']=max(controls['squint'],.36*aggression)
        controls['lid_tilt']=max(controls['lid_tilt'],.75*aggression)
        controls['mouth_tension']=max(controls['mouth_tension'],.60*aggression)
    controls['cheek_lift']*=1-.90*negative
    controls['warmth']*=1-.55*aggression
    for side,sign in (('left',1),('right',-1)):
        for key in ('brow_raise','brow_inner','brow_outer','frown'):
            controls[key+'_'+side]=controls[key]+(sign*controls['brow_asym'] if key=='brow_raise' else 0)
        controls['squint_'+side]=controls['squint']
        controls['gaze_x_'+side]=controls['gaze_x']
        controls['gaze_y_'+side]=controls['gaze_y']
    pattern=[sum(PATTERNS[k][i]*w for k,w in weights.items()) if weights else (2.5,.6,1,0,0,0,.3)[i] for i in range(7)]
    # Speaking style shapes articulation; only supported hostility tightens the
    # brow. An excited happy speaker or a scared speaker retains their own eyes.
    styles=segment.get('styles',{})
    strength=lambda key:bounded((styles.get(key,{}).get('z',0)-.5)/2.5)
    rant,whisper,dramatic,playful=(strength(k) for k in ('ranting','whispering','dramatic','playful'))
    emphasis=strength('emphasis')
    pattern[0]*=1+.18*rant-.12*whisper
    pattern[1]*=1+.30*rant+.15*emphasis-.40*whisper
    pattern[4]*=1+.20*dramatic+.15*playful-.45*whisper
    pattern[5]*=1+.40*rant+.25*emphasis-.55*whisper
    for side in ('left','right'):
        controls['frown_'+side]=bounded(controls['frown_'+side]+.22*aggression)
        controls['squint_'+side]=bounded(controls['squint_'+side]+.12*aggression)
    controls['mouth_width']*=pattern[2]
    controls['mouth_pucker']=pattern[3]*intensity
    controls['lip_pout']=pattern[3]*intensity
    controls['mouth_open']=0.;controls['tongue_out']=0.
    return controls,pattern,ranked,scores,intensity

def prepare_performance(analysis, progress=None):
    neutral=controls_to_pose(NEUTRAL_CONTROLS)
    analysis['neutral_svg']=render_svg(neutral,870,450,live=True)
    analysis['neutral_mouth']=mouth_basis(neutral,NEUTRAL_CONTROLS)
    for index,segment in enumerate(analysis['segments']):
        mix=expression_mix(segment)
        a,pattern,ranked,scores,intensity=performance_controls(segment,mix)
        affect={key:mix[key]*intensity for key in ('aggression','negative')}
        acting=max(mix['weights'],key=mix['weights'].get) if mix['weights'] else ranked[0]
        variants=[]
        for sign in (-1,1):
            c=dict(a)
            magnitude=(.02+.06*segment['arousal'])*intensity
            c['head_yaw']=sign*magnitude*.45
            c['head_pitch']=sign*magnitude*.35
            for side in ('left','right'):
                c['brow_raise_'+side]+=sign*magnitude*(1-1.5*affect['aggression'])
            c['eye_open']=bounded(c['eye_open']+sign*magnitude*.35*(1-affect['aggression']),.05,1.4)
            pose=controls_to_pose(c)
            variants.append({'svg':render_svg(pose,870,450,live=True),'mouth':mouth_basis(pose,c)})
        segment.update(poses=variants,pattern=dict(zip(('tempo','aperture','width','pucker','roll','nod','sway'),pattern)),
                       dominant=ranked[0],performance_dominant=acting,affect=affect,
                       model_label=resolve_emotion(ranked[0])['label_de'],
                       label=resolve_emotion(acting)['label_de'] if intensity>.04 else 'Ruhiger Ausdruck',
                       scores=scores,score_scale='z' if 'scores_z' in segment else 'raw',intensity=intensity)
        if progress:progress((index+1)/max(1,len(analysis['segments'])))
    return analysis
