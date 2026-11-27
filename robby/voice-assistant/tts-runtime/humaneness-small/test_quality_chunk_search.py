import unittest
from quality_chunk_search import combine

class QualitySearchTests(unittest.TestCase):
    def test_exact_studio_formula_and_bounded_inverse_wer(self):
        row={'prefix_wer':.25,'timestamps':[],'matched_words':3}
        result=combine(row,clap=.2,speaker=.8)
        self.assertAlmostEqual(result['reward'],.75*(.4*.6+.6*.9))
        self.assertEqual(result['matched_words'],3)
        self.assertEqual(combine({'prefix_wer':2},.5,.5)['reward'],0.)
        self.assertEqual(combine({'prefix_wer':-1},-2.,2.)['reward'],.6)

if __name__=='__main__':unittest.main()
