"""No live services: command, tool availability, and latency option contracts."""
import unittest,json
from unittest.mock import patch,AsyncMock
from types import SimpleNamespace
from avatar_commands import explicit_actions
from avatar_actions import EMOTIONS,validate
from bolt_director import needs_tools,SYSTEM
from conversation_prompt import POLICY
from knowledge_tools import required_lookup,relevant,arguments
from verification_settings import validated,tts_options,final_model,search_options
from web_lookup import public_link

class Capabilities(unittest.TestCase):
 def test_exact_requests_wake_aliases_followups(self):
  for prefix in ('','Hey Robbie, ','Hi Robby, ','Robbi, '):
   for text,kind in [('schneid eine Grimasse','grimace'),('mach einen Salto','somersault'),('mach ein ernstes Gesicht','emotion'),('dreh dich im Kreis','spin')]:
    self.assertEqual(explicit_actions(prefix+text)[0]['kind'],kind,prefix+text)
  self.assertEqual(explicit_actions('Mach ein ernstes Gesicht')[0]['emotion'],'concentration')
  self.assertEqual(explicit_actions('Mach so 😡')[0]['emotion'],'anger')
  self.assertEqual(explicit_actions('Hi Robbie, please do a somer salt.')[0]['kind'],'somersault')
  self.assertEqual(explicit_actions('Noch mal!',history=[{'role':'user','content':'Mach einen Salto'}])[0]['kind'],'somersault')
  self.assertFalse(explicit_actions('Noch mal!',history=[{'role':'user','content':'Erzähl einen Witz'}]))
 def test_known_capabilities_are_in_both_prompts(self):
  for prompt in (SYSTEM,POLICY):
   for word in ('somersault','search_web','concentration','perform_avatar'):self.assertIn(word,prompt)
  for emotion in EMOTIONS:self.assertIn(emotion,SYSTEM)
 def test_lookup_context_and_fresh_task(self):
  for prompt in ('Kannst du das mal nachgucken?','Bitte schau das nach.','Look that up.','Kannst du im Internet dazu suchen?'):
   self.assertTrue(needs_tools(prompt,[],None),prompt)
   self.assertEqual(required_lookup(prompt),'search_web',prompt)
  self.assertEqual(required_lookup('Kannst du das mal nachgucken?',[{'role':'user','content':'Was sagt Wikipedia über Logotherapie?'}]),'search_wikipedia')
  self.assertFalse(needs_tools('Erzähle einen Witz.',[{'role':'user','content':'Suche bei Wikipedia nach Pinguinen'}],None))
  for t in ('Bitte nicht nachgucken.','Do not search the web.','Erfinde eine Nachricht.'):
   self.assertFalse(relevant(t),t)
  self.assertTrue(needs_tools('Zeig ein Gesicht wie eine Zitrone.',[],None))
  self.assertEqual(explicit_actions('Ich möchte sehen, wie du deine Augen im Kreis wandern lässt.')[0]['kind'],'eye_roll')
  self.assertFalse(needs_tools('Ich möchte sehen, wie du mir deine Augen erklärst.',[],None))
 def test_options_not_truthy_strings_or_speaker_bypass(self):
  self.assertEqual(tts_options({}),{'align':True,'speech_verification':'parallel'})
  self.assertFalse(tts_options({'verify_tts':False})['align'])
  self.assertEqual(tts_options({'serial_tts':True})['speech_verification'],'serial')
  for raw in ({'verify_tts':'false'},{'skip_speaker':True},[],{'verify_input':0}):
   with self.assertRaises(ValueError):validated(raw)
  c=SimpleNamespace(verification_settings=validated({'verify_input':False}));s=SimpleNamespace(c=c,asr=SimpleNamespace(selected='parakeet_ultra'))
  self.assertEqual(final_model(s),'nemotron');c.verification_settings['verify_input']=True;self.assertEqual(final_model(s),'parakeet_ultra')
 def test_search_settings_are_explicit_and_model_specific(self):
  self.assertEqual(search_options({}),{})
  self.assertEqual(search_options({'candidate_search':True})['search_n'],3)
  self.assertEqual(search_options({'candidate_search':True})['search_chunk_frames'],12)
  self.assertEqual(search_options({'candidate_search':True},'large'),{})
  self.assertEqual(search_options({'candidate_search':True},eligible=False),{})
 def test_search_links_and_args(self):
  for url in ('file:///etc/passwd','http://example.org','https://localhost','https://127.0.0.1','https://192.168.1.1','https://169.254.169.254/a','https://a.local/a','javascript:alert(1)','https://u:p@example.org'):self.assertFalse(public_link(url),url)
  self.assertTrue(public_link('https://www.nasa.gov/a'))
  self.assertEqual(arguments('search_web',{'query':'NASA Artemis'}),{'query':'NASA Artemis'})

class Pipeline(unittest.IsolatedAsyncioTestCase):
 async def test_unknown_phrase_uses_model_requested_tool_director(self):
  from bolt_pipeline import pipeline
  from tool_capabilities import ToolRouteRequest
  async def request(*a,**kw):
   raise ToolRouteRequest()
   yield
  result={'script':'(amusement) Schau mal, jetzt kommt meine lustige Grimasse!','language':'de','avatar_actions':validate({'steps':[{'kind':'grimace'}]}),'director_ms':3}
  with patch('bolt_pipeline.BoltDirector.stream',request),patch('conversation_director.CompactDirector.generate',AsyncMock(return_value=result)) as tool:
   events=[x async for x in pipeline(None,'Überrasche mich mit einem kleinen optischen Schabernack.',{},[],tts=False)]
  self.assertEqual(tool.await_count,1)
  self.assertTrue(any(k=='sentence' and v.get('avatar_actions') for k,v in events))
 async def test_real_tts_request_receives_toggle(self):
  import numpy as np
  from bolt_pipeline import pipeline
  from bolt_text import Sentence
  bodies=[]
  async def events(client,body,*a,**kw):
   bodies.append(body);yield {'event':'done'}
  with patch('bolt_pipeline.speech_events',events):
   # No PCM is expected in this transport contract; producer still sends body.
   try:[x async for x in pipeline(None,'Hallo',{},[],preset=[Sentence('Hallo zusammen.','interest')],verification_settings={'verify_tts':False})]
   except Exception:pass
  self.assertEqual(len(bodies),1)
  self.assertFalse(bodies[0]['align']);self.assertEqual(bodies[0]['speech_verification'],'parallel')
 async def test_candidate_search_reaches_actual_sentence_request(self):
  from bolt_pipeline import pipeline
  from bolt_text import Sentence
  bodies=[]
  async def events(client,body,*a,**kw):
   bodies.append(body);yield {'event':'result','candidates':[]}
  with patch('bolt_pipeline.speech_events',events):
   try:[x async for x in pipeline(None,'Hallo',{},[],preset=[Sentence('Hallo zusammen.','interest')],verification_settings={'candidate_search':True})]
   except Exception:pass
  self.assertEqual(len(bodies),1)
  self.assertEqual(bodies[0]['generation'],'search_asr')
  self.assertEqual(bodies[0]['search_n'],3)
