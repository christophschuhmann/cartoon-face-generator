import asyncio,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
import numpy as np
from buddy_wake import BuddySession,choose

class BuddyTests(unittest.IsolatedAsyncioTestCase):
    def make(self,text):
        asr=SimpleNamespace(transcribe=AsyncMock(return_value={'text':text}))
        ss=SimpleNamespace(admission_epoch=0,effective_final_model=lambda:'parakeet_ultra',asr=asr,queue=asyncio.Queue())
        c=SimpleNamespace(sentence_stream=ss,input_samples=64000,speaking=False,ws=SimpleNamespace(closed=False,send_json=AsyncMock()))
        return BuddySession(c),c,ss

    async def test_go_submits_once_after_validated_command(self):
        b,c,s=self.make('Erzähl mir eine Geschichte. Go Buddy.');b.state='processing'
        await b.submit(np.ones(32000,np.float32)*.03)
        row=s.queue.get_nowait();self.assertEqual(row[0],'Erzähl mir eine Geschichte')
        self.assertTrue(row[5]['buddy_control']);self.assertEqual(b.state,'waiting')
        s.asr.transcribe.assert_awaited_once()

    async def test_go_bunny_is_not_submitted(self):
        b,c,s=self.make('Erzähl mir eine Geschichte. Go bunny.');b.state='processing';b.capture=[np.ones(32000)]
        await b.submit(np.ones(32000,np.float32))
        self.assertTrue(s.queue.empty());self.assertEqual(b.state,'recording');self.assertTrue(b.capture)

    async def test_browser_confirms_go_omitted_from_full_german_transcript(self):
        b,c,s=self.make('');b.browser_mode=True
        s.asr.transcribe.side_effect=[
            {'text':'Bitte drehen. Unklar.', 'timestamps':[{'word':'Bitte','start':.1},
                {'word':'drehen.','start':1.}, {'word':'Unklar.','start':3.2}]},
            {'text':'Go buddy.', 'timestamps':[{'word':'Go','start':1.3},{'word':'buddy.','start':1.7}]},
        ]
        await b.submit(np.ones(4*16000,np.float32))
        self.assertEqual(s.queue.get_nowait()[0],'Bitte drehen')
        self.assertEqual(len(s.asr.transcribe.call_args_list[1].args[1]),38400)

    async def test_browser_rejects_unconfirmed_tail_and_keeps_audio(self):
        b,c,s=self.make('');b.browser_mode=True;b.capture=[np.ones(64000,np.float32)]
        s.asr.transcribe.side_effect=[{'text':'Dreh dich.'},{'text':'Go bunny.',
            'timestamps':[{'word':'Go','start':1.},{'word':'bunny.','start':1.3}]}]
        await b.submit(b.capture[0])
        self.assertTrue(s.queue.empty());self.assertTrue(b.capture)

    async def test_stop_discards_recording(self):
        b,c,s=self.make('Ein Satz. Stop Buddy.');b.state='processing';b.capture=[np.ones(32000)]
        await b.submit(np.ones(32000,np.float32),action='stop')
        self.assertTrue(s.queue.empty());self.assertEqual(b.state,'waiting');self.assertFalse(b.capture)

    async def test_command_common_asr_spelling_body(self):
        b,c,s=self.make('Hallo. Go body.');b.state='processing'
        await b.submit(np.ones(32000,np.float32))
        self.assertEqual(s.queue.get_nowait()[0],'Hallo')

    async def test_stop_punctuation_before_birdie(self):
        b,c,s=self.make('Ein Satz. Stop, Birdie.');b.state='processing';b.capture=[np.ones(32000)]
        await b.submit(np.ones(32000,np.float32),action='stop')
        self.assertTrue(s.queue.empty());self.assertEqual(b.state,'waiting')

    async def test_browser_go_proposal_with_explicit_stop_discards_the_stunt(self):
        b,c,s=self.make('Mach bitte einen Salto. Stop, Murdy.');b.state='processing';b.browser_mode=True
        b.capture=[np.ones(64000,np.float32)]
        await b.submit(b.capture[0])
        self.assertTrue(s.queue.empty());self.assertFalse(b.capture);self.assertEqual(b.state,'waiting')
        self.assertIn('recording discarded',c.ws.send_json.await_args.args[0]['reason'])

    async def test_wake_preroll_and_go_asr_variations(self):
        b,c,s=self.make('Birdie. Hallo Robby. Go Murdy.');b.state='processing'
        await b.submit(np.ones(32000,np.float32))
        self.assertEqual(s.queue.get_nowait()[0],'Hallo Robby')

    async def test_go_maddie_is_accepted_after_local_keyword_detection(self):
        b,c,s=self.make('Guten Tag. Go Maddie.');b.state='processing'
        await b.submit(np.ones(32000,np.float32))
        self.assertEqual(s.queue.get_nowait()[0],'Guten Tag')

    async def test_german_stunt_with_transcribed_wake_word_and_repeated_submit(self):
        from avatar_commands import explicit_actions
        b,c,s=self.make('Hey Madi. Hey, Robbie, mach einen Salto. Gaumadi. Go, Madi.')
        await b.submit(np.ones(32000,np.float32))
        text=s.queue.get_nowait()[0]
        self.assertEqual(text,'Hey, Robbie, mach einen Salto')
        self.assertEqual([step['kind'] for step in explicit_actions(text)],['somersault'])

    async def test_go_maggie_is_accepted_after_local_keyword_detection(self):
        b,c,s=self.make('Guten Tag. Go Maggie.');b.state='processing'
        await b.submit(np.ones(32000,np.float32))
        self.assertEqual(s.queue.get_nowait()[0],'Guten Tag')

    async def test_browser_mode_buffers_without_running_wake_detector(self):
        b,c,s=self.make('Hallo. Go Buddy.')
        await b.browser_command('ready');await b.browser_command('begin')
        with patch('buddy_wake.detector',side_effect=AssertionError('must stay in browser')):
            await b.receive(np.ones(32000,np.float32))
        self.assertEqual(sum(map(len,b.capture)),32000)
        await b.browser_command('go')
        await asyncio.gather(*list(b.jobs))
        self.assertEqual(s.queue.get_nowait()[0],'Hallo')

    async def test_asr_failure_preserves_recording_for_retry(self):
        b,c,s=self.make('unused');b.state='processing';b.capture=[np.ones(32000)]
        s.asr.transcribe.side_effect=RuntimeError('temporary ASR outage')
        await b.submit(np.ones(32000,np.float32))
        self.assertTrue(s.queue.empty());self.assertEqual(b.state,'recording');self.assertTrue(b.capture)

    async def test_standby_audio_does_not_invoke_asr(self):
        b,c,s=self.make('unused')
        with patch('buddy_wake.detector',return_value=SimpleNamespace(predict_both=lambda x: ({},{}))):
            for _ in range(60):await b.receive(np.zeros(320,np.float32))
            if b.probe:await b.probe
        s.asr.transcribe.assert_not_awaited();self.assertEqual(b.state,'waiting')

    async def test_wake_keeps_audio_from_before_detection(self):
        b,c,s=self.make('unused')
        v3={'hey':.6,'go':.1,'stop':.1};v2={'hey':.8,'go':.2,'stop':.01}
        with patch('buddy_wake.detector',return_value=SimpleNamespace(predict_both=lambda x: (v3,v2))):
            await b.receive(np.ones(16000,np.float32));await b.probe
        self.assertEqual(b.state,'recording');self.assertGreaterEqual(sum(map(len,b.capture)),12000)

    def test_arbitration_requires_both_models_and_state(self):
        hey={'hey':.6,'go':.1,'stop':.1};v2={'hey':.8,'go':.2,'stop':.01}
        self.assertEqual(choose('waiting',hey,v2),'hey');self.assertIsNone(choose('recording',hey,v2))
        self.assertEqual(choose('recording',{'hey':.1,'go':.9,'stop':.2},{'hey':.1,'go':.95,'stop':.2}),'go')
        self.assertEqual(choose('recording',{'hey':.1,'go':.8,'stop':.9},{'hey':.1,'go':.7,'stop':.95}),'stop')

if __name__=='__main__':unittest.main()
