import asyncio,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from avatar_actions import EMOTIONS
from avatar_commands import explicit_actions

class CommandTests(unittest.TestCase):
    def test_whole_body_spin_head_scope_and_flips(self):
        self.assertEqual(explicit_actions('Hey Robby, dreh dich mal im Kreis.')[0]['scope'],'body')
        self.assertEqual(explicit_actions('Dreh deinen Kopf gegen den Uhrzeigersinn.')[0]['scope'],'head')
        for text,direction in [('Mach mal einen Salto.','forward'),('Mach einen Salto rückwärts.','backward'),
                               ('Can you do a somersault?','forward'),('Do a backflip.','backward')]:
            action=explicit_actions(text)[0]
            self.assertEqual((action['kind'],action['direction']),('somersault',direction),text)
        self.assertEqual([s['kind'] for s in explicit_actions('Mach einen Salto und dreh dich dann im Kreis.')],['somersault','spin'])
        for text in ['Mach keinen Salto.','Erkläre mir einen Salto.','Sag "Mach einen Salto".',
                     'Wenn ich klatsche, mach einen Salto.','Alice macht einen Salto.']:
            self.assertEqual(explicit_actions(text),[],text)

    def test_token_split_stage_directions_cannot_become_speech(self):
        from bolt_text import SentenceFramer
        texts=[('(amusement) *Robby dreht sich kreisrund im Bildschirm!*',[]),
               ('(elation) *spins around* Schau mal, ich drehe eine Runde!',['Schau mal, ich drehe eine Runde!']),
               ('(amusement) **Hallo!**',['Hallo!']),('*Ich drehe eine Runde!*',['Ich drehe eine Runde!']),
               ('*Robby macht einen Salto!*',[]),('*does a flip*',[])]
        for text,expected in texts:
            for size in (1,2,7,999):
                f=SentenceFramer(strip_stage_directions=True);parts=[]
                for start in range(0,len(text),size):parts.extend(f.feed(text[start:start+size]))
                parts.extend(f.feed('',final=True))
                self.assertEqual([p.text for p in parts],expected,(size,text))
        self.assertEqual(SentenceFramer().feed('*Robby dreht sich um.*',final=True)[0].text,'*Robby dreht sich um.*')
    def test_common_german_english_commands_and_order(self):
        cases=[('Kannst du bitte eine lustige Grimasse schneiden?',['grimace']),
            ('Mach mal eine verrückte Grimasse!',['grimace']),('Make some funny faces.',['grimace']),
            ('Schiele bitte und rolle dann mit den Augen.',['grimace','eye_roll']),
            ('Guck bitte wütend und mach dann eine lustige Grimasse.',['emotion','grimace']),
            ('Schüttel bitte den Kopf und nicke danach.',['shake','nod']),
            ('Please wink.',['wink']),('Mach ein Fischgesicht.',['grimace'])]
        for text,kinds in cases:self.assertEqual([s['kind'] for s in explicit_actions(text)],kinds,text)
        self.assertEqual(explicit_actions(cases[3][0])[0]['variant'],'crossed')
        self.assertEqual(explicit_actions(cases[4][0])[0]['emotion'],'anger')
        self.assertEqual(explicit_actions(cases[-1][0])[0]['variant'],'fish')
        self.assertEqual(explicit_actions('Mach ein wütendes Gesicht.')[0]['emotion'],'anger')
        self.assertEqual(explicit_actions('Guck bitte lustig.')[0]['emotion'],'amusement')
        self.assertEqual(explicit_actions('Show me how you make a goofy face.')[0]['kind'],'grimace')
        for text in ['Mach eine Grimasse und sag etwas Lustiges.','Mach eine Grimasse und sag "Hallo".','Mach bitte grimmassen.','Sag etwas Lustiges und mach eine Grimasse.']:
            self.assertTrue(explicit_actions(text),text)
    def test_direct_emotional_requests_trigger_the_correct_face(self):
        for text in ('Sei mal sauer.', 'Kannst du bitte wütend sein?', 'Kannst du sauer sein?', 'Be angry.', 'Ich möchte, dass du sauer bist.', 'Tu so als wärst du wütend.', 'Show anger.'):
            actions=explicit_actions(text)
            self.assertEqual([(a['kind'],a['emotion']) for a in actions],[('emotion','anger')],text)
        self.assertEqual(explicit_actions('Sei mal traurig.')[0]['emotion'],'sadness')
        for text in ('Ich bin sauer.', 'Erkläre mir, warum du sauer bist.', 'Sei nicht sauer.', 'Sag "Sei sauer".'):
            self.assertEqual(explicit_actions(text),[],text)

    def test_noun_commands_and_all_german_emotion_names(self):
        from emotion_recipes import GERMAN
        for text in ('Mach eine Drehung.', 'Kannst du eine Drehung machen?', 'Führe eine Drehung durch.', 'Ich möchte, dass du eine Drehung machst.'):
            self.assertEqual(explicit_actions(text)[0]['kind'],'spin',text)
        self.assertEqual(explicit_actions('Führe eine Drehung gegen den Uhrzeigersinn durch.')[0]['direction'],'counterclockwise')
        for slug,names in GERMAN.items():
            text='Zeig mir '+names.split('|')[0]+'.'
            self.assertEqual(explicit_actions(text)[0]['emotion'],slug,text)
        for text in ('Erkläre eine Drehung.', 'Mach keine Drehung.', 'Ich habe eine Drehung gesehen.', 'Zeig mir eine traurige Geschichte.'):
            self.assertEqual(explicit_actions(text),[],text)

    def test_negation_quotes_explanations_conditions_and_descriptions_never_trigger(self):
        for text in ['Mach keine Grimasse.','Do not make a funny face.','Sag "Mach eine Grimasse".',
            'Wenn ich Banane sage, mach eine Grimasse.','Erkläre mir, wie man Grimassen schneidet.',
            'Alice looks angry.','Ich bin Nicky.','Mach ein Gedicht über einen traurigen Roboter.',
            'Bitte sag mach eine Grimasse.','Kannst du bitte sagen mach eine Grimasse?']:
            self.assertEqual(explicit_actions(text),[],text)
    def test_all_catalogue_emotions_and_bounded_varied_faces(self):
        for emotion in EMOTIONS:
            self.assertEqual(explicit_actions('Zeige den Gesichtsausdruck '+emotion)[0]['emotion'],emotion)
        a=explicit_actions('Mach Grimassen.',0);b=explicit_actions('Mach Grimassen.',1)
        self.assertEqual(len(a),2);self.assertNotEqual(a[0]['variant'],b[0]['variant'])
        self.assertLessEqual(len(explicit_actions('Mach Grimassen und Grimassen und Grimassen und Grimassen.')),6)

class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_provider_failure_does_not_make_a_valid_trick_silent(self):
        import httpx
        from bolt_pipeline import pipeline
        request=httpx.Request('POST','https://example.invalid')
        response=httpx.Response(503,request=request)
        async def unavailable(*args,**kwargs):
            raise httpx.HTTPStatusError('Model unavailable',request=request,response=response)
            yield
        with patch('bolt_pipeline.BoltDirector.stream',unavailable):
            events=[(k,v) async for k,v in pipeline(None,'Mach mal einen Salto.',{},[],tts=False)]
        self.assertEqual(sum(k=='avatar_action' for k,v in events),1)
        self.assertTrue(any(k=='sentence' for k,v in events))
        done=next(v for k,v in events if k=='done')
        self.assertEqual(done['visual_acknowledgment_http_status'],503)

    async def test_two_nonverbal_replies_have_a_bounded_ack_not_a_silent_error(self):
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        async def words(*args,**kwargs):yield Sentence('Haha!','amusement',language='de')
        with patch('bolt_pipeline.BoltDirector.stream',words):
            events=[(k,v) async for k,v in pipeline(None,'Mach mal einen Salto.',{},[],tts=False)]
        self.assertEqual(sum(k=='avatar_action' for k,v in events),1)
        self.assertTrue(next(v for k,v in events if k=='done')['visual_acknowledgment_fallback'])
        self.assertEqual([v['text'] for k,v in events if k=='sentence'],['Schau mal, jetzt kommt mein kleines Kunststück!'])

    async def test_pure_laughter_requests_real_words_without_replaying_action(self):
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        calls=[]
        async def words(*args,**kwargs):
            calls.append(True)
            yield Sentence('Haha!' if len(calls)==1 else 'Mein letzter Keks ist weg!','anger',language='de')
        with patch('bolt_pipeline.BoltDirector.stream',words):
            events=[(k,v) async for k,v in pipeline(None,'Sei mal wütend.',{},[],tts=False)]
        self.assertEqual(len(calls),2)
        self.assertEqual(sum(k=='avatar_action' for k,v in events),1)
        self.assertEqual([v['text'] for k,v in events if k=='sentence'],['Mein letzter Keks ist weg!'])

    async def test_tiny_emotion_fragment_does_not_block_the_following_sentence(self):
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        async def words(*args,**kwargs):
            yield Sentence('ACH!','anger',language='de')
            yield Sentence('Mein letzter Keks ist weg!','anger',language='de')
        with patch('bolt_pipeline.BoltDirector.stream',words):
            events=[(k,v) async for k,v in pipeline(None,'Sei mal wütend.',{},[],tts=False)]
        self.assertEqual([v['text'] for k,v in events if k=='sentence'],['Mein letzter Keks ist weg!'])

    async def test_animation_dispatched_before_even_starting_llm_and_survives_failure(self):
        from bolt_pipeline import pipeline
        async def fail(*args,**kwargs):
            raise RuntimeError('LLM unavailable')
            yield
        with patch('bolt_pipeline.BoltDirector.stream',fail):
            stream=pipeline(None,'Mach eine lustige Grimasse.',{},[],tts=False)
            kind,value=await anext(stream)
            self.assertEqual(kind,'avatar_action');self.assertEqual(value['steps'][0]['kind'],'grimace')
            with self.assertRaisesRegex(RuntimeError,'unavailable'):await anext(stream)
            await stream.aclose()
    async def test_direct_action_does_not_use_fragile_tool_json_and_still_produces_speech(self):
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        async def words(*args,**kwargs):yield Sentence('Schau mal, ein lustiges Fischgesicht!','amusement',language='de')
        with patch('bolt_pipeline.BoltDirector.stream',words),patch('conversation_director.CompactDirector.generate',side_effect=AssertionError('No JSON tool loop')):
            events=[(k,v) async for k,v in pipeline(None,'Mach eine Grimasse.',{},[],interaction_state={'rules':[]},tts=False)]
        self.assertEqual(events[0][0],'avatar_action')
        speech=next(v for k,v in events if k=='sentence')
        self.assertTrue(speech['text']);self.assertEqual(speech['avatar_action_id'],events[0][1]['action_id'])
    async def test_pure_spin_starts_immediately_and_is_not_replayed_by_metadata(self):
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        async def words(*args,**kwargs):yield Sentence('Hui, ich drehe mich!','elation',language='de')
        with patch('bolt_pipeline.BoltDirector.stream',words):
            events=[(k,v) async for k,v in pipeline(None,'Dreh dich bitte.',{},[],tts=False)]
        self.assertEqual(events[0][0],'avatar_action')
        speech=next(v for k,v in events if k=='sentence')
        self.assertEqual(speech['avatar_actions'][0]['kind'],'spin')
        self.assertEqual(speech['avatar_action_id'],events[0][1]['action_id'])
    async def test_empty_or_malformed_visual_speech_has_one_llm_retry(self):
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        for malformed in [False,True]:
            calls=[]
            async def words(*args,**kwargs):
                calls.append(args)
                if len(calls)==1:
                    if malformed:raise ValueError('Invalid acting cue')
                    return
                yield Sentence('Jetzt kommt mein lustiges Fischgesicht!','amusement',language='de')
            with patch('bolt_pipeline.BoltDirector.stream',words):
                events=[(k,v) async for k,v in pipeline(None,'Mach eine Grimasse.',{},[],tts=False)]
            self.assertEqual(len(calls),2);self.assertEqual(sum(k=='avatar_action' for k,v in events),1)
            self.assertTrue(any(k=='sentence' for k,v in events))
    async def test_requested_emotion_is_shared_with_tts_even_if_model_cue_is_neutral(self):
        from bolt_pipeline import pipeline
        from bolt_text import Sentence
        async def words(*args,**kwargs):yield Sentence('Mein letzter Keks ist weg!','contentment, soft',language='de')
        with patch('bolt_pipeline.BoltDirector.stream',words):
            events=[(k,v) async for k,v in pipeline(None,'Zeig mir Wut.',{},[],tts=False)]
        self.assertEqual(events[0][1]['steps'][0]['emotion'],'anger')
        part=next(v for k,v in events if k=='sentence')
        self.assertEqual(part['template_id'],'anger.intense')
        self.assertEqual(part['performance']['sentences'][0]['emotion'],'anger')
        self.assertIn('(anger, intense, natural)',part['script'])

    async def test_explicitly_silent_request_needs_neither_llm_nor_tts(self):
        from bolt_pipeline import pipeline
        with patch('bolt_pipeline.BoltDirector.stream',side_effect=AssertionError('Silent action')):
            events=[(k,v) async for k,v in pipeline(None,'Mach eine Grimasse ohne etwas zu sagen.',{},[])]
        self.assertEqual([k for k,v in events],['avatar_action','done']);self.assertTrue(events[-1][1]['silent'])

if __name__=='__main__':unittest.main()
