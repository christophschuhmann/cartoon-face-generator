import unittest
import numpy as np
from quality_chunk_search import QualitySearchScorer, combine
from asr_chunk_search import OrderedSearchCommitter
from streaming_boundaries import written_suffixes, RATE, UnverifiedSpeechError

class QualitySearchTests(unittest.TestCase):
    def test_exact_studio_formula_and_bounded_inverse_wer(self):
        row={'prefix_wer':.25,'timestamps':[],'matched_words':3}
        result=combine(row,clap=.2,speaker=.8)
        self.assertAlmostEqual(result['reward'],.75*(.4*.6+.6*.9))
        self.assertEqual(result['matched_words'],3)
        self.assertEqual(combine({'prefix_wer':2},.5,.5)['reward'],0.)
        self.assertEqual(combine({'prefix_wer':-1},-2.,2.)['reward'],.6)

    def scorer(self,text):
        scorer=QualitySearchScorer.__new__(QualitySearchScorer)
        scorer.suffixes=written_suffixes(text)
        return scorer

    def score(self,scorer,text,words,final=False):
        spans=[{'word':w,'start':(i+1)*.1,'end':(i+2)*.1} for i,w in enumerate(words.split())]
        return scorer.ordered_score(text,spans,RATE,final)

    def test_missing_negation_blocks_suffix_and_resumes_original_script(self):
        text='Ich will nicht gehen.'
        scorer=self.scorer(text)
        wrong=self.score(scorer,text,'ich will gehen',True)
        self.assertEqual(wrong['ordered_words'],2)
        self.assertFalse(wrong['complete'])
        received=[]
        c=OrderedSearchCommitter(lambda audio,_: received.append(len(audio)),text)
        c.feed(np.ones(RATE),{'step':1,'retained_rows':[1],'scores':[{},wrong]})
        c.finish(wrong)
        self.assertEqual(sum(received),int(wrong['ordered_end_s']*RATE))
        self.assertEqual(c.report['remaining_text'],'nicht gehen.')

    def test_natural_tail_preserved_including_final_evidence_without_new_pcm(self):
        text='Guten Morgen!'
        scorer=self.scorer(text)
        prefix=self.score(scorer,text,'guten')
        full=self.score(scorer,text,'guten morgen',True)
        for early in [prefix,full]:
            out=[]
            c=OrderedSearchCommitter(lambda a,_:out.append(a),text)
            self.assertFalse(c.feed(np.ones(RATE),{'step':1,'retained_rows':[0],'scores':[early]}))
            if early is prefix:self.assertFalse(out)
            c.finish(full)
            pcm=np.concatenate(out)
            self.assertEqual(len(pcm),RATE)
            self.assertEqual(pcm[-1],1.)
            self.assertTrue(c.report['end_verified'])
            self.assertFalse(c.report['tail_cutoff'])

    def test_quality_cannot_select_dead_or_empty_take_over_live_progress(self):
        text='Heute ist es kalt.'
        scorer=self.scorer(text)
        dead=self.score(scorer,text,'heute ist',True)
        empty=self.score(scorer,text,'')
        good=self.score(scorer,text,'heute ist es')
        rows=[dict(row,reward=r,prefix_wer=0) for row,r in [(dead,1),(empty,1),(good,.3)]]
        self.assertEqual(min(range(3),key=lambda i:scorer.selection_key(rows[i])),2)
        c=OrderedSearchCommitter(lambda *_:self.fail('unconfirmed PCM'),text)
        with self.assertRaises(UnverifiedSpeechError):c.finish(empty)

    def test_never_resume_half_of_a_contraction(self):
        text="We know it's ready."
        scorer=self.scorer(text)
        score=self.score(scorer,text,'we know it',True)
        self.assertEqual(scorer.suffixes[score['ordered_words']],"it's ready.")

if __name__=='__main__':unittest.main()
