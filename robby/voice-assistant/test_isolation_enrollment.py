import asyncio
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock,Mock
import unittest
import numpy as np
from input_isolation import InputIsolation
from input_isolation_union import SpectralUnion
from test_input_isolation import Conversation,Worker,packet,until

class Enrollment(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.c=Conversation();self.f=InputIsolation(self.c,Worker)
    async def asyncTearDown(self):await self.f.close()
    async def feed(self,seconds):
        for _ in range(round(seconds*25)):await self.f.receive(packet(np.full(640,2000)))
    def remember(self,sid,a,b,text):
        self.f.remember({'speaker_id':sid,'display_name':sid,'enrolled':True},a,b,text)
    async def test_short_wake_accumulates_only_same_voice_and_nonoverlapping_audio(self):
        await self.feed(8)
        self.remember('A',0,2,'Hey Robbie');self.remember('B',2,4,'Hallo Robby')
        self.assertFalse(self.f.references)
        self.remember('A',0,2,'Hey Robbie');self.assertEqual(len(self.f.collected['A']),32000)
        self.remember('A',4,6,'Ich bin noch da');self.assertEqual(list(self.f.references),['A'])
        self.remember('B',6,8,'Auch noch da');self.assertEqual(set(self.f.references),{'A','B'})
        original=self.f.references['A'].copy();self.remember('A',0,4,'Hey Robbie')
        np.testing.assert_array_equal(self.f.references['A'],original)
    async def test_non_wake_does_not_create_filter_identity(self):
        await self.feed(4);self.remember('TV',0,4,'Heute ist das Wetter schön')
        self.assertFalse(self.f.authorized);self.assertIsNone(self.f.reference)
    async def test_unknown_leak_rejected_known_people_and_wake_accepted(self):
        self.f.selected='voxlock';self.f.authorized={'A','B'};v=np.eye(3,dtype=np.float32)
        self.c.sentence_stream=SimpleNamespace(memory=SimpleNamespace(users={x:{'vectors':[v[k]]} for k,x in enumerate(['A','B','TV'])},threshold=.32))
        for x in v[:2]:self.assertTrue(self.f.admit('Guten Tag',x))
        self.assertFalse(self.f.admit('Werbung im Fernsehen',v[2]))
        self.assertTrue(self.f.admit('Hi Robby, ich bin neu',v[2]))
        self.assertFalse(self.f.admit('Er sagte Hey Robby',v[2]))
        self.assertFalse(self.f.admit('Guten Tag',np.ones(3)/np.sqrt(3)))
    async def test_adding_person_updates_active_worker_without_forgetting_first(self):
        await self.feed(8);self.remember('A',0,4,'Hey Robbie');await self.f.configure('voxlock')
        await until(lambda:self.f.phase=='active')
        self.remember('B',4,8,'Hey Robbie');await asyncio.sleep(.04)
        self.assertEqual(set(self.f.references),{'A','B'});self.assertEqual(self.f.phase,'active')
        await self.f.allow_new_voice();self.assertEqual(set(self.f.references),{'A','B'})
        await self.f.relearn();self.assertFalse(self.f.references)
    async def test_recovery_dedup_only_between_raw_and_main_paths(self):
        self.f.seen.append((0,4,'normal'))
        self.assertTrue(self.f.duplicate(.1,4.1,'raw_isolation_wake'))
        self.assertFalse(self.f.duplicate(5,8,'raw_isolation_wake'))
        self.assertFalse(self.f.duplicate(0,4,'normal'))
    async def test_raw_wake_is_queued_unknown_background_is_not(self):
        self.f.selected='voxlock';v=np.eye(3,dtype=np.float32)
        self.c.sentence_stream=SimpleNamespace(memory=SimpleNamespace(users={},threshold=.32),admission_epoch=0,pause_ms=300,
            asr=SimpleNamespace(selected='parakeet_v3',transcribe=AsyncMock(return_value={'text':'Hey Robby ich bin Bob','model':'parakeet_v3'})),queue=asyncio.Queue())
        with patch('speaker_teacher.get_cached_teacher',return_value=SimpleNamespace(embed=lambda a:v[0])):
            await self.f.wake_recovery.check(0,4,np.full(64000,.04,np.float32),0)
            self.assertEqual(self.c.sentence_stream.queue.qsize(),1)
            self.c.sentence_stream.asr.transcribe.return_value={'text':'Werbung im Fernsehen','model':'parakeet_v3'}
            await self.f.wake_recovery.check(5,9,np.full(64000,.04,np.float32),0)
            self.assertEqual(self.c.sentence_stream.queue.qsize(),1)

    async def test_expired_voice_is_removed_and_name_alone_is_not_a_reference(self):
        await self.feed(4);self.remember('A',0,4,'Hey Robby')
        self.c.sentence_stream=SimpleNamespace(memory=SimpleNamespace(users={},threshold=.32))
        self.f.sync_profiles();self.assertFalse(self.f.references);self.assertFalse(self.f.authorized)
        self.c.sentence_stream.memory.users['B']={'vectors':[]}
        self.remember('B',0,4,'Hey Robby ich bin Bob');self.assertFalse(self.f.authorized)

    async def test_known_second_speaker_does_not_inherit_wake_owner_name(self):
        from test_sentence_reliability import ReliabilityTests
        s,c,v=ReliabilityTests().session();c.input_isolation=InputIsolation(c,Worker)
        c.input_isolation.selected='voxlock';c.input_isolation.authorized={'speaker-1','speaker-2'}
        s.memory.assign(v[1],'Ich bin Selma.');s.wake.configure(True);s.wake.accept('speaker-1',v[0])
        done=asyncio.create_task(asyncio.sleep(0));await done
        await s.queue.put(('Was können wir zusammen machen?',np.full(48000,.04,np.float32),3.,0.,{'task':done,'embedding':v[1],'compute_ms':0.}))
        runner=asyncio.create_task(s.deliver())
        try:
            await until(lambda:c._send_turn.await_count>0)
            self.assertEqual(c.current_speaker['display_name'],'Selma')
            self.assertEqual(c.current_speaker['speaker_id'],'speaker-2')
        finally:
            runner.cancel();await runner;await c.input_isolation.close()

    async def test_filtered_voice_cannot_certify_unknown_raw_speaker(self):
        from test_sentence_reliability import ReliabilityTests
        s,c,v=ReliabilityTests().session();f=c.input_isolation=InputIsolation(c,Worker)
        f.selected='voxlock';f.authorized={'speaker-1'}
        f.raw_audio=lambda a,b,**kw:np.full(48000,.02,np.float32)
        done=asyncio.create_task(asyncio.sleep(0));await done
        cached={'task':done,'embedding':v[0],'compute_ms':0.}
        await s.queue.put(('Heute ist das Wetter schön.',np.full(48000,.04,np.float32),3.,0.,cached,{'input_start_s':0.,'input_end_s':3.}))
        with patch('speaker_teacher.get_cached_teacher',return_value=SimpleNamespace(embed=lambda x:v[2])):
            runner=asyncio.create_task(s.deliver())
            try:
                await until(lambda:any(c.args[0].get('source')=='input_isolation' for c in c.ws.send_json.await_args_list))
                c._send_turn.assert_not_awaited();self.assertEqual(len(s.memory.users),1)
            finally:runner.cancel();await runner;await f.close()

    async def test_exact_original_prefetch_reused_but_changed_audio_rejected(self):
        from test_sentence_reliability import ReliabilityTests
        from speaker_teacher import reference_key,enrollment_reference
        for changed in (False,True):
            s,c,v=ReliabilityTests().session();f=c.input_isolation=InputIsolation(c,Worker)
            f.selected='voxlock';f.authorized={'speaker-1'}
            raw=np.full(48000,.02,np.float32)
            f.raw_audio=lambda a,b,**kw:raw.copy()*(2 if changed else 1)
            done=asyncio.create_task(asyncio.sleep(0));await done
            cached={'task':done,'embedding':v[0],'compute_ms':1.,'raw_key':reference_key(enrollment_reference(raw))}
            await s.queue.put(('Kannst du mir etwas erzählen?',np.full(48000,.04,np.float32),3.,0.,cached,{'input_start_s':0.,'input_end_s':3.}))
            with patch('speaker_teacher.get_cached_teacher',return_value=SimpleNamespace(embed=lambda x:v[2])) as teacher:
                runner=asyncio.create_task(s.deliver())
                try:
                    await until(lambda:c._send_turn.await_count>0 or any(x.args[0].get('source')=='input_isolation' for x in c.ws.send_json.await_args_list))
                    self.assertEqual(c._send_turn.await_count,0 if changed else 1)
                    self.assertEqual(teacher.call_count,1 if changed else 0)
                finally:runner.cancel();await runner;await f.close()

class FinalAsrTests(unittest.TestCase):
    def test_short_rejected_continuation_uses_real_longer_context(self):
        from test_sentence_reliability import ReliabilityTests
        s,c,v=ReliabilityTests().session()
        s.rejected_identity_span=(0.,5.,s.admission_epoch)
        s.identity_audio=Mock(side_effect=lambda a,b:np.full(round((b-a)*16000),.02,np.float32))
        meta={'input_start_s':5.2,'input_end_s':6.6}
        short=np.ones(22400,np.float32)
        result=s.identity_continuation('Und die Nachrichten.',meta,short)
        self.assertEqual(len(result),64000);self.assertEqual(meta['speaker_context_seconds'],4.)
        self.assertEqual(s.identity_audio.call_count,1)

    def test_rejected_context_never_carries_across_wake_gap_or_reset(self):
        from test_sentence_reliability import ReliabilityTests
        s,c,v=ReliabilityTests().session();short=np.ones(22400,np.float32)
        s.rejected_identity_span=(0.,5.,s.admission_epoch)
        s.identity_audio=Mock(side_effect=AssertionError('must not consult earlier speech'))
        for text,start,end in [('Hey Robby ich bin Bob',5.2,6.6),('Hallo',7.,8.),('Langer neuer Satz',5.2,8.)]:
            self.assertIs(s.identity_continuation(text,{'input_start_s':start,'input_end_s':end},short),short)
        s.admission_epoch+=1
        self.assertIs(s.identity_continuation('Hallo',{'input_start_s':5.2,'input_end_s':6.6},short),short)

    def test_external_final_does_not_block_hop_native_path_is_unchanged(self):
        from feature_tap import external_final_results
        class Session:pass
        external=Session();external.robo_external_final=True;native=Session()
        e={'kind':'ENDPOINT','seg_texts':['partial']};n={'kind':'ENDPOINT'}
        wave=np.ones(100);result={external:([e],[(e,wave)]),native:([n],[(n,wave)])}
        external_final_results(result)
        self.assertEqual(result[external][1],[]);self.assertEqual(e['transcript'],'')
        self.assertEqual(len(result[native][1]),1);self.assertNotIn('transcript',n)

class UnionTests(unittest.TestCase):
    def test_duplicate_estimates_do_not_amplify_and_flush_exactly(self):
        x=np.random.default_rng(3).normal(0,.05,16013).astype(np.float32);u=SpectralUnion(2);ys=[]
        for at in range(0,len(x),640):
            a=x[at:at+640];ys.append(u.push(a,np.stack([a,a])))
        ys.append(u.flush());y=np.concatenate(ys)
        self.assertEqual(len(y),len(x));np.testing.assert_allclose(y,x,atol=1e-6)
    def test_two_rejected_tracks_produce_no_unknown_audio(self):
        x=np.full(1403,.2,np.float32);u=SpectralUnion(2)
        y=np.r_[u.push(x,np.zeros((2,len(x)))),u.flush()]
        self.assertEqual(len(y),len(x));self.assertLess(np.max(np.abs(y)),1e-8)

if __name__=='__main__':unittest.main()
