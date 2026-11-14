"""Clock, reference and failure regressions. GPU tests are in test_input_isolation_cuda.py."""
import asyncio
from types import SimpleNamespace
import unittest
import numpy as np
from input_isolation import InputIsolation,TaggedAudio,HEADER,unpack

def packet(x,rid=0,at=-1):return HEADER.pack(rid,at)+np.asarray(x,dtype='<i2').tobytes()

class Conversation:
    def __init__(self):
        self.messages=[];self.packets=[];self.raw=[]
        async def send_json(m):self.messages.append(m)
        self.ws=SimpleNamespace(closed=False,send_json=send_json)
        self.environment=SimpleNamespace(feed=lambda x,t,playback:self.raw.append((x.copy(),t,playback)))
    async def _deliver_microphone(self,p):self.packets.append(p)

class Worker:
    gpu='test';lag=384
    def __init__(self):self.buffer=np.zeros(0,np.float32);self.fail=False;self.closed=False
    def start(self):pass
    def close(self):self.closed=True
    def request(self,m,timeout):
        if m['op']=='enroll':self.buffer=np.zeros(0,np.float32)
        if m['op']=='push':
            if self.fail:raise TimeoutError('test inference deadline')
            self.buffer=np.r_[self.buffer,m['audio']];y=self.buffer[:-self.lag].copy();self.buffer=self.buffer[-self.lag:]
            return {'audio':y,'compute_ms':4.}
        if m['op']=='flush':
            y=np.r_[self.buffer,m.get('audio',[])];self.buffer=np.zeros(0,np.float32);return {'audio':y}
        return {'ok':True}

async def until(predicate):
    for _ in range(200):
        if predicate():return
        await asyncio.sleep(.005)
    raise AssertionError('state transition timed out')

class ClockTests(unittest.TestCase):
    def test_partial_packets_keep_playback_positions(self):
        q=TaggedAudio();q.append(packet(np.arange(320),8,2400));q.append(packet(np.arange(320,640),8,2880))
        a=q.take(np.arange(256,dtype=np.float32)/32768);b=q.take()
        self.assertEqual([unpack(p)[:2] for p in a+b],[(8,2400),(8,2784),(8,2880)])
        np.testing.assert_array_equal(np.concatenate([unpack(p)[2] for p in a+b])*32768,np.arange(640))

class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.c=Conversation();self.f=InputIsolation(self.c,Worker)
    async def asyncTearDown(self):await self.f.close()
    async def activate(self):
        self.f.reference=np.full(64000,.05,np.float32)
        await self.f.configure('voxlock');await until(lambda:self.f.phase=='active')
    async def test_default_off_and_raw_environment(self):
        p=packet(np.arange(320));await self.f.receive(p)
        self.assertEqual(self.c.packets,[p]);self.assertIsNone(self.f.worker);self.assertEqual(len(self.c.raw),1)
    async def test_switch_off_flushes_remainder_without_clock_loss(self):
        await self.activate()
        x=np.arange(2301,dtype=np.int16)
        for i in range(0,len(x),237):await self.f.receive(packet(x[i:i+237],9,6000+round(i*1.5)))
        self.assertGreater(self.f.pending.size,0)
        await self.f.configure('off')
        y=np.concatenate([unpack(p)[2] for p in self.c.packets])*32768
        np.testing.assert_array_equal(y,x);self.assertEqual(self.f.pending.size,0)
        pos=0
        for p in self.c.packets:
            rid,at,a=unpack(p);self.assertEqual(rid,9);self.assertLessEqual(abs(at-(6000+round(pos*1.5))),1);pos+=len(a)
        self.assertEqual(sum(len(x[0]) for x in self.c.raw),len(y))
    async def test_failure_flushes_raw_and_keeps_microphone(self):
        await self.activate();x=np.arange(1600,dtype=np.int16)
        await self.f.receive(packet(x[:640]));self.f.worker.fail=True
        await self.f.receive(packet(x[640:1280]));await self.f.receive(packet(x[1280:]))
        np.testing.assert_array_equal(np.concatenate([unpack(p)[2] for p in self.c.packets])*32768,x)
        self.assertEqual(self.f.phase,'error')
    async def test_manual_reference_bypasses_filter_and_excludes_playback(self):
        await self.activate();await self.f.relearn(manual=True)
        await self.f.receive(packet(np.full(640,2000),4,0));self.assertEqual(self.f.capture_size,0)
        for _ in range(100):await self.f.receive(packet(np.full(640,2000)))
        await until(lambda:self.f.phase=='active')
        self.assertEqual(len(self.f.reference),64000)
    async def test_automatic_reference_requires_accepted_long_clean_turn(self):
        for _ in range(100):await self.f.receive(packet(np.full(640,2000)))
        self.f.remember({'speaker_id':'a','enrolled':False},0,4,'Hey Robby');self.assertIsNone(self.f.reference)
        self.f.remember({'speaker_id':'a','enrolled':True},0,1,'Hey Robby');self.assertIsNone(self.f.reference)
        self.f.remember({'speaker_id':'a','enrolled':True},0,4,'Hey Robby');self.assertEqual(len(self.f.reference),64000)
        await self.f.relearn()
        await self.f.receive(packet(np.full(640,2000),1,0))
        self.f.remember({'speaker_id':'a','enrolled':True},1,4.04,'Hey Robby');self.assertIsNone(self.f.reference)
    async def test_switch_during_loading_does_not_reactivate(self):
        await self.f.configure('voxlock');await self.f.configure('off');await asyncio.sleep(.02)
        self.assertEqual(self.f.phase,'off');self.assertIsNone(self.f.worker)

if __name__=='__main__':unittest.main()
