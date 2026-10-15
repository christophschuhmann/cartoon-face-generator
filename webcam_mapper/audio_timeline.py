"""Word-aligned motion timing. No classifier or model imports in this module."""
import math
import numpy as np


def group_words(result, duration, maximum_words=3):
    words=[]
    for segment in result.get('segments', []):
        for item in segment.get('words', []):
            start,end=float(item['start']),float(item['end'])
            if not math.isfinite(start+end): continue
            start,end=max(0.,start),min(duration,end)
            if end<=start: continue
            words.append({'start':start,'end':end,'word':str(item.get('word',item.get('text','')))})
    words.sort(key=lambda w:w['start'])
    groups=[]; current=[]
    for word in words:
        # Never bridge a real pause just to fill a three-word bucket.
        if current and (len(current)>=maximum_words or word['start']-current[-1]['end']>.35 or word['end']-current[0]['start']>2.8):
            groups.append(current);current=[]
        current.append(word)
    if current: groups.append(current)
    return words,[{'start':g[0]['start'],'end':g[-1]['end'],'text':' '.join(w['word'].strip() for w in g),'words':g} for g in groups]


def loudness_envelope(wave, rate=16000, step=.02):
    wave=np.asarray(wave,dtype=np.float32)
    if wave.ndim!=1 or not np.isfinite(wave).all(): raise ValueError('Invalid audio waveform')
    hop=round(rate*step)
    padded=np.pad(wave,(0,(-len(wave))%hop))
    rms=np.sqrt(np.mean(padded.reshape(-1,hop)**2,axis=1)) if len(wave) else np.zeros(0)
    # Keep relative dynamics across the whole recording, not per segment.
    reference=max(.01,float(np.percentile(rms,95))) if len(rms) else .01
    level=np.clip((rms-.002)/reference,0,1)**.65
    return {'step':step,'values':np.round(level,4).tolist(), 'rms':np.round(rms,6).tolist()}


def audible_words(words, envelope):
    rms=envelope['rms'];step=envelope['step']
    return [w for w in words if max(rms[int(w['start']/step):max(int(w['start']/step)+1,math.ceil(w['end']/step))] or [0])>.003]
