import argparse,asyncio,time,json,httpx
from speech_retry import retained_speech_events
from bolt_text import Sentence
from collections import Counter
phrases=['Hm, das ist eine gute Frage.', 'Oh, ja, ich helfe dir gerne weiter.', '2026 ist ein spannendes Jahr.', 'Das kostet etwa 15 Euro und 50 Cent.', 'ChatGPT kann dabei sehr hilfreich sein.', 'Zum Beispiel kannst du das ausprobieren.', 'Das ist z. B. eine interessante Idee.', 'Okay, ich mache jetzt einen Salto!', 'In den USA gibt es viele interessante Orte.', 'Ach, das klingt ja richtig wunderbar!']
async def main(attempts):
 counts=Counter()
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8792',timeout=60) as c:
  for n,text in enumerate(phrases):
   spec=Sentence(text,language='de').spec();body={'model':'small_rl','input_mode':'manual','format':'structured','message':spec['manual_prompt'],'language':'de','generation':'single','n':1,'batch_size':1,'streaming':True,'stream_transport':'pcm_f32','live_only':True,'chunk_frames':20,'cancel_on_disconnect':True,'temperature':.8,'guidance':2.,'voice_mode':'profile','voice_profile':'emolia_c1699','voice_conversion':False,'speaker_steering':False,'dynamic_reference':False,'align':True,'speech_verification':'parallel','seed':777+n}
   async def notice(*a):pass
   started=time.monotonic();failure=None;reports=[];chunks=0
   async for event in retained_speech_events(c,body,notice,attempts=attempts):
    if event.get('event')=='audio_chunk':chunks+=1
    if event.get('event')=='speech_unavailable':failure=event['code']
    if event.get('event')=='result':reports.append({k:v for k,v in (event.get('live_stream') or {}).items() if k in ['start_verified','end_verified','asr_calls','asr_error','target_word_count','ordered_target_words','asr_word_count','backend','resume_safe']})
   counts[failure or 'complete']+=1
   print(json.dumps({'case':n,'failure':failure,'chunks':chunks,'reports':reports,'ms':round(1000*(time.monotonic()-started))}),flush=True)
 print('SUMMARY',dict(counts),flush=True)
if __name__ == '__main__':
 parser=argparse.ArgumentParser(description='Run ten synthetic fixed-seed German TTS boundary cases against the local TTS server.')
 parser.add_argument('--attempts',type=int,choices=(1,2,3),default=1)
 asyncio.run(main(parser.parse_args().attempts))
