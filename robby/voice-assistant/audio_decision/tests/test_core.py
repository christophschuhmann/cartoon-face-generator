"""CPU-only contract tests. GPU/browser integration lives in browser.cjs."""
import unittest,csv,io
from audio_decision.core import Settings,TAXONOMY,intervals,process_rows,csv_export
from audio_decision.storage import key
class Contracts(unittest.TestCase):
 def test_verified_taxonomies(self):
  for name,count in [('classic',527),('strong',456)]:
   self.assertEqual(len(TAXONOMY[name]),count);self.assertEqual(len({c['id'] for c in TAXONOMY[name]}),count)
 def test_partial_history_and_final_interval(self):
  self.assertEqual(intervals(7200,200),[(0,0,3200),(1,3200,6400),(2,6400,7200)])
 def test_invalid_or_duplicate_class_rejected(self):
  for ids in [[],['unknown'],['/m/09x0r','/m/09x0r']]:
   with self.assertRaises(ValueError):Settings(selected_ids=ids)
 def test_cache_separates_context_and_target_method(self):
  s=Settings().model_dump();self.assertNotEqual(key('audio',s),key('audio',s|{'context':'pool'}));self.assertNotEqual(key('audio',s),key('audio',s|{'repeat_target':True}))
 def test_missing_is_not_silence_and_resets_smoothing(self):
  classes=[{'id':'x','name':'Test'}];rows=[{'start_s':i*.2,'end_s':(i+1)*.2,'raw':[p],'status':'test'} for i,p in enumerate([1.,None,0.])]
  smooth,events=process_rows(rows,classes,Settings().model_dump());self.assertEqual(smooth,[[1.],[None],[0.]]);self.assertEqual(events[0]['end_time'],.2)
  result={'classes':classes,'rows':rows,'smoothed_scores':smooth};parsed=list(csv.reader(io.StringIO(csv_export(result))))
  self.assertEqual(parsed[2][-1],'');self.assertEqual(parsed[3][-1],'0.0')
 def test_causal_and_short_impulse(self):
  c=[{'id':'x','name':'Test'}];s=Settings(ema_ms=0).model_dump();rows=[{'start_s':i*.2,'end_s':(i+1)*.2,'raw':[p]} for i,p in enumerate([0.,1.,0.,0.])]
  short,_=process_rows(rows[:2],c,s);full,events=process_rows(rows,c,s);self.assertEqual(short,full[:2]);self.assertAlmostEqual(events[0]['end_time']-events[0]['start_time'],.2)
if __name__=='__main__':unittest.main()
