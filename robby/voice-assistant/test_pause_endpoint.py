import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock
import numpy as np
from pause_vad import SpeechClock
from sentence_session import SentenceSession

class Probabilities:
    def __init__(self,values):self.values=iter(values)
    def run(self,_,inputs):return np.array([[next(self.values)]],np.float32),inputs['state']

class SpeechClockTests(unittest.TestCase):
    def test_no_energy_gate_and_temporal_onset(self):
        # Loud sustained noise is deliberately assigned non-speech by the
        # neural model. One isolated high score is not a speech onset.
        clock=SpeechClock(Probabilities([.01,.02,.8,.02,.9,.9,.4,.1]))
        clock.feed(np.ones(8*512,np.float32)*.5,.256)
        self.assertAlmostEqual(clock.last_speech,.224)
        self.assertFalse(clock.active)
    def test_packet_fragmentation_preserves_32ms_timestamps(self):
        clock=SpeechClock(Probabilities([.9]*5))
        for index in range(8):clock.feed(np.ones(320,np.float32)*.02,(index+1)*.02)
        self.assertEqual(clock.calls,5);self.assertAlmostEqual(clock.last_speech,.16)

@asynccontextmanager
async def slot(_):yield

class PauseSubmissionTests(unittest.IsolatedAsyncioTestCase):
    def session(self):
        c=SimpleNamespace(ws=SimpleNamespace(send_json=AsyncMock()),speaking=False,halting=False,
            session=SimpleNamespace(reset=Mock()),ears=SimpleNamespace(sr=16000),_on_barge=AsyncMock())
        s=SentenceSession(c);s.wake.configure(False);s.set_pause(400);s.begin=0.;s.last_speech=1.;s.mic_now=1.2;s.now=1.2
        s.records.append((0.,2.,np.zeros(32000,np.float32)))
        return s
    async def test_punctuation_and_native_endpoint_do_not_submit_while_speaking(self):
        s=self.session()
        await s.preview_text('That is one sentence. Here is another.',1.2,final=True)
        await s.native_endpoint('That is one sentence. Here is another.',1.2)
        self.assertTrue(s.queue.empty());self.assertIn('another',s.preview)
        s.c.session.reset.assert_not_called()
    async def test_pause_sends_all_sentences_once_in_one_turn(self):
        s=self.session();s.mic_now=1.4
        await s.native_endpoint('That is one sentence.',1.)
        await s.preview_text('Here is another.',1.2)
        text=s.native_text();epoch=s.epoch
        self.assertTrue(await s.commit_pause(text,1.4,epoch,1.))
        self.assertEqual(s.queue.get_nowait()[0],'That is one sentence. Here is another.')
        self.assertFalse(await s.commit_pause(text,1.4,epoch,1.))
    async def test_settings_are_bounded_and_apply_to_current_pause(self):
        s=self.session();s.mic_now=1.6;s.set_pause(900)
        self.assertFalse(await s.commit_pause('Bye bye.',1.6,s.epoch,1.))
        s.set_pause(300);self.assertTrue(await s.commit_pause('Bitte sage mir jetzt auf Wiedersehen.',1.6,s.epoch,1.))
        for value in [float('nan'),float('inf'),199,2001]:
            with self.assertRaises(ValueError):s.set_pause(value)
    async def test_speech_resuming_during_asr_probe_invalidates_flush(self):
        s=self.session();s.mic_now=s.now=1.5
        entered=asyncio.Event();release=__import__('threading').Event()
        loop=asyncio.get_running_loop()
        def transcribe(audio):
            loop.call_soon_threadsafe(entered.set);release.wait(2)
            return ['First sentence. Second sentence.']
        s.c.speaker_ext=SimpleNamespace(asr_slot=slot)
        s.c.ears.service=SimpleNamespace(engine=SimpleNamespace(asr=SimpleNamespace(transcribe=transcribe)))
        s._maybe_probe();await asyncio.wait_for(entered.wait(),2)
        s.last_speech=1.5;s.mic_now=1.6;release.set();await s.probe
        self.assertTrue(s.queue.empty())
    async def test_incipient_speech_also_blocks_a_pending_pause(self):
        s=self.session();s.mic_now=2.
        s.vad=SimpleNamespace(active=False,probability=.48)
        self.assertFalse(await s.commit_pause('This is not finished.',2.,s.epoch,1.))
    async def test_quieter_voice_and_stale_asr_cannot_override_live_speech(self):
        s=self.session();s.focus.owner='known';s.preview='Ich bin noch mitten im Satz'
        s.mic_now=s.last_speech=s.now=5.;s.foreground_last=2.;s.foreground_now=False;s.word_at=2.
        s.vad=SimpleNamespace(active=True,probability=.95)
        self.assertFalse(s.quiet_ready())
        self.assertFalse(await s.commit_pause(s.preview,5.,s.epoch,5.))
        self.assertEqual(s.final_audio_end(5.),5.)
    async def test_resumed_then_paused_again_invalidates_old_transcript(self):
        s=self.session();s.focus.owner='known';s.preview='Erster Teil'
        s.last_speech=2.;s.mic_now=s.now=3.;s.word_at=0.
        s.foreground_last=.5;s.foreground_now=False
        s.vad=SimpleNamespace(active=False,probability=.01)
        self.assertFalse(await s.commit_pause(s.preview,1.5,s.epoch,1.))
    async def test_gpu_hop_backlog_cannot_submit_incomplete_audio(self):
        s=self.session();s.focus.owner='known';s.mic_now=4.;s.now=1.;s.last_speech=3.
        s.vad=SimpleNamespace(active=False,probability=.01)
        self.assertFalse(await s.commit_pause('Noch nicht vollständig.',1.,s.epoch,3.))
        s._maybe_probe();self.assertIsNone(s.probe)

    async def test_complete_mic_pcm_bypasses_preview_backlog_without_losing_tail(self):
        from unittest.mock import patch
        s=self.session();s.focus.owner='known';s.mic_now=4.;s.now=1.;s.last_speech=3.;s.begin=0.
        s.vad=SimpleNamespace(active=False,probability=.01);s.mic_driven=True
        x=np.r_[np.ones(16000)*.01,np.ones(16000)*.02,np.ones(16000)*.03,np.zeros(16000)].astype(np.float32)
        s.mic_records.append((0.,4.,x))
        async def transcribe(key,audio):
            self.assertEqual(len(audio),round(3.12*16000))
            self.assertAlmostEqual(float(audio[40000]),.03,places=5)
            return {'text':'Der ganze Satz mit letztem Wort.','model':key,'transcribe_ms':1.}
        s.asr.selected='parakeet_ultra';s.asr.transcribe=transcribe
        with patch('speaker_teacher.get_cached_teacher',return_value=SimpleNamespace(embed=lambda a:np.eye(192)[0])):
            s._maybe_probe();await s.probe
        self.assertEqual(s.queue.get_nowait()[0],'Der ganze Satz mit letztem Wort.')
        self.assertEqual(s.segment_floor,4.)
        await s.native_endpoint('Veraltete Wörter.',1.2)
        self.assertEqual(s.native_text(),'')
        await s.close()

    async def test_new_speech_invalidates_fast_mic_transcript(self):
        s=self.session();s.focus.owner='known';s.mic_now=4.;s.now=1.;s.last_speech=3.;s.begin=0.
        s.vad=SimpleNamespace(active=False,probability=.01)
        s.mic_records.append((0.,4.,np.zeros(64000,np.float32)))
        entered=asyncio.Event();release=asyncio.Event()
        async def transcribe(*args):
            entered.set();await release.wait()
            return {'text':'Noch nicht der ganze Satz.','model':'parakeet_ultra'}
        s.asr.selected='parakeet_ultra';s.asr.transcribe=transcribe
        s._maybe_probe();await entered.wait()
        s.last_speech=s.mic_now=4.1;s.vad.active=True
        release.set();await s.probe
        self.assertTrue(s.queue.empty());await s.close()
    async def test_new_turn_preroll_never_reuses_previous_submitted_words(self):
        s=self.session();s.now=1.4;s.reset_segment()
        s.vad=SpeechClock(Probabilities([.9,.9]))
        await s._speech_audio(np.zeros(1024,np.float32),1.8)
        self.assertEqual(s.begin,1.4)
    async def test_stop_remains_immediate_while_reply_is_playing(self):
        s=self.session();s.c.speaking=True
        s.verify_barge=AsyncMock(return_value={'accepted':True})
        await s.preview_text('Stopp!',1.2)
        await s.barge_task
        s.c._on_barge.assert_awaited_once();self.assertTrue(s.queue.empty())

if __name__=='__main__':unittest.main()

class EarlyFinalAsrTests(unittest.IsolatedAsyncioTestCase):
    def session(self):
        c=SimpleNamespace(ws=SimpleNamespace(send_json=AsyncMock()),speaking=False,halting=False,
            session=SimpleNamespace(reset=Mock()),ears=SimpleNamespace(sr=16000),_on_barge=AsyncMock())
        s=SentenceSession(c);s.wake.configure(False);s.set_pause(300);s.begin=0.;s.last_speech=1.;s.mic_now=s.now=1.15
        s.records.append((0.,2.,np.zeros(32000,np.float32)))
        s.vad=SimpleNamespace(active=False,probability=.01)
        s.asr=SimpleNamespace(selected='parakeet_v3',transcribe=AsyncMock(return_value={'text':'Hallo Robby.','model':'parakeet_v3'}))
        return s
    async def test_early_transcript_is_kept_while_no_new_speech(self):
        s=self.session();s._maybe_early_final(1.15);await s.early_task
        self.assertEqual(s.early_final['key'],s.early_key())
        s.asr.transcribe.assert_awaited_once()
        s._maybe_early_final(1.2);self.assertEqual(s.asr.transcribe.await_count,1)
    async def test_new_speech_invalidates_the_early_transcript(self):
        s=self.session();s._maybe_early_final(1.15);await s.early_task
        s.last_speech=1.18
        self.assertNotEqual(s.early_final['key'],s.early_key())
    async def test_disabled_or_native_asr_never_runs_early(self):
        s=self.session();s.early_final_ms=0;s._maybe_early_final(1.15);self.assertIsNone(s.early_task)
        s=self.session();s.asr.selected='nemotron';s._maybe_early_final(1.15);self.assertIsNone(s.early_task)
        s=self.session();s.mic_now=1.05;s._maybe_early_final(1.05);self.assertIsNone(s.early_task)
