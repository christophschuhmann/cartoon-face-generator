"""Optional 40-ms input filter with sample-exact playback tags and raw fallback.

The microphone clock never skips, repeats or invents audio on model switches.
Filtering precedes both ASR and VAD/TYGER. Environmental captions keep their raw
branch. References and the bounded raw ring disappear with the browser session.
"""
import asyncio
from collections import deque
import struct
import time
import numpy as np
from input_isolation_process import GPUWorker,reserve,close_worker

SR=16000
HEADER=struct.Struct('<ii')
MODELS={'off':'Off · original microphone','voxlock':'VoxLock · CUDA Graphs',
        'scicom':'Scicom Agent · CUDA Graphs'}


def unpack(data):
    if len(data)<8 or (len(data)-8)%2:return None
    rid,at=HEADER.unpack_from(data)
    return rid,at,np.frombuffer(data,dtype='<i2',offset=8).astype(np.float32)/32768.


class TaggedAudio:
    """Keep the ORIGINAL playback label for each delayed filtered output sample."""
    def __init__(self):self.parts=deque();self.size=0
    def append(self,data):
        rid,at,x=unpack(data);self.parts.append([rid,at,x,0]);self.size+=len(x)
    def take(self,wave=None):
        remaining=self.size if wave is None else len(wave)
        if remaining>self.size:raise ValueError('Filter produced too many samples')
        packets=[];pos=0
        while remaining:
            rid,at,x,used=self.parts[0];n=min(remaining,len(x)-used)
            y=x[used:used+n] if wave is None else wave[pos:pos+n]
            tag=at+round(used*24000/SR) if at>=0 else -1
            pcm=np.clip(np.rint(y*32768),-32768,32767).astype('<i2')
            packets.append(HEADER.pack(rid,tag)+pcm.tobytes())
            self.parts[0][3]+=n;pos+=n;remaining-=n;self.size-=n
            if used+n==len(x):self.parts.popleft()
        return packets


class InputIsolation:
    def __init__(self,conversation,worker_factory=GPUWorker):
        self.c=conversation;self.factory=worker_factory;self.worker=None
        self.selected='off';self.phase='off';self.reason='Original microphone audio'
        self.reference=None;self.reference_speaker=None;self.reference_name=None
        self.ring=deque();self.raw_samples=0;self.pending=TaggedAudio();self.partial=np.zeros(0,np.float32)
        self.capture=None;self.capture_size=0;self.capture_voiced=0
        self.lock=asyncio.Lock();self.epoch=0;self.tasks=set();self.closed=False
        self.compute_ms=None;self.last_notice=0.;self.processed_chunks=0;self.filtered_samples=0
        self.worker_loaded=False;self.gpu='1'
        self.references={};self.collected={};self.authorized=set();self.names={};self.seen=deque(maxlen=30)
        self.bank_version=0;self.invite_until=0.
        self.collection_end={}
        self.output_ring=deque();self.output_samples=0
        from input_isolation_wake import RawWakeRecovery
        self.wake_recovery=RawWakeRecovery(self)

    def state(self):
        return {'type':'input_isolation','selected':self.selected,'phase':self.phase,'reason':self.reason,
            'active':self.phase=='active','chunk_ms':40,'gpu':self.gpu,'cuda_graphs':True,
            'reference_s':round(len(self.reference)/SR,2) if self.reference is not None else 0,
            'reference_name':self.reference_name,'capture_s':round(self.capture_size/SR,1),
            'known_voices':[{'id':sid,'name':self.names.get(sid,sid),'seconds':round(len(self.collected.get(sid,[]))/SR,2),'ready':sid in self.references} for sid in sorted(self.authorized)],
            'auto_enrollment':True,'reference_target_s':4,'max_filtered_voices':4,
            'raw_wake_recovery':self.wake_recovery.state(),
            'compute_ms':None if self.compute_ms is None else round(self.compute_ms,2),
            'held_audio_ms':round(self.pending.size/SR*1000,2),'chunks':self.processed_chunks,
            'filtered_samples':self.filtered_samples,'storage':'Session RAM only; no audio saved'}

    async def notice(self,force=False):
        if self.closed or getattr(self.c.ws,'closed',False):return
        now=time.monotonic()
        if force or now-self.last_notice>.5:
            self.last_notice=now
            await self.c.ws.send_json(self.state())

    def task(self,coro):
        t=asyncio.create_task(coro);self.tasks.add(t);t.add_done_callback(self.tasks.discard);return t

    async def _emit(self,packets):
        for packet in packets:
            _,_,x=unpack(packet);start=self.output_samples/SR;self.output_samples+=len(x);end=self.output_samples/SR
            self.output_ring.append((start,end,x))
            while self.output_ring and self.output_ring[0][1]<end-30:self.output_ring.popleft()
            await self.c._deliver_microphone(packet)

    async def _drain(self):
        """Flush only unheard samples, including a sub-40-ms final fragment."""
        packets=[]
        if self.pending.size and self.worker:
            try:
                r=await asyncio.to_thread(self.worker.request,{'op':'flush','audio':self.partial},.5)
                if len(r['audio'])!=self.pending.size:raise ValueError('Filter tail length mismatch')
                packets=self.pending.take(r['audio'])
            except Exception:packets=self.pending.take()  # Never lose buffered input on failure.
        elif self.pending.size:packets=self.pending.take()
        self.partial=np.zeros(0,np.float32)
        await self._emit(packets)

    async def configure(self,model):
        if model not in MODELS:raise ValueError('Choose off, voxlock or scicom')
        async with self.lock:
            if model==self.selected and self.phase in ('off','loading','waiting_reference','preparing_reference','active'):
                await self.notice(True);return
            self.epoch+=1;epoch=self.epoch
            await self._drain()
            old,self.worker=self.worker,None;self.worker_loaded=False;self.capture=None
            self.selected=model;self.phase='off' if model=='off' else 'loading'
            self.reason='Original microphone audio' if model=='off' else 'Loading CUDA model; microphone remains unfiltered'
            await close_worker(old)
            await self.notice(True)
            if model!='off':self.task(self._load(model,epoch))

    async def _load(self,model,epoch):
        worker=self.factory()
        try:
            reserve(worker)
            async with self.lock:
                if epoch!=self.epoch or self.closed:await close_worker(worker);return
                self.worker=worker;self.gpu=worker.gpu
            await asyncio.to_thread(worker.start)
            await asyncio.to_thread(worker.request,{'op':'load','model':model},90.)
            async with self.lock:
                if epoch!=self.epoch or self.closed:await close_worker(worker);return
                self.worker_loaded=True;self.phase='capturing' if self.capture is not None else 'waiting_reference'
                if self.capture is None:self.reason='Model ready. Say Hey Robbie and speak alone for four seconds, or use Learn my voice.'
                ready=self.reference is not None
                await self.notice(True)
            if ready:await self._enroll(epoch)
        except Exception as exc:
            await close_worker(worker)
            if epoch==self.epoch and not self.closed:
                self.worker=None;self.worker_loaded=False;self.phase='error'
                self.reason='CUDA filter unavailable ('+type(exc).__name__+'). Original microphone remains active; reselect to retry.'
                await self.notice(True)

    async def _enroll(self,epoch):
        async with self.lock:
            if epoch!=self.epoch or not self.worker_loaded or self.reference is None or self.phase in ('active','preparing_reference'):return
            worker=self.worker;reference=self.reference.copy();version=self.bank_version
            references=list(self.references.values()) or [reference]
            if len(references)>4:
                self.phase='capacity';self.reason='More than four registered voices: GPU filter bypassed, voice admission still applies. No known voice is silently discarded.'
                await self.notice(True);return
            self.phase='preparing_reference';self.reason='Preparing your voice reference; microphone remains unfiltered'
            await self.notice(True)
        try:
            await asyncio.to_thread(worker.request,{'op':'enroll','references':references},90.)
            async with self.lock:
                if epoch!=self.epoch or self.closed:return
                self.phase='active';self.reason='Keeping registered voices → VAD, ASR and interruption detection. New people can say Hey Robby.'
                await self.notice(True)
            if version!=self.bank_version:await self.refresh_bank()
        except Exception as exc:
            if epoch==self.epoch:
                await close_worker(worker);self.worker=None;self.worker_loaded=False;self.phase='error'
                self.reason='Voice reference failed ('+type(exc).__name__+'). Original microphone remains active.'
                await self.notice(True)

    def raw_audio(self,start,end,require_clean=True):
        pieces=[]
        for a,b,x,playback in self.ring:
            lo=max(0,round((start-a)*SR));hi=min(len(x),round((end-a)*SR))
            if hi>lo:
                if playback and require_clean:return None
                pieces.append(x[lo:hi])
        return np.concatenate(pieces) if pieces else None

    def duplicate(self,start,end,source):
        return any(('raw_isolation_wake' in (source,src)) and
            max(0,min(end,b)-max(start,a))>=.65*max(end-start,b-a) for a,b,src in self.seen)

    def output_ratio(self,start,end,raw):
        pieces=[]
        for a,b,x in self.output_ring:
            lo=max(0,round((start-a)*SR));hi=min(len(x),round((end-a)*SR))
            if hi>lo:pieces.append(x[lo:hi])
        if not pieces:return 0.
        y=np.concatenate(pieces)
        return float(np.sqrt(np.mean(y**2))/(np.sqrt(np.mean(raw**2))+1e-8))

    def match_known(self,embedding):
        s=getattr(self.c,'sentence_stream',None)
        if not s or embedding is None:return None
        self.sync_profiles()
        scores=sorted([(max((float(embedding@v) for v in u.get('vectors',[])),default=-1.),sid)
                       for sid,u in s.memory.users.items()],reverse=True)
        if not scores:return None
        best,sid=scores[0];rival=scores[1][0] if len(scores)>1 else -1.
        return sid if sid in self.authorized and best>=s.memory.threshold and best>=rival+.06 else None

    def sync_profiles(self):
        """Expired/deleted database identities must not survive in the filter."""
        s=getattr(self.c,'sentence_stream',None)
        if not s:return
        if hasattr(s.memory,'expire'):s.memory.expire()
        stale=self.authorized-set(s.memory.users)
        if not stale:return
        for sid in stale:
            self.authorized.discard(sid)
            for bank in (self.references,self.collected,self.names,self.collection_end):bank.pop(sid,None)
        self.reference=next(iter(self.references.values()),None)
        self.reference_name=', '.join(self.names.get(sid,sid) for sid in self.references) or None
        self.bank_version+=1
        if self.worker_loaded:self.task(self.refresh_bank())

    def admit(self,text,embedding):
        """Unknown leakage is not enrollment. Only a wake phrase or explicit invite opens it."""
        from speaker_turns import WAKE
        if self.selected=='off' or WAKE.match(text.lstrip()) or time.monotonic()<self.invite_until:return True
        return self.match_known(embedding) is not None

    def remember(self,context,start,end,text='',source='normal'):
        """Accumulate four seconds per matched person, never across speaker IDs."""
        self.seen.append((start,end,source))
        sid=context.get('speaker_id')
        if not context.get('enrolled') or sid in (None,'unknown') or context.get('identity_uncertain'):return
        s=getattr(self.c,'sentence_stream',None)
        if s:
            self.sync_profiles()
            # A recognized name alone is insufficient to learn an audio filter.
            if not s.memory.users.get(sid,{}).get('vectors'):return
        from speaker_turns import WAKE
        if WAKE.match(text.lstrip()) or time.monotonic()<self.invite_until:self.authorized.add(sid)
        if sid not in self.authorized:return
        self.names[sid]=context.get('display_name','Current speaker')
        if sid in self.references or self.capture is not None:return
        start=max(start,self.collection_end.get(sid,start))
        ref=self.raw_audio(start,end)
        if ref is None or len(ref)<10240 or float(np.sqrt(np.mean(ref**2)))<.003:return
        from speaker_teacher import enrollment_reference
        ref=enrollment_reference(ref,seconds=4)
        self.collection_end[sid]=end
        old=self.collected.get(sid,np.zeros(0,np.float32));self.collected[sid]=np.r_[old,ref][:64000]
        if len(self.collected[sid])<64000:
            self.reason='Collecting four seconds for '+self.names[sid]+'. Continue speaking after Hey Robby.'
            self.task(self.notice(True));return
        self.references[sid]=self.collected[sid].copy();self.bank_version+=1
        self.reference=next(iter(self.references.values()));self.reference_speaker=sid
        self.reference_name=', '.join(self.names[k] for k in self.references)
        self.task(self.refresh_bank())

    async def refresh_bank(self):
        async with self.lock:
            if not self.worker_loaded or self.phase=='preparing_reference':
                await self.notice(True);return
            await self._drain();self.phase='waiting_reference'
        await self._enroll(self.epoch)

    async def allow_new_voice(self):
        self.invite_until=time.monotonic()+30
        self.reason='The next speaker can join. Registered voice references are retained.'
        await self.notice(True)

    async def relearn(self,manual=False):
        async with self.lock:
            self.epoch+=1
            await self._drain()
            # Cancelled load/enrollment cannot leave a stale CUDA stream behind.
            if self.phase in ('loading','preparing_reference'):
                await close_worker(self.worker);self.worker=None;self.worker_loaded=False
            self.reference=None;self.reference_name=None;self.reference_speaker=None
            self.references.clear();self.collected.clear();self.authorized.clear();self.names.clear();self.seen.clear()
            self.collection_end.clear()
            self.bank_version+=1;self.invite_until=0.;self.wake_recovery.reset()
            self.capture=[] if manual else None;self.capture_size=0;self.capture_voiced=0
            self.phase='capturing' if manual else ('off' if self.selected=='off' else 'waiting_reference')
            self.reason='Speak alone for four seconds. Robby playback is excluded.' if manual else 'Voice reference cleared; original microphone is active'
            await self.notice(True)
            if self.selected!='off' and not self.worker_loaded:self.task(self._load(self.selected,self.epoch))

    async def receive(self,data):
        block=unpack(data)
        if block is None:return
        rid,at,x=block
        if not len(x):return
        # Bound memory and IPC even when a malformed client sends huge packets.
        if len(x)>SR:raise ValueError('Microphone packet exceeds one second')
        start=self.raw_samples/SR;self.raw_samples+=len(x);end=self.raw_samples/SR
        playback=at>=0
        self.ring.append((start,end,x.copy(),playback))
        while self.ring and self.ring[0][1]<end-30:self.ring.popleft()
        if getattr(self.c,'environment',None):self.c.environment.feed(x,end,playback=playback)
        await self.wake_recovery.feed(x,end,playback)
        async with self.lock:
            if self.capture is not None and not playback:
                n=min(len(x),4*SR-self.capture_size)
                self.capture.append(x[:n].copy());self.capture_size+=n
                if float(np.sqrt(np.mean(x[:n]**2)))>=.003:self.capture_voiced+=n
                if self.capture_size>=4*SR:
                    ref=np.concatenate(self.capture);self.capture=None
                    self.phase='off' if self.selected=='off' else ('waiting_reference' if self.worker_loaded else 'loading')
                    if self.capture_voiced>=2*SR:
                        self.reference=ref;self.reference_name='Manually selected voice';self.reference_speaker='manual'
                        self.reason='Voice reference captured in session RAM.'
                        if self.worker_loaded:self.task(self._enroll(self.epoch))
                    else:self.reason='Too little audible speech. Press Learn my voice and speak alone for four seconds.'
                await self.notice()
            if self.phase!='active':
                await self._emit([data]);return
            self.pending.append(data);self.partial=np.concatenate([self.partial,x]);packets=[]
            try:
                while len(self.partial)>=640:
                    chunk=self.partial[:640].copy();self.partial=self.partial[640:]
                    r=await asyncio.to_thread(self.worker.request,{'op':'push','audio':chunk},.25)
                    y=np.asarray(r['audio'],np.float32)
                    if not np.isfinite(y).all():raise ValueError('Invalid audio')
                    packets.extend(self.pending.take(y));self.compute_ms=r['compute_ms']
                    self.processed_chunks+=1;self.filtered_samples+=len(y)
            except Exception as exc:
                packets.extend(self.pending.take());self.partial=np.zeros(0,np.float32)
                self.phase='error';self.reason='Filtering stopped ('+type(exc).__name__+'); original microphone is active. Reselect to retry.'
                old,self.worker=self.worker,None;self.worker_loaded=False
                self.task(close_worker(old))
                await self.notice(True)
            await self._emit(packets);await self.notice()

    async def close(self):
        self.closed=True;self.epoch+=1
        self.wake_recovery.reset()
        await close_worker(self.worker);self.worker=None
        if self.tasks:await asyncio.gather(*list(self.tasks),return_exceptions=True)
        self.reference=None;self.ring.clear();self.capture=None;self.pending=TaggedAudio();self.partial=np.zeros(0,np.float32)
        self.references.clear();self.collected.clear();self.authorized.clear()
        self.output_ring.clear()
