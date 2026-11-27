import base64,io,json,unittest,wave
from unittest.mock import patch
import httpx
import numpy as np
import openai_gateway as gateway

class Events:
    def __init__(self,rows):self.rows=rows
    async def aiter_lines(self):
        for row in self.rows:yield 'data: '+json.dumps(row)

class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_authentication_and_model_metadata(self):
        with patch.object(gateway.TOKEN_FILE.__class__,'read_text',return_value='secret-test-token'):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway.app),base_url='http://test') as client:
                self.assertEqual((await client.get('/v1/models')).status_code,401)
                r=await client.get('/v1/models',headers={'Authorization':'Bearer secret-test-token'})
                self.assertEqual(r.status_code,200)
                self.assertEqual([x['id'] for x in r.json()['data']],[gateway.LLM_MODEL,gateway.TTS_MODEL])

    async def test_pcm_resampling_and_incomplete_stream(self):
        source=np.full(4800,.2,dtype='<f4').tobytes()
        audio={'event':'audio_chunk','sample_rate':48000,'channels':1,'pcm_f32':base64.b64encode(source).decode()}
        chunks=[chunk async for chunk in gateway.pcm_events(Events([audio,{'event':'result'}]))]
        self.assertGreater(len(chunks[0]),4000);self.assertLess(len(chunks[0]),5000)
        with self.assertRaises(RuntimeError):
            _=[chunk async for chunk in gateway.pcm_events(Events([audio]))]

    async def test_wav_has_real_length_and_speech_payload(self):
        pcm=b'\x00\x00'*2400
        data=await gateway.ffmpeg_encode(pcm,'wav')
        with wave.open(io.BytesIO(data)) as w:
            self.assertEqual((w.getframerate(),w.getnchannels(),w.getnframes()),(24000,1,2400))
        body=gateway.SpeechRequest(input='Hello',voice='mira')
        sent=gateway.backend_body(body,gateway.VOICES['mira'])
        self.assertEqual(sent['model'],'small_rl');self.assertTrue(sent['live_only'])
        self.assertIn('SCRIPT:\nHello',sent['message'])

if __name__=='__main__':unittest.main()
