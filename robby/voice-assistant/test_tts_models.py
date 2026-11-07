"""Switch isolation: reject overlap, keep the old choice on failure, unblock turns."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp import web
import tts_models


class SwitchTests(unittest.IsolatedAsyncioTestCase):
    def request(self,model='large17',active=0):
        bridge=SimpleNamespace(tts_model='small_rl',tts_loading=None,tts_error=None,
            tts_ready=asyncio.Event(),active=active,base='http://127.0.0.1:8792')
        bridge.tts_ready.set()
        async def body():return {'model':model}
        return SimpleNamespace(app={'bridge':bridge,'tasks':[]},json=body),bridge

    async def test_reject_during_reply_without_touching_state(self):
        request,bridge=self.request(active=1)
        with self.assertRaises(web.HTTPConflict):await tts_models.select(request)
        self.assertTrue(bridge.tts_ready.is_set());self.assertEqual(bridge.tts_model,'small_rl')

    async def test_unknown_model_is_not_forwarded(self):
        request,bridge=self.request(model='arbitrary-remote-code')
        with self.assertRaises(web.HTTPBadRequest):await tts_models.select(request)
        self.assertFalse(request.app['tasks'])

    async def exercise(self,fail):
        request,bridge=self.request();gate=asyncio.Event()
        class Client:
            def __init__(self,**kwargs):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def post(self,path,json):
                assert path=='/api/models/select' and json=={'model':'large17'}
                await gate.wait()
                if fail:raise RuntimeError('synthetic OOM')
                return SimpleNamespace(raise_for_status=lambda:None)
        with patch.object(tts_models.httpx,'AsyncClient',Client):
            result=await tts_models.select(request)
            self.assertEqual(result.status,202);self.assertFalse(bridge.tts_ready.is_set())
            with self.assertRaises(web.HTTPConflict):await tts_models.select(request)
            gate.set();await asyncio.gather(*request.app['tasks'])
        self.assertTrue(bridge.tts_ready.is_set());self.assertIsNone(bridge.tts_loading)
        self.assertEqual(bridge.tts_model,'small_rl' if fail else 'large17')
        self.assertEqual(bool(bridge.tts_error),fail)

    async def test_success_selects_only_after_gpu_is_ready(self):await self.exercise(False)
    async def test_failure_keeps_previous_choice_and_unblocks(self):await self.exercise(True)


if __name__=='__main__':unittest.main()
