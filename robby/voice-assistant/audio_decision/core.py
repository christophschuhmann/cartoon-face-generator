"""Validated settings, causal score processing and explicit missing intervals."""
import csv,io,json,math
from pathlib import Path
from pydantic import BaseModel,Field,model_validator

TAXONOMY=json.loads((Path(__file__).parent/'data/taxonomy.json').read_text())
COMMON=['Speech','Music','Silence','Dog','Bark','Cat','Meow','Laughter','Clapping','Knock','Beep, bleep','Water','Splash, splatter','Car','Bird','Telephone bell ringing']

class Settings(BaseModel):
    taxonomy:str='strong'
    selected_ids:list[str]|None=None
    hop_ms:int=Field(default=200,ge=100,le=1000,multiple_of=100)
    window_s:float=Field(default=10,ge=2,le=20)
    context:str=Field(default='',max_length=4000)
    use_context:bool=True
    repeat_target:bool=False
    method:str='binary'
    group_size:int=16
    feedback:bool=False
    ema_ms:int=Field(default=200,ge=0,le=2000)
    on_threshold:float=Field(default=.6,ge=0,le=1)
    off_threshold:float=Field(default=.4,ge=0,le=1)
    gap_ms:int=Field(default=0,ge=0,le=300)
    @model_validator(mode='after')
    def check(self):
        if self.taxonomy not in ('strong','classic'):raise ValueError('Unknown taxonomy')
        if self.method not in ('binary','multilabel'):raise ValueError('Unknown decision method')
        if self.group_size not in (1,4,8,16,32,64):raise ValueError('Unsupported question group size')
        if self.off_threshold>self.on_threshold:raise ValueError('Off threshold exceeds on threshold')
        ids={x['id'] for x in TAXONOMY[self.taxonomy]}
        if self.selected_ids is not None and (not self.selected_ids or len(set(self.selected_ids))!=len(self.selected_ids) or set(self.selected_ids)-ids):raise ValueError('Invalid class selection')
        return self
    def classes(self):
        wanted=set(self.selected_ids) if self.selected_ids is not None else None
        return [x for x in TAXONOMY[self.taxonomy] if wanted is None or x['id'] in wanted]

def intervals(samples,hop_ms):
    step=hop_ms*16
    return [(i,start,min(samples,start+step)) for i,start in enumerate(range(0,samples,step))]

def process_rows(rows,classes,config):
    """Causal EMA and hysteresis; missing rows reset state and are never filled."""
    s=Settings.model_validate(config);count=len(classes);state=[None]*count;active=[False]*count;low=[0.]*count
    smooth=[];events=[];open_events={}
    for row in rows:
        values=row['raw'];dt=row['end_s']-row['start_s'];current=[]
        alpha=1. if s.ema_ms==0 else -math.expm1(-dt*1000/s.ema_ms)
        for j,p in enumerate(values):
            if p is None:
                state[j]=None;active[j]=False;low[j]=0.;value=None
            else:
                value=p if state[j] is None else alpha*p+(1-alpha)*state[j];state[j]=value
                if not active[j] and value>=s.on_threshold:active[j]=True
                if active[j]:
                    low[j]=low[j]+dt*1000 if value<s.off_threshold else 0.
                    if value<s.off_threshold and low[j]>s.gap_ms:active[j]=False
            current.append(value)
            if active[j] and value is not None:
                event=open_events.setdefault(j,{'class_id':classes[j]['id'],'start_time':row['start_s'],'end_time':row['end_s'],'peak_score':value,'sum':0.,'count':0})
                event.update(end_time=row['end_s'],peak_score=max(event['peak_score'],value),sum=event['sum']+value,count=event['count']+1)
            elif j in open_events:
                event=open_events.pop(j);event['mean_score']=event.pop('sum')/event.pop('count');events.append(event)
        smooth.append(current)
    for event in open_events.values():event['mean_score']=event.pop('sum')/event.pop('count');events.append(event)
    return smooth,events

def csv_export(result,smoothed=False):
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['start_s','end_s','status']+[c['id']+' '+c['name'] for c in result['classes']])
    values=result['smoothed_scores'] if smoothed else [r['raw'] for r in result['rows']]
    for row,values in zip(result['rows'],values):writer.writerow([row['start_s'],row['end_s'],row['status']]+['' if p is None else p for p in values])
    return output.getvalue()
