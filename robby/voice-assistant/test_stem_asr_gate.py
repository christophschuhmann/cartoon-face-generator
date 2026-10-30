import unittest
from unittest.mock import AsyncMock,Mock
import numpy as np
from stem_lab import ASR_MIN_RMS,transcribe_speech

class StemAsrGate(unittest.IsolatedAsyncioTestCase):
    def client(self):
        client=Mock();state=Mock();state.json.return_value={'active_gpu_model':'parakeet_v3'}
        response=Mock();response.json.return_value={'model':'parakeet_v3','text':'Hello'}
        client.get=AsyncMock(return_value=state);client.post=AsyncMock(return_value=response)
        return client

    async def test_silence_and_low_artifacts_never_reach_asr(self):
        for value in (0.,0.001,0.009):
            client=self.client();result=await transcribe_speech(client,np.full(48000,value,np.float32))
            self.assertEqual(result['status'],'skipped');self.assertEqual(result['minimum_rms'],ASR_MIN_RMS)
            client.get.assert_not_awaited();client.post.assert_not_awaited()

    async def test_loud_speech_reaches_parakeet_v3(self):
        client=self.client();result=await transcribe_speech(client,np.full(48000,.03,np.float32))
        self.assertEqual(result['text'],'Hello');self.assertTrue(client.post.await_args.args[0].endswith('/transcribe/parakeet_v3'))

    async def test_inactive_model_does_not_get_switched(self):
        client=self.client();client.get.return_value.json.return_value={'active_gpu_model':'moonshine_de'}
        result=await transcribe_speech(client,np.full(48000,.03,np.float32))
        self.assertEqual(result['status'],'unavailable');client.post.assert_not_awaited()

if __name__=='__main__':unittest.main()
