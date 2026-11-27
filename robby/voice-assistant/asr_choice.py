"""Per-session ASR selection and bounded pause-final transcription requests."""
import asyncio,re
import numpy as np
from asr_catalog import MODELS,worker_url

def overlapped_words(previous,current,offset_seconds):
    """Count duplicate words at a window seam; timed ASR must agree in time too."""
    norm=lambda word:re.sub(r'\W','',word).casefold()
    old=previous['text'].split()
    new=current['text'].split()
    before=previous.get('timestamps') or []
    after=current.get('timestamps') or []
    for n in range(min(12,len(old),len(new)),0,-1):
        ending=[norm(w) for w in old[-n:]]
        if ending!=[norm(w) for w in new[:n]]:continue
        if before and after:
            left,right=before[-n:],after[:n]
            if [norm(w['word']) for w in left]!=ending or [norm(w['word']) for w in right]!=ending:continue
            # The same phrase spoken
            # again after the boundary belongs in the transcript a second time.
            if any(min(a['end'],offset_seconds+b['end']) <= max(a['start'],offset_seconds+b['start'])
                   for a,b in zip(left,right)):continue
        return n
    return 0


class ASRChoice:
    def __init__(self,session):
        self.session=session;self.selected='nemotron';self.loading=None;self.switch_ms=None
        self.task=None;self.http=None
    def settings(self):
        return {'selected_model':self.selected,'loading_model':self.loading,'switch_ms':self.switch_ms,
            'models':[{'id':key,'label':s['label']} for key,s in MODELS.items()],
            'preview_model':'nemotron','final_model':self.selected,'reply_language':'de'}
    def client(self):
        if self.http is None:
            import httpx
            self.http=httpx.AsyncClient(base_url=worker_url(),timeout=60)
        return self.http
    async def close(self):
        if self.task:self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        if self.http:await self.http.aclose()
    async def select(self,key):
        if key not in MODELS:
            await self.session.c.ws.send_json({'type':'warning','text':'Unknown speech recognizer.'});return
        if self.task:self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.loading=key
        await self.session.c.ws.send_json(self.session.settings())
        async def load():
            try:
                if key=='nemotron':
                    # Original recognition must remain a recovery option even
                    # if the separate optional-model worker is unavailable.
                    self.session.epoch+=1;self.session.pause_checked=False
                    self.selected=key;self.switch_ms=0.;self.loading=None
                    await self.session.c.ws.send_json(self.session.settings())
                    try:await self.client().post('/activate/'+key,timeout=3)
                    except Exception:pass
                    return
                response=await self.client().post(worker_url(key)+'/activate/'+key);response.raise_for_status()
                # Invalidate any old finalization, retaining all audio and text.
                self.session.epoch+=1;self.session.pause_checked=False
                self.selected=key;self.switch_ms=response.json()['switch_ms']
            except asyncio.CancelledError:raise
            except Exception:
                await self.session.c.ws.send_json({'type':'warning','text':'Could not activate the selected recognizer. The previous model is still selected; check model readiness or try again.'})
            finally:
                self.loading=None
                if not self.session.closed:await self.session.c.ws.send_json(self.session.settings())
        self.task=asyncio.create_task(load())
    async def transcribe(self,key,audio):
        """At most 28 s per inference; short overlap protects boundary words.

        This is pause-final buffered recognition, not native Whisper streaming.
        No audio is written to disk or passed to the language model here.
        """
        if key not in MODELS or key=='nemotron':raise ValueError('Invalid alternative ASR')
        audio=np.asarray(audio,np.float32);parts=[];receipts=[]
        timed=key in ('parakeet_ultra','parakeet_redux')
        # Timed decoders can safely reconcile a larger overlap. Starting a
        # fresh multilingual decode on a cut syllable often changes the text.
        stride=(25 if timed else 27)*16000
        previous_start=0
        for start in range(0,len(audio),stride):
            window_start=start if timed else max(0,start-4000)
            end=start+27*16000
            chunk=audio[window_start:end]
            response=await self.client().post(worker_url(key)+'/transcribe/'+key,content=chunk.astype('<f4').tobytes(),headers={'Content-Type':'application/octet-stream'})
            response.raise_for_status();row=response.json();text=row['text'].strip();receipts.append(row)
            if len(receipts)>1:
                offset=(window_start-previous_start)/16000
                keep=overlapped_words(receipts[-2],row,offset)
                if keep:text=' '.join(text.split()[keep:])
            previous_start=window_start
            parts.append(text)
            if end>=len(audio):break
        return {'text':' '.join(filter(None,parts)),'model':key,'chunks':len(receipts),
            'transcribe_ms':round(sum(r['transcribe_ms'] for r in receipts),2)}
