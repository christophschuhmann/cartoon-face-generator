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

    async def test_wake_preroll_and_go_asr_variations(self):
        b,c,s=self.make('Birdie. Hallo Robby. Go Murdy.');b.state='processing'
        await b.submit(np.ones(32000,np.float32))
        self.assertEqual(s.queue.get_nowait()[0],'Hallo Robby')

    async def test_go_maddie_is_accepted_after_local_keyword_detection(self):
        b,c,s=self.make('Guten Tag. Go Maddie.');b.state='processing'
        await b.submit(np.ones(32000,np.float32))
        self.assertEqual(s.queue.get_nowait()[0],'Guten Tag')

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
