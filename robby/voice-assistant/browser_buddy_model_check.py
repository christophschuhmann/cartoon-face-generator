"""Run the production ONNX WASM worker in Chromium on synthetic fixtures."""
import asyncio,base64,json,subprocess,os
from pathlib import Path
from playwright.async_api import async_playwright
P=Path(os.environ.get('BUDDY_FIXTURES','/mnt/nvme/moss-15-v2/buddy-test'))
def data(name):
 b=subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(P/(name+'.wav')),'-ar','16000','-ac','1','-f','f32le','pipe:1'],capture_output=True,check=True).stdout
 return base64.b64encode(b).decode()
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox']);page=await browser.new_page()
  models=set()
  page.context.on('request',lambda r:models.add(r.url.rsplit('/',1)[-1]) if '/static/wake-models/' in r.url else None)
  await page.goto('http://127.0.0.1:8793/not-a-route')
  print('Loading browser WASM models',flush=True)
  await page.evaluate('''() => {window.messages=[];window.w=new Worker('/static/buddy-worker.js?v=buddy-admit-1');w.onmessage=e=>messages.push(e.data);w.onerror=e=>messages.push({type:'fatal',message:e.message});w.postMessage({type:'init'});}''')
  await page.wait_for_function("messages.some(x=>['ready','error','fatal'].includes(x.type))",timeout=120000)
  state=await page.evaluate('messages');print('Model state',json.dumps(state),flush=True)
  if any(x['type'] in ('error','fatal') for x in state):raise RuntimeError('worker init failed')
  expected={'melspectrogram.onnx','embedding_model.onnx','hey_buddy_en_tiny.onnx','go_buddy_en_medium.onnx','stop_buddy_en_medium.onnx'}
  if models!=expected:raise AssertionError(('Requested model files',sorted(models)))
  for name in ('hey','go','stop','go-bunny'):
   before=await page.evaluate('messages.length');encoded=data(name)
   await page.evaluate('''s=>{let bytes=Uint8Array.from(atob(s),c=>c.charCodeAt(0)),x=new Float32Array(bytes.buffer),a=new Float32Array(32000);a.set(x.subarray(Math.max(0,x.length-32000)),Math.max(0,32000-x.length));w.postMessage({type:'audio',samples:a.buffer},[a.buffer]);}''',encoded)
   await page.wait_for_function('(n)=>messages.slice(n).some(x=>["scores","error"].includes(x.type))',arg=before,timeout=30000)
   m=await page.evaluate('(n)=>messages.slice(n).find(x=>x.type==="scores"||x.type==="error")',before)
   if m['type']!='scores':raise AssertionError(m)
   if name in ('hey','go','stop') and max(m['scores'],key=m['scores'].get)!=name:raise AssertionError((name,m))
   print(name,json.dumps(m),flush=True)
  # At a live 160-ms hop, compare reuse against a fresh extraction on
  # exactly the same audio. A cache-offset error changes the head scores.
  result=await page.evaluate('''async(encoded)=>{
   const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
   const samples=new Float32Array(34560),clip=new Float32Array(bytes.buffer);
   samples.set(clip.subarray(0,22000),10000);
   async function score(start){
    const data=samples.slice(start,start+32000);
    const scored=new Promise((resolve,reject)=>{
     function read(e){
      if(e.data.type==='scores'||e.data.type==='error'){
       w.removeEventListener('message',read);
       if(e.data.type==='error')reject(Error(e.data.message));else resolve(e.data);
      }
     }
     w.addEventListener('message',read);
    });
    w.postMessage({type:'window',samples:data.buffer,end:start+32000},[data.buffer]);return scored;
   }
   w.postMessage({type:'reset'});await score(0);
   const reused=await score(2560);
   w.postMessage({type:'reset'});const full=await score(2560);
   return {max_error:Math.max(...Object.keys(full.scores).map(k=>Math.abs(full.scores[k]-reused.scores[k]))),
    cached_ms:reused.ms,full_ms:full.ms};
  }''',data('hey'))
  print('Overlap cache',result,flush=True)
  if result['max_error']>1e-5:raise AssertionError(result)
  await browser.close()
asyncio.run(main())
