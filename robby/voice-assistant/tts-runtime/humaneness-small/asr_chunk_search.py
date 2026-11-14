"""ASR-only sequential best-of-N. Real batches, one irrevocable winning history.

No VoiceCLAP/quality model, no post-generation ASR pass. Scores are noisy search
surrogates, not a guarantee of word correctness. Original samples stay in RAM.
"""
import time
from types import SimpleNamespace
import numpy as np
from streaming_boundaries import BoundaryASR, boundary_tokens, RATE, UnverifiedSpeechError


def align_prefix(reference, hypothesis, final=False):
    """Edit alignment to the best target prefix, retaining real matched positions."""
    m,n=len(reference),len(hypothesis)
    d=[[0]*(n+1) for _ in range(m+1)]
    for i in range(m+1):d[i][0]=i
    for j in range(n+1):d[0][j]=j
    for i in range(1,m+1):
        for j in range(1,n+1):
            d[i][j]=min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(reference[i-1]!=hypothesis[j-1]))
    endpoint=m if final else min(range(m+1),key=lambda i:(d[i][n],abs(i-n),-i))
    i,j=endpoint,n;matches=[]
    while i or j:
        if i and j and d[i][j]==d[i-1][j-1]+(reference[i-1]!=hypothesis[j-1]):
            if reference[i-1]==hypothesis[j-1]:matches.append((i-1,j-1))
            i-=1;j-=1
        elif i and d[i][j]==d[i-1][j]+1:i-=1
        else:j-=1
    return {'errors':d[endpoint][n],'matched_prefix_words':endpoint,'matches':list(reversed(matches)),
            'prefix_wer':d[endpoint][n]/max(1,endpoint)}


class ASRSearchScorer:
    def __init__(self,asr,check_cancel=lambda:None,window_seconds=12.):
        self.reader=BoundaryASR(asr);self.device='private ASR worker / resident fallback'
        self.check_cancel=check_cancel;self.window_seconds=window_seconds
        self.history=[];self.rows=[];self.last_timing={}

    def score(self,waves,text,final):
        start=time.perf_counter();self.check_cancel();ref=boundary_tokens(text)
        duration=max((len(w)/RATE for w in waves),default=0.)
        offset=max(0.,duration-self.window_seconds)
        # Keep three prior words as an overlap anchor. ASR word timestamps can
        # shift across decodes; timestamp-only slicing used to lose old words.
        if offset and self.history:
            crossing=next((i for i,w in enumerate(self.history) if w['end']>=offset),len(self.history)-1)
            offset=max(0.,self.history[max(0,crossing-3)]['start']-.15)
            offset=max(offset,duration-27.)  # private ASR accepts at most 28 seconds
        first=int(offset*RATE);offset=first/RATE
        prefix=[w for w in self.history if w['end']<offset-.02]
        gates=[SimpleNamespace(buffer=w[first:],total=max(0,len(w)-first),last_scan=0,
            report={'asr_calls':0,'asr_ms':0.}) for w in waves]
        for attempt in range(2):
            self.check_cancel()
            rows=self.reader.scores(gates)
            if not any('asr_error' in g.report for g in gates):break
            if attempt:raise UnverifiedSpeechError('Candidate ASR unavailable after two bounded attempts')
            for g in gates:g.report.pop('asr_error',None)
            time.sleep(.15)
        self.rows=[]
        for index,(g,row,wave,is_final) in enumerate(zip(gates,rows,waves,final)):
            recent=[]
            for w in row.get('timestamps',[]):
                a,b=float(w['start'])+offset,float(w['end'])+offset
                if not np.isfinite([a,b]).all() or not 0<=a<=b<=len(wave)/RATE+.08:continue
                recent.extend({'word':t,'start':a,'end':b} for t in boundary_tokens(w['word']))
            spans,anchored=merge_history(self.history,recent,offset,prefix)
            # A clipped final word is unstable until a little more audio exists.
            stable=spans if is_final else [w for w in spans if w['end']<=len(wave)/RATE-.10]
            result=align_prefix(ref,[w['word'] for w in stable],is_final)
            pairs=result.pop('matches');matched=len(pairs)
            early=[(i,j) for i,j in pairs if i<4]
            opening=(len(early)>=min(2,len(ref)) and early[0][0]==0)
            ending=bool(pairs and pairs[-1][0]==len(ref)-1 and matched/max(1,len(ref))>=.85
                and [i for i,j in pairs[-min(2,len(ref)):]]==list(range(max(0,len(ref)-2),len(ref))))
            # Reward actual progress as well as low errors. Pure inverse WER
            # would prefer repeatedly saying one easy word or stopping early.
            reward=(matched-2*result['errors'])/max(1,len(ref))
            self.rows.append({**result,'reward':reward,'ranking_available':True,'matched_words':matched,
                'hyp':' '.join(w['word'] for w in stable),'timestamps':spans,'sec':len(wave)/RATE,
                'start_s':stable[early[0][1]]['start'] if opening else None,
                'end_s':stable[pairs[-1][1]]['end'] if ending else None,
                'complete':ending,'asr_backend':g.report.get('backend'),'asr_batch_size':g.report.get('asr_batch_size',0),
                'asr_window_start_s':offset,'history_anchor':anchored,'asr_retries':attempt})
        elapsed=time.perf_counter()-start
        self.last_timing={'asr_seconds':elapsed,'quality_seconds':0.,'total_seconds':elapsed}
        return self.rows

    def select(self,index):
        self.history=list(self.rows[index]['timestamps'])


def merge_history(history,recent,offset,fallback_prefix):
    """Keep old words before a time-consistent exact 2/3-word overlap."""
    if offset<=0:return recent,True
    anchors=[]
    for j in range(min(8,len(recent))):
        for i in range(len(history)):
            delta=abs(history[i]['start']-recent[j]['start'])
            if delta>.6:continue
            for count in (3,2):
                if i+count>len(history) or j+count>len(recent):continue
                if [w['word'] for w in history[i:i+count]]==[w['word'] for w in recent[j:j+count]]:
                    anchors.append((j,-count,delta,i));break
    if anchors:
        j,_,_,i=min(anchors)
        return list(history[:i])+recent[j:],True
    return list(fallback_prefix)+recent,False


class SearchCommitter:
    """Use selection timestamps for 100-ms edge fades, without running ASR again."""
    def __init__(self,emit,check_cancel=lambda:None,trim=True):
        self.emit=emit;self.check_cancel=check_cancel;self.trim=trim
        self.buffer=np.zeros(0,np.float32);self.cursor=0;self.start=None;self.done=False
        self.report={'verification_mode':'candidate_search','asr_postcheck':False,'emitted_seconds':0.,
            'start_verified':False,'end_verified':False,'candidate_selection_only':True}
    def feed(self,wave,detail):
        self.check_cancel();self.buffer=np.concatenate((self.buffer,wave))
        score=detail['scores'][detail['retained_rows'][0]]
        if self.start is None:
            if not self.trim:self.start=0
            elif score.get('start_s') is not None:self.start=max(0,int((score['start_s']-.10)*RATE))
            elif len(self.buffer)>=3.84*RATE:raise UnverifiedSpeechError('No candidate contains the expected opening yet')
            if self.start is not None:
                self.cursor=self.start;self.report['start_verified']=score.get('start_s') is not None
        if self.start is None:return False
        end=score.get('end_s') if self.trim else None
        self.done=end is not None
        stop=min(len(self.buffer),int((end+.10)*RATE)) if self.done else max(self.cursor,len(self.buffer)-int(.10*RATE))
        self._release(stop,detail,self.done)
        if self.done:self.report['end_verified']=True
        return self.done
    def _release(self,stop,detail,final):
        if stop<=self.cursor:return
        audio=self.buffer[self.cursor:stop].copy();pos=np.arange(self.cursor,stop)
        audio*=np.clip((pos-self.start)/(RATE*.10),0,1)
        if final:audio*=np.clip((stop-1-pos)/(RATE*.10),0,1)
        self.cursor=stop;self.report['emitted_seconds']+=len(audio)/RATE
        self.emit(audio,{**detail,'live_alignment':dict(self.report)})
    def finish(self):
        if self.start is None:raise UnverifiedSpeechError('No candidate established a recognizable opening')
        if not self.done:self._release(len(self.buffer),{'step':-1,'retained_rows':[0]},True)
