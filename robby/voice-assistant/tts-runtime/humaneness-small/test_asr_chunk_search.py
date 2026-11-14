import unittest
import numpy as np
from asr_chunk_search import align_prefix, SearchCommitter, ASRSearchScorer, merge_history
from streaming_boundaries import UnverifiedSpeechError
from beam_search import expansion_indices, reorder_codec
import torch
from types import SimpleNamespace

class SearchTests(unittest.TestCase):
    def test_failed_codec_capture_clears_only_its_owned_state(self):
        from search_codec_graph import SearchStreamingCodec,BANKS
        state=object();module=SimpleNamespace(_streaming_state=state)
        def fail():raise torch.cuda.OutOfMemoryError('injected test')
        owner=SimpleNamespace(modules=[module],states=[state],attach=fail)
        stream=SearchStreamingCodec.__new__(SearchStreamingCodec)
        stream.key=('test',3,12);stream.graphs=owner;BANKS[stream.key]=owner
        with self.assertRaises(torch.cuda.OutOfMemoryError):stream.__enter__()
        self.assertIsNone(module._streaming_state);self.assertIsNone(stream.graphs)
        self.assertNotIn(stream.key,BANKS)
    def test_rolling_overlap_preserves_words_despite_shifted_timestamps(self):
        old=[dict(word=w,start=i*.3,end=i*.3+.25) for i,w in enumerate('a rainbow appears when sunlight enters drops'.split())]
        recent=[dict(word=w,start=.93+i*.3,end=1.18+i*.3) for i,w in enumerate('when sunlight enters drops of water'.split())]
        result,found=merge_history(old,recent,.8,old[:2])
        self.assertTrue(found)
        self.assertEqual([w['word'] for w in result],'a rainbow appears when sunlight enters drops of water'.split())
    def test_repeated_phrase_needs_time_consistency(self):
        old=[dict(word=w,start=i,end=i+.5) for i,w in enumerate('hello friend then hello friend'.split())]
        recent=[dict(word=w,start=3.1+i,end=3.6+i) for i,w in enumerate('hello friend again'.split())]
        result,found=merge_history(old,recent,2.8,[])
        self.assertTrue(found);self.assertEqual([w['word'] for w in result],'hello friend then hello friend again'.split())
    def test_api_search_requires_supported_shape(self):
        from small_app import Turn,candidate_batch_size
        body=dict(message='hello',model='small_rl',generation='search_asr',search_n=3,
            live_only=True,streaming=True,stream_transport='pcm_f32',search_chunk_frames=12)
        self.assertEqual(candidate_batch_size(Turn(**body)),3)
        for override in ({'search_n':8},{'model':'large17'},{'live_only':False},{'voice_conversion':True}):
            with self.assertRaises(ValueError):Turn(**{**body,**override})
    def test_prefix_and_final_differ(self):
        r='one two three four'.split();h=['one','two']
        self.assertEqual(align_prefix(r,h)['errors'],0)
        self.assertEqual(align_prefix(r,h,True)['errors'],2)
    def test_negation_not_silently_matched(self):
        a=align_prefix('ich will nicht gehen'.split(),'ich will gehen'.split(),True)
        self.assertEqual(a['errors'],1);self.assertNotIn(2,[i for i,j in a['matches']])
    def test_insertions_penalized(self):
        self.assertEqual(align_prefix(['hello','friend'],['hello','blah','friend'],True)['errors'],1)
    def test_empty_has_no_progress(self):
        a=align_prefix(['hello'],[]);self.assertFalse(a['matches']);self.assertEqual(a['matched_prefix_words'],0)
    def test_clone_rows_do_not_share_mutable_state(self):
        state=SimpleNamespace(cache=torch.tensor([[1.],[2.],[3.]]))
        codec=SimpleNamespace(modules=lambda:[SimpleNamespace(_streaming_state=state)])
        reorder_codec(codec,torch.tensor(expansion_indices([1],3)),3)
        self.assertEqual(state.cache.tolist(),[[2.],[2.],[2.]])
        state.cache[0,0]=9;self.assertEqual(state.cache[1,0],2)
    def test_shared_timestamps_fades_without_asr(self):
        emitted=[];c=SearchCommitter(lambda w,d:emitted.append(w.copy()))
        detail={'step':1,'retained_rows':[0],'scores':[{'start_s':.2,'end_s':.7}]}
        self.assertTrue(c.feed(np.ones(48000,np.float32),detail));c.finish()
        a=np.concatenate(emitted);self.assertEqual(len(a),33600)
        self.assertAlmostEqual(a[0],0);self.assertAlmostEqual(a[-1],0)
        self.assertFalse(c.report['asr_postcheck'])
    def test_inplace_codec_fork_preserves_addresses_and_shared_masks(self):
        mask=torch.tensor([True,False,True]);value=torch.tensor([[1.],[2.],[3.]])
        a=SimpleNamespace(mask=mask,cache=value);b=SimpleNamespace(mask=mask)
        codec=SimpleNamespace(modules=lambda:[SimpleNamespace(_streaming_state=s) for s in (a,b)])
        address=value.data_ptr();reorder_codec(codec,torch.tensor([1,2,0]),3,inplace=True)
        self.assertEqual(value.data_ptr(),address);self.assertIs(a.mask,b.mask)
        self.assertEqual(mask.tolist(),[False,True,True]);self.assertEqual(value.tolist(),[[2.],[3.],[1.]])
    def test_missing_opening_is_bounded(self):
        c=SearchCommitter(lambda *a:None)
        with self.assertRaises(UnverifiedSpeechError):
            c.feed(np.zeros(4*48000,np.float32),{'step':1,'retained_rows':[0],'scores':[{}]})
    def test_score_progress_beats_empty_or_truncated(self):
        s=ASRSearchScorer.__new__(ASRSearchScorer)
        s.device='test';s.history=[];s.window_seconds=12.;s.check_cancel=lambda:None
        def scores(gates):
            words=[['hello'],['hello','dear','friend'],[]]
            return [{'timestamps':[{'word':w,'start':j*.2,'end':j*.2+.1} for j,w in enumerate(row)]} for row in words]
        s.reader=SimpleNamespace(scores=scores)
        rows=s.score([np.ones(48000,np.float32)]*3,'hello dear friend',[False]*3)
        self.assertEqual(max(range(3),key=lambda i:rows[i]['reward']),1)
        self.assertTrue(rows[1]['complete'])
        self.assertIsNone(rows[0]['start_s'])

if __name__=='__main__':unittest.main()
