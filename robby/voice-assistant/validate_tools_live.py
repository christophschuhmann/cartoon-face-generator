"""Authored German/English requests, real configured model + live read-only tools.
No audio/GPU synthesis in this tier; browser tests cover playback and rendering.
"""
import asyncio,json,time
from pathlib import Path
import httpx
from bolt_pipeline import pipeline
ROOT=Path(__file__).parent
CASES=[
 ('Hey Robbie, schneid eine Grimasse.','grimace',None),
 ('Mach ein ernstes Gesicht.','emotion','concentration'),
 ('Mach einen Salto rückwärts.','somersault',None),
 ('Hi Robby, sei mal wütend.','emotion','anger'),
 ('Mach so 😡','emotion','anger'),
 ('Mach einen Hundeblick.','puppy',None),
 ('Puste deine Backen auf und schiele lustig.','grimace',None),
 ('Kannst du kurz mit einem Auge blinzeln?','wink',None),
 ('Look stern, then make a funny face.','emotion','concentration'),
 ('Rolle mit den Augen.','eye_roll',None),
 ('Nicke und schüttle dann den Kopf.','nod',None),
 ('Erzähl ein Gedicht über einen Roboter in vier Zeilen.',None,None),
 ('Sag nur: Ich kann einen Salto machen.',None,None),
 ('Schau bei Wikipedia nach Pinguinen und nenne zwei Fakten.','lookup','search_wikipedia'),
 ('Guck die aktuellen Tagesschau-Nachrichten nach und nenne zwei Schlagzeilen.','lookup','search_news'),
 ('Wie wird das Wetter morgen in Berlin? Nenne zwei Sätze.','lookup','get_weather'),
 ('Finde die offizielle Internetseite des Viktor Frankl Instituts.','lookup','search_web'),
]
async def main():
 report={'date':'2026-11-14','mode':'real Qwen Cerebras, no TTS in this tier','cases':[]}
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8792',timeout=45.) as client:
  for text,kind,extra in CASES:
   row={'request':text};start=time.perf_counter()
   try:
    events=[(k,v) async for k,v in pipeline(client,text,{},[],tts=False,llm_selection={'model':'qwen','provider':'cerebras/fp16'})]
    sentences=[v for k,v in events if k=='sentence'];row['text']=sentences[-1]['text'] if sentences else ''
    acts=[a for k,v in events if k=='avatar_action' for a in v.get('steps',[])];acts+=next((v.get('avatar_actions',[]) for v in sentences if v.get('avatar_actions')),[])
    row['actions']=acts;row['lookups']=sentences[-1].get('lookups',[]) if sentences else [];row['sources']=sentences[-1].get('sources',[]) if sentences else []
    row['metrics']=next((v for k,v in events if k=='done'),{})
    assert sentences,'No spoken text'
    if kind=='lookup':
     assert any(x['tool']==extra and not x.get('error') for x in row['lookups']),row['lookups']
     assert row['sources'],'Missing actual sources'
    elif kind:
     assert any(a['kind']==kind and (not extra or a.get('emotion')==extra) for a in acts),acts
     assert not any(p in row['text'].lower() for p in ('kann keine saltos','kann keinen salto','habe keine beine','nur ein text'))
    else:assert not acts,acts
    row['passed']=True
   except Exception as e:row.update(passed=False,error=str(e)[:400],error_type=type(e).__name__)
   row['ms']=round((time.perf_counter()-start)*1000);report['cases'].append(row)
   print(text,'PASS' if row['passed'] else 'FAIL',row.get('error',''),flush=True)
   (ROOT/'logs/tools-live-20261114.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
   await asyncio.sleep(1.5)
  # Explicitly anaphoric research: facts and target refer to the prior topic.
  h=[{'role':'user','content':'Ich möchte etwas über Viktor Frankls Logotherapie wissen.'},{'role':'assistant','content':'Sie beschäftigt sich mit Sinn und Verantwortung.'}]
  row={'request':'Kannst du das mal nachgucken?','history':h}
  try:
   ev=[(k,v) async for k,v in pipeline(client,row['request'],{},h,tts=False,llm_selection={'model':'qwen','provider':'cerebras/fp16'})]
   last=[v for k,v in ev if k=='sentence'][-1];row.update(text=last['text'],lookups=last.get('lookups'),sources=last.get('sources'))
   assert row['sources'];assert any('frankl' in str(x.get('arguments')).lower() or 'logotherap' in str(x.get('arguments')).lower() for x in row['lookups']);row['passed']=True
  except Exception as e:row.update(passed=False,error=str(e)[:400])
  report['cases'].append(row);report['passed']=all(x['passed'] for x in report['cases']);(ROOT/'logs/tools-live-20261114.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print('ALL PASSED',report['passed'],flush=True)
if __name__=='__main__':asyncio.run(main())
