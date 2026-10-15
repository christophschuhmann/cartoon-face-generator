"""Model-specific reference deviations, separate from training normalization."""
from functools import lru_cache
import json
import math
from pathlib import Path

STYLE_NAMES={'ranting':'S_RANT','whispering':'S_WHIS','dramatic':'S_DRAM','playful':'S_PLAY',
             'monotone':'S_MONO','assertive':'S_AUTH','conversational':'S_CONV','narrative':'S_NARR',
             'tension':'TENS','emphasis':'EMPH','attack':'ATCK','tempo':'TEMP'}


@lru_cache(maxsize=1)
def medium_reference():
    rows=json.loads((Path(__file__).parent/'models/ears/medium/speech_reference.json').read_text(encoding='utf8'))
    return rows['_raw_targets']


def normalize_scores(scores,display,variant='base'):
    if variant=='medium':
        reference=medium_reference();center='mean';name='medium-speech-80265-mean-std'
    else:
        reference={r['name']:r for r in display['targets']};center='median';name='base-release-teacher-median-std'
    z={}
    for key,value in scores.items():
        row=reference.get(key,{})
        if row.get(center) is not None and row.get('std',0)>0:
            z[key]=(value-row[center])/row['std']
    # For auxiliary targets without the speech-reference column, retain the
    # original release reference explicitly rather than inventing statistics.
    release={r['name']:r for r in display['targets']}
    for key in ('eiv_extra:Arousal','eiv_extra:Valence'):
        row=release[key]
        if key not in z:z[key]=(scores[key]-row['median'])/row['std']
    styles={name:{'raw':scores['vn_'+code+'_reg'],'z':z['vn_'+code+'_reg']}
            for name,code in STYLE_NAMES.items()}
    return {'scores_raw':{k:v for k,v in scores.items() if k.startswith('emo_')},
            'scores_z':{k:z[k] for k in scores if k.startswith('emo_')},
            'voice_raw':{k:v for k,v in scores.items() if k.startswith('vn_')},
            'voice_z':{k:z[k] for k in scores if k.startswith('vn_')},'styles':styles,
            'normalization':name,'arousal_raw':scores['eiv_extra:Arousal'],'valence_raw':scores['eiv_extra:Valence'],
            'arousal':max(0.,min(1.,.5+.38*math.tanh(z['eiv_extra:Arousal']/2))),
            'valence':math.tanh(z['eiv_extra:Valence']/2)}
