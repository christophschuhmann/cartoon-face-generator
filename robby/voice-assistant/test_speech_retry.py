"""Transport-level recovery tests; synthetic SSE is never used by the demo."""
import asyncio,json,unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from speech_retry import speech_events,SpeechGenerationError,recovery_prompt

class Client:
    def __init__(self,takes):self.takes=list(takes);self.bodies=[]
    async def get(self,*args,**kwargs):
        class State:
            status_code=200
            def json(self):return {'ready':True,'busy':False}
        return State()
    @asynccontextmanager
    async def stream(self,*args,**kwargs):
        self.bodies.append(kwargs['json']);take=self.takes.pop(0)
        class Response:
            status_code=200
            def raise_for_status(self):pass
            async def aiter_lines(self):
                for event in take:
                    if isinstance(event,Exception):raise event
                    yield 'data: '+json.dumps(event)
        yield Response()

BAD={'event':'error','code':'unverified_speech'}
PCM={'event':'audio_chunk','pcm_f32':'AAAAAA==','sample_rate':48000}
DONE={'event':'result','candidates':[],'live_only':True}

class Recovery(unittest.IsolatedAsyncioTestCase):
    async def test_unheard_sentence_retried_with_new_seed_then_succeeds(self):
        c=Client([[BAD],[PCM,DONE]])
        result=[e async for e in speech_events(c,{'seed':777},AsyncMock())]
        self.assertEqual([e['event'] for e in result],['speech_retry','audio_chunk','result'])
        self.assertNotEqual(c.bodies[0]['seed'],c.bodies[1]['seed'])
    async def test_no_retry_after_any_published_audio(self):
        c=Client([[PCM,BAD],[PCM,DONE]])
        with self.assertRaises(SpeechGenerationError):
            _=[e async for e in speech_events(c,{},AsyncMock())]
        self.assertEqual(len(c.bodies),1)
    async def test_missing_completion_after_audio_is_not_silent_success(self):
        c=Client([[PCM],[PCM,DONE]])
        with self.assertRaises(SpeechGenerationError) as caught:
            _=[e async for e in speech_events(c,{},AsyncMock())]
        self.assertEqual(caught.exception.code,'incomplete_stream')
        self.assertEqual(len(c.bodies),1)
    async def test_retries_bounded_and_final_failure_actionable(self):
        c=Client([[BAD]]*5)
        with self.assertRaises(SpeechGenerationError) as caught:
            _=[e async for e in speech_events(c,{},AsyncMock())]
        self.assertEqual(caught.exception.attempts,3)
        self.assertEqual(len(c.bodies),3)
    async def test_clean_empty_result_and_unheard_disconnect_retry(self):
        c=Client([[DONE],[PCM,DONE]])
        _=[e async for e in speech_events(c,{},AsyncMock())]
        self.assertEqual(len(c.bodies),2)
        c=Client([[ConnectionError('disconnected')],[PCM,DONE]])
        _=[e async for e in speech_events(c,{},AsyncMock())]
        self.assertEqual(len(c.bodies),2)

    async def test_disconnect_after_audio_is_never_automatically_replayed(self):
        c=Client([[PCM,ConnectionError('disconnected')],[PCM,DONE]])
        with self.assertRaises(SpeechGenerationError) as caught:
            _=[e async for e in speech_events(c,{},AsyncMock())]
        self.assertEqual(len(c.bodies),1)
        self.assertTrue(caught.exception.audio_published)

    async def test_verified_prefix_resumes_only_the_exact_suffix(self):
        partial={**DONE,'live_stream':{'enabled':True,'start_verified':True,'end_verified':False,
            'resume_safe':True,'remaining_text':'nicht öffnen.'}}
        c=Client([[PCM,partial],[PCM,DONE]])
        result=[e async for e in speech_events(c,{'message':'GENERAL: Clear.\nSCRIPT:\nBitte die Tür nicht öffnen.'},AsyncMock())]
        self.assertIn('nicht öffnen.',c.bodies[1]['message'])
        self.assertNotIn('Bitte die Tür',c.bodies[1]['message'])
        self.assertTrue(next(e for e in result if e['event']=='speech_retry')['continuation'])

    async def test_unpositioned_partial_result_is_not_reported_as_success(self):
        partial={**DONE,'live_stream':{'enabled':True,'start_verified':True,'end_verified':False}}
        c=Client([[PCM,partial]])
        with self.assertRaises(SpeechGenerationError) as caught:
            _=[e async for e in speech_events(c,{},AsyncMock())]
        self.assertEqual(caught.exception.code,'incomplete_verified_speech')
        self.assertEqual(len(c.bodies),1)

    async def test_last_unheard_retry_changes_to_candidate_search(self):
        c=Client([[BAD],[BAD],[PCM,DONE]])
        _=[e async for e in speech_events(c,{'model':'small_rl','align':True},AsyncMock())]
        self.assertEqual(c.bodies[2]['generation'],'search_asr')
        self.assertEqual(c.bodies[2]['search_n'],3)

    async def test_failed_audio_keeps_entire_long_reply_and_exact_retry_queue(self):
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        # More than the producer queue's capacity: must not cancel or deadlock
        # the LLM producer merely because the first sentence lost audio.
        sentences=[Sentence(f'Dies ist Testsatz Nummer {n}.',language='de') for n in range(7)]
        c=Client([[BAD]]*3)
        rows=[r async for r in pipeline(c,'Test.',{},[],preset=sentences)]
        replies=[v for k,v in rows if k=='sentence']
        self.assertEqual(len(replies),7)
        self.assertIn('Nummer 6',replies[-1]['text'])
        self.assertFalse(rows[-1][1]['speech_complete'])
        self.assertEqual(len(rows[-1][1]['_retry_sentences']),7)
        self.assertEqual(len(c.bodies),3)
    async def test_cancel_during_retry_does_not_start_another_take(self):
        c=Client([[BAD],[PCM,DONE]])
        async def run():
            async for event in speech_events(c,{},AsyncMock()):
                if event['event']=='speech_retry':asyncio.current_task().cancel()
        with self.assertRaises(asyncio.CancelledError):await asyncio.create_task(run())
        self.assertEqual(len(c.bodies),1)
    async def test_oom_has_only_one_retry(self):
        c=Client([[{'event':'error','code':'cuda_oom'}]]*3)
        with self.assertRaises(SpeechGenerationError):
            _=[e async for e in speech_events(c,{},AsyncMock())]
        self.assertEqual(len(c.bodies),2)
    async def test_candidate_search_oom_recovers_with_smaller_single_stream(self):
        c=Client([[{'event':'error','code':'cuda_oom'}],[PCM,DONE]])
        events=[e async for e in speech_events(c,{'generation':'search_asr','batch_size':3},AsyncMock())]
        self.assertEqual(c.bodies[1]['generation'],'single')
        self.assertEqual(c.bodies[1]['batch_size'],1)
        self.assertEqual(events[0]['strategy'],'single_stream_after_oom')
    async def test_later_sentence_retry_preserves_order_without_replaying_first(self):
        import base64,numpy as np
        from bolt_text import Sentence
        from bolt_pipeline import pipeline
        audio={**PCM,'channels':1,'pcm_f32':base64.b64encode(np.full(4800,.1,dtype='<f4').tobytes()).decode()}
        c=Client([[audio,DONE],[BAD],[audio,DONE]])
        result=[(k,v) async for k,v in pipeline(c,'Test.',{},[],preset=[
            Sentence('Erster vollständiger Satz.',language='de'),Sentence('Zweiter vollständiger Satz.',language='de')])]
        self.assertEqual(len([k for k,v in result if k=='sentence']),2)
        self.assertEqual(len(c.bodies),3)
        self.assertEqual(c.bodies[1]['message'].split('SCRIPT:')[1],c.bodies[2]['message'].split('SCRIPT:')[1])
        self.assertNotEqual(c.bodies[0]['message'],c.bodies[1]['message'])
        self.assertEqual(result[-1][0],'done')
        self.assertEqual(result[-1][1]['sentences'],2)
    async def test_malformed_unspoken_llm_completion_retries_once(self):
        from unittest.mock import patch
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        calls=[]
        async def director(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:raise ValueError('Unclosed acting cue')
            yield Sentence('Hier ist die vollständige Antwort.',language='de')
        with patch('bolt_pipeline.BoltDirector.stream',director):
            result=[(k,v) async for k,v in pipeline(None,'Erzähle etwas Nettes.',{},[],tts=False)]
        self.assertEqual(len(calls),2)
        self.assertEqual(len([k for k,v in result if k=='sentence']),1)
        self.assertEqual(result[-1][1]['unspoken_format_retries'],1)

    async def test_compact_fallback_preserves_words_and_internal_cues(self):
        body={'model':'small_rl','input_mode':'manual','format':'structured','language':'de',
              'message':'GENERAL: Long acting description.\nSCRIPT:\n(anger, intense) Nein! (pause) Nicht jetzt.'}
        c=Client([[BAD],[BAD],[PCM,DONE]])
        _=[e async for e in speech_events(c,body,AsyncMock())]
        self.assertEqual(c.bodies[0]['message'],body['message'])
        self.assertTrue(c.bodies[1]['message'].endswith('(anger, intense) Nein! (pause) Nicht jetzt.'))
        self.assertTrue(c.bodies[2]['message'].endswith('(natural, relaxed) Nein! (pause) Nicht jetzt.'))
        self.assertEqual(recovery_prompt({**body,'model':'large'},2),body['message'])

    async def test_provider_failure_only_retried_before_any_sentence(self):
        from unittest.mock import patch
        from bolt_pipeline import pipeline
        from bolt_director import ModelStreamError
        from bolt_text import Sentence
        for partial in (False,True):
            calls=[]
            async def director(*args,**kwargs):
                calls.append(1)
                if len(calls)==1:
                    if partial:yield Sentence('Bereits gesprochene Antwort.',language='de')
                    raise ModelStreamError({'code':503})
                yield Sentence('Vollständige Antwort.',language='de')
            with patch('bolt_pipeline.BoltDirector.stream',director):
                if partial:
                    with self.assertRaises(ModelStreamError):
                        _=[e async for e in pipeline(None,'Erzähle etwas Nettes.',{},[],tts=False)]
                    self.assertEqual(len(calls),1)
                else:
                    result=[e async for e in pipeline(None,'Erzähle etwas Nettes.',{},[],tts=False)]
                    self.assertEqual(len(calls),2)
                    self.assertEqual(result[-1][1]['unspoken_provider_retries'],1)

if __name__=='__main__':unittest.main()
