import asyncio,json,time,httpx
from bolt_director import SYSTEM
URL='http://127.0.0.1:18826/v1/chat/completions'
CASES=[('greeting','Hallo Robby, wie geht es dir?'),('joke','Erzähle mir einen kurzen lustigen Witz über Roboter.'),('poem','Schreibe mir ein kleines Gedicht mit vier Zeilen über einen freundlichen Roboter.'),('memory','Ich heiße Christoph. Was möchtest du gemeinsam erleben?')]
async def main():
 async with httpx.AsyncClient(timeout=90,trust_env=False) as client:
  for label,query in CASES:
   body={'model':'gemma-4-26b-a4b-q4','messages':[{'role':'system','content':SYSTEM},{'role':'user','content':query}],'temperature':.7,'max_tokens':160,'stream':True,'chat_template_kwargs':{'enable_thinking':False},'stream_options':{'include_usage':True}}
   t=time.perf_counter();first=None;content='';final={};status=0
   try:
    async with client.stream('POST',URL,json=body) as r:
     status=r.status_code
     if status!=200:print(json.dumps({'case':label,'status':status}));continue
     async for line in r.aiter_lines():
      if not line.startswith('data: '):continue
      raw=line[6:]
      if raw=='[DONE]':break
      obj=json.loads(raw);choices=obj.get('choices') or []
      if choices:
       d=choices[0].get('delta') or {};s=d.get('content') or ''
       if s and first is None:first=time.perf_counter()
       content+=s
      if obj.get('timings'):final['timings']=obj['timings']
      if obj.get('usage'):final['usage']=obj['usage']
    print(json.dumps({'case':label,'status':status,'first_ms':round((first-t)*1000) if first else None,'total_ms':round((time.perf_counter()-t)*1000),'text':content,**final},ensure_ascii=False),flush=True)
   except Exception as e:print(json.dumps({'case':label,'error':type(e).__name__}),flush=True)
asyncio.run(main())
