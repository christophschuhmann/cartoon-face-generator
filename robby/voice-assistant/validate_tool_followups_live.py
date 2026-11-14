"""Real-model follow-up / unknown paraphrase / session-rule regression tier."""
import asyncio,json,time
from pathlib import Path
import httpx
from bolt_pipeline import pipeline
from conversation_director import CompactDirector
from llm_backends import config
from interaction_policy import RuleBook
ROOT=Path(__file__).parent
async def main():
 report={'cases':[],'date':'2026-11-14'}
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8792',timeout=45.) as c:
  h=[{'role':'user','content':'Ich möchte etwas über Viktor Frankls Logotherapie wissen.'},{'role':'assistant','content':'Sie beschäftigt sich mit Sinn und Verantwortung.'}]
  for text,history,expect in [('Kannst du das mal nachgucken?',h,'search'),('Ich möchte sehen, wie du deine Augen einmal im Kreis wandern lässt.',[],'avatar')]:
   row={'request':text,'history':history};t=time.perf_counter()
   try:
    ev=[(k,v) async for k,v in pipeline(c,text,{},history,tts=False,llm_selection={'model':'qwen','provider':'cerebras/fp16'})]
    last=[v for k,v in ev if k=='sentence'][-1];row.update(text=last['text'],lookups=last.get('lookups',[]),sources=last.get('sources',[]),actions=last.get('avatar_actions',[]),metrics=next(v for k,v in ev if k=='done'))
    if expect=='search':assert row['sources'] and any('frankl' in str(x.get('arguments')).lower() or 'logotherap' in str(x.get('arguments')).lower() for x in row['lookups']),row['lookups']
    else:assert any(a['kind']=='eye_roll' for a in row['actions']),row['actions']
    row['passed']=True
   except Exception as e:row.update(passed=False,error=str(e)[:800])
   row['ms']=round((time.perf_counter()-t)*1000);report['cases'].append(row);print(text,row['passed'],row.get('error',''),flush=True);await asyncio.sleep(2)
  book=RuleBook()
  for text,mode in [('Unterbrich mich, wenn ich Bananen sage, und sage Stopp, stopp.','any_term'),('Unterbrich mich, wenn meine Erklärung sich selbst widerspricht. Entscheide nach der Bedeutung, nicht nach bestimmten Wörtern.','semantic'),('Lösche bitte die Unterbrechungsregeln.',None)]:
   row={'request':text,'expected_mode':mode};t=time.perf_counter()
   try:
    r=await CompactDirector().generate(c,text,{},[],interaction_state={'enabled':True,'rules':book.public()},provider=config({'model':'qwen','provider':'cerebras/fp16'}));actions=r.get('interaction_actions',[]);row.update(actions=actions,text=r['text'])
    if mode:assert any(a['arguments'].get('match_mode')==mode for a in actions),actions
    else:assert any(a['name']=='clear_interruption_rules' for a in actions),actions
    # Isolated synthetic rule book only, never the live user's conversation.
    book.apply(actions,'test-owner',text);row['rulebook_after']=book.public();row['passed']=True
   except Exception as e:row.update(passed=False,error=str(e)[:800])
   row['ms']=round((time.perf_counter()-t)*1000);report['cases'].append(row);print(text,row['passed'],row.get('error',''),flush=True);await asyncio.sleep(2)
 report['passed']=all(x['passed'] for x in report['cases']);(ROOT/'logs/tool-followups-live-20261114.json').write_text(json.dumps(report,indent=2,ensure_ascii=False));print('PASSED',report['passed'],flush=True)
if __name__=='__main__':asyncio.run(main())
