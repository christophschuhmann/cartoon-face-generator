"""CPU-only LAION Buddy keyword detector; no ASR or identity model involved.

The three classifier heads share the frozen openWakeWord mel/embedding front end.
Models and front-end revisions are documented in BUDDY_WAKE.md.
"""
from pathlib import Path
from collections import deque
import asyncio
import re
import time
import numpy as np
import onnxruntime as ort

ROOT=Path(__file__).resolve().parent/'models/buddy-wakeword'
SAMPLE_RATE=16000
WINDOW_SAMPLES=32000
MODEL_FILES={'hey':'hey_buddy_en_large_v3.onnx','go':'go_buddy_en_large_v3.onnx',
             'stop':'stop_buddy_en_large_v3.onnx'}
# Model-card v3 operating points; application-level evaluation is still needed.
THRESHOLDS={'hey':.02,'go':.02,'stop':.02}

# These spellings only confirm a control already proposed by a wakeword head.
# German Parakeet can join both words of the English command into “Gaumadi”.
_BUDDY_NAME=r'(?:buddy|body|bobby|budi|burdy|murdy|maddie|maddy|madi|maggie|bird\s*ie|hobby|wobby)'
_BREAK=r'[\s,.:;!?-]*'
_GO_END=re.compile(r'(?<!\w)(?:(?:go[\s,.:;!?-]+'+_BUDDY_NAME+r'|(?:go|gau)(?:madi|mardi|buddy))'+_BREAK+r')+$',re.I)
_STOP_END=re.compile(r'(?<!\w)stop+p?[\s,.:;!?-]+'+_BUDDY_NAME+_BREAK+r'$',re.I)
_WAKE_START=re.compile(r'^\s*(?:(?:hey|hi)[\s,.:;!?-]+)?(?:buddy|body|bobby|bird\s*ie|burdy|murdy)\b'+_BREAK+
                       r'|^\s*(?:hey|hi)[\s,.:;!?-]+'+_BUDDY_NAME+r'\b'+_BREAK,re.I)

async def confirm_go_tail(asr,model,audio,full):
    """Verify an independently detected Go and recover just the preceding request."""
    tail_size=38400  # 2.4 s at 16 kHz, including the browser's post-roll
    if model not in ('parakeet_ultra','parakeet_redux') or len(audio)<=tail_size:return None
    tail=await asr.transcribe(model,audio[-tail_size:],word_times=True)
    rows=tail.get('timestamps') or []
    words=' '.join(row['word'] for row in rows)
    match=_GO_END.search(words)
    if not match or len(words.split())!=len(rows):return None
    first=len(words[:match.start()].split())
    onset=rows[first]['start']
    if not 0<=onset<tail_size/SAMPLE_RATE:return None
    cut=len(audio)-tail_size+round(onset*SAMPLE_RATE)
    if full.get('timestamps'):
        return ' '.join(row['word'] for row in full['timestamps'] if row['start']*SAMPLE_RATE<cut)
    # Long recordings are transcribed in overlapping chunks. Their reported
    # token times are not globally aligned, so decode the confirmed prefix.
    return (await asr.transcribe(model,audio[:cut]))['text']

class BuddyDetector:
    def __init__(self,root=ROOT):
        options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
        def load(name):return ort.InferenceSession(str(root/name),sess_options=options,providers=['CPUExecutionProvider'])
        self.mel=load('melspectrogram.onnx');self.embedding=load('embedding_model.onnx')
        self.models={key:load(name) for key,name in MODEL_FILES.items()}
        self.v2={key:load(name.replace('_v3.onnx','_v2.onnx')) for key,name in MODEL_FILES.items()}

    def predict(self,audio):
        audio=np.asarray(audio,dtype=np.float32).reshape(-1)
        if len(audio)<WINDOW_SAMPLES:audio=np.pad(audio,(WINDOW_SAMPLES-len(audio),0))
        else:audio=audio[-WINDOW_SAMPLES:]
        out=self.mel.run(None,{self.mel.get_inputs()[0].name:audio.reshape(1,-1)})[0]
        mel=np.asarray(out,dtype=np.float32).reshape(-1,32)/10.+2.
        frames=[mel[i:i+76] for i in range(0,len(mel)-75,8)]
        if len(frames)<16:return {key:0. for key in self.models}
        batch=np.stack(frames[-16:],axis=0).astype(np.float32)[...,None]
        emb=self.embedding.run(None,{self.embedding.get_inputs()[0].name:batch})[0].reshape(1,16,96)
        return {key:float(model.run(None,{model.get_inputs()[0].name:emb})[0][0,0]) for key,model in self.models.items()}

    def predict_both(self,audio):
        # Reuse the front end across all six heads.
        audio=np.asarray(audio,dtype=np.float32).reshape(-1)[-WINDOW_SAMPLES:]
        if len(audio)<WINDOW_SAMPLES:audio=np.pad(audio,(WINDOW_SAMPLES-len(audio),0))
        mel=self.mel.run(None,{self.mel.get_inputs()[0].name:audio.reshape(1,-1)})[0].reshape(-1,32)/10.+2.
        frames=[mel[i:i+76] for i in range(0,len(mel)-75,8)]
        if len(frames)<16:return {},{}
        batch=np.stack(frames[-16:],axis=0).astype(np.float32)[...,None]
        emb=self.embedding.run(None,{self.embedding.get_inputs()[0].name:batch})[0].reshape(1,16,96)
        def scores(models):return {key:float(m.run(None,{m.get_inputs()[0].name:emb})[0][0,0]) for key,m in models.items()}
        return scores(self.models),scores(self.v2)

def choose(state,v3,v2):
    """Experimental conservative cross-head arbitration; not calibrated."""
    if not v3 or not v2:return None
    if state=='waiting':
        if v3['hey']>=.20 and v2['hey']>=.4 and v2['hey']>max(v2['go'],v2['stop'])+.08:return 'hey'
    elif state in ('recording','processing'):
        if v2['stop']>=.5 and v2['stop']>v2['go']+.005 and v3['stop']>=.3:return 'stop'
        if state=='recording' and v2['go']>=.5 and v2['go']>v2['stop']+.23 and v3['go']>=.3:return 'go'
    return None

_detector=None
def detector():
    global _detector
    if _detector is None:_detector=BuddyDetector()
    return _detector

class BuddySession:
    def __init__(self,conversation):
        self.c=conversation;self.enabled=True;self.state='waiting';self.closed=False
        self.ring=deque();self.samples=0;self.last_probe=0;self.probe=None;self.jobs=set()
        self.capture=[];self.capture_start=0;self.last_event=-1e9
        self.browser_mode=False

    async def notice(self,reason=None,command_hint=None):
        if not self.c.ws.closed:
            await self.c.ws.send_json({'type':'buddy_wake','enabled':self.enabled,'state':self.state,
                'reason':reason,'recorded_s':round(sum(len(x) for x in self.capture)/16000,1),
                'command_hint':command_hint,
                'models':'LAION Buddy v3 + v2 arbiter','asr_in_standby':False})

    async def configure(self,enabled):
        self.enabled=bool(enabled);self.browser_mode=False;self.state='waiting';self.capture=[]
        self.ring.clear();self.samples=0;self.last_probe=0;self.last_event=-1e9
        if self.probe and not self.probe.done():self.probe.cancel()
        for job in self.jobs:job.cancel()
        if self.c.sentence_stream:
            self.c.sentence_stream.admission_epoch+=1;self.c.sentence_stream.reset_segment()
        self.c.session.reset();self.c.mic=np.zeros(0,np.float32);self.c.ear=np.zeros(0,np.float32)
        self.c.mic_pos=self.c.hop_pos=self.c.input_samples
        self.c.input_isolation.output_samples=self.c.input_samples
        await self.notice('Waiting for Hey Buddy' if enabled else 'Buddy mode disabled')

    async def receive(self,pcm):
        if self.closed:return
        if self.browser_mode:
            if self.state=='recording':
                self.capture.append(np.asarray(pcm,dtype=np.float32).copy())
                if sum(map(len,self.capture))>60*SAMPLE_RATE:
                    self.capture=[];self.state='waiting';await self.notice('Recording exceeded 60 seconds')
            return
        x=np.asarray(pcm,dtype=np.float32).copy();start=self.samples;self.samples+=len(x)
        self.ring.append((start,x))
        while self.ring and self.ring[0][0]+len(self.ring[0][1])<self.samples-WINDOW_SAMPLES:self.ring.popleft()
        if self.state in ('recording','processing'):
            self.capture.append(x)
            if sum(map(len,self.capture))>60*SAMPLE_RATE:
                self.capture=[];self.state='waiting';self.c.sentence_stream.admission_epoch+=1
                for job in self.jobs:job.cancel()
                await self.notice('Recording exceeded 60 seconds; say Hey Buddy to try again')
        if self.samples-self.last_probe<3200 or self.samples<16000 or self.probe and not self.probe.done():return
        self.last_probe=self.samples;end=self.samples;state=self.state
        window=np.concatenate([part for _,part in self.ring])[-WINDOW_SAMPLES:]
        async def run():
            try:
                model=await asyncio.to_thread(detector);v3,v2=await asyncio.to_thread(model.predict_both,window)
                event=choose(state,v3,v2)
                if self.closed or not self.enabled or state!=self.state or not event:return
                if end-self.last_event<12000:return
                self.last_event=end
                if event=='hey':
                    # Keep a short pre-roll: a user may start the request
                    # before the wake classifier has finished its window.
                    self.state='recording';self.capture_start=max(0,end-int(.8*SAMPLE_RATE))
                    self.capture=[part[max(0,self.capture_start-at):].copy() for at,part in self.ring
                                  if at+len(part)>self.capture_start]
                    await self.notice('Hey Buddy detected — recording until Go Buddy or Stop Buddy')
                elif event=='stop':
                    if self.state=='processing':
                        self.state='waiting';self.capture=[];self.c.sentence_stream.admission_epoch+=1
                        for task in self.jobs:task.cancel()
                        await self.notice('Stop Buddy detected — recording discarded')
                    else:
                        self.state='processing';n=max(0,end-self.capture_start)
                        audio=np.concatenate(self.capture)[:n] if self.capture else np.zeros(0,np.float32)
                        await self.notice('Checking Stop Buddy')
                        job=asyncio.create_task(self.submit(audio,action='stop'));self.jobs.add(job);job.add_done_callback(self.jobs.discard)
                elif event=='go':
                    self.state='processing';n=max(0,end-self.capture_start)
                    audio=np.concatenate(self.capture)[:n] if self.capture else np.zeros(0,np.float32)
                    await self.notice('Go Buddy detected — checking and transcribing')
                    job=asyncio.create_task(self.submit(audio));self.jobs.add(job);job.add_done_callback(self.jobs.discard)
            except asyncio.CancelledError:raise
            except Exception as exc:
                self.state='unavailable';await self.notice('Wake detector unavailable: '+type(exc).__name__)
        self.probe=asyncio.create_task(run())

    async def browser_command(self,command):
        """Accept a bounded recording only after the browser detects a command."""
        if not self.enabled:return
        self.browser_mode=True
        if command=='ready':
            self.capture=[];self.state='waiting';await self.notice('Wake words running locally in browser')
        elif command=='begin':
            self.capture=[];self.state='recording'
        elif command in ('go','stop') and self.state=='recording':
            self.state='processing'
            audio=np.concatenate(self.capture) if self.capture else np.zeros(0,np.float32)
            job=asyncio.create_task(self.submit(audio,action=command));self.jobs.add(job);job.add_done_callback(self.jobs.discard)
        elif command=='cancel':
            self.capture=[];self.state='waiting';self.c.sentence_stream.admission_epoch+=1
            for job in self.jobs:job.cancel()
            await self.notice('Recording discarded')

    async def submit(self,audio,action='go'):
        ss=self.c.sentence_stream;epoch=ss.admission_epoch
        try:
            # Wake scores can cross threshold before the command's final
            # syllable. Include the subsequent audio before verifying it.
            await asyncio.sleep(.5)
            if self.capture:audio=np.concatenate(self.capture)
            if epoch!=ss.admission_epoch or not self.enabled:return
            if len(audio)<3200:raise ValueError('No recorded speech')
            model=ss.effective_final_model();tick=time.perf_counter()
            if model=='nemotron':
                async with self.c.speaker_ext.asr_slot(0):
                    result=await asyncio.to_thread(self.c.ears.service.engine.asr.transcribe,[audio])
                text=result[0] if result else ''
            else:
                full=await ss.asr.transcribe(model,audio,word_times=self.browser_mode and action=='go')
                text=full['text']
            # The small browser Go head can also fire on an actual Stop Buddy.
            # A transcribed terminal Stop discards this take before any submission.
            if self.browser_mode and action=='go' and _STOP_END.search(text):
                action='stop'
            suffix=_GO_END if action=='go' else _STOP_END
            confirmed_prefix=None
            if self.browser_mode and action=='go' and model!='nemotron' and not suffix.search(text):
                confirmed_prefix=await confirm_go_tail(ss.asr,model,audio,full)
            if confirmed_prefix is None and not suffix.search(text):
                self.state='recording';await self.notice('Command was uncertain; still recording',' '.join(text.split()[-3:]))
                return
            if action=='stop':
                self.capture=[];self.state='waiting';ss.admission_epoch+=1
                await self.notice('Stop Buddy confirmed — recording discarded');return
            text=_WAKE_START.sub('',suffix.sub('',confirmed_prefix if confirmed_prefix is not None else text)).strip().rstrip(' ,.:;!?-')
            if not text:raise ValueError('No spoken request recognized')
            if epoch!=ss.admission_epoch or not self.enabled:return
            asr={'model':model,'endpoint_reason':'buddy_go','buddy_control':True,'transcribe_ms':round((time.perf_counter()-tick)*1000,2)}
            at=self.c.input_samples/16000
            ss.queue.put_nowait((text,audio,at,time.perf_counter(),None,asr,None,ss.admission_epoch,None))
            await self.c.ws.send_json({'type':'asr_sentence','text':text,'queued':self.c.speaking,'reason':'Go Buddy','asr':asr})
            self.capture=[];self.state='waiting';await self.notice('Request submitted — waiting for Hey Buddy')
        except asyncio.CancelledError:raise
        except Exception as exc:
            # A transient ASR/service failure must not discard the user's request.
            # Keep collecting until the user retries Go/Stop or the 60 s cap.
            self.state='recording'
            await self.notice('Could not confirm command; still recording: '+type(exc).__name__)

    async def close(self):
        self.closed=True
        tasks=[t for t in [self.probe,*self.jobs] if t and not t.done()]
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
