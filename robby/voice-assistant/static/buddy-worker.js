/* LAION Buddy ONNX wakewords. CPU/WASM in a dedicated browser worker. */
importScripts('/static/vendor/onnxruntime/ort.min.js?v=1.20.1');
ort.env.wasm.numThreads=1;
ort.env.wasm.wasmPaths='/static/vendor/onnxruntime/';
const base='/static/wake-models/';
let mel,embedding,heads={},ring=new Float32Array(32000),filled=0,total=0,last=0,busy=false,ready=false,version=0;
// Adjacent classifier inputs share most 80-ms embedding steps. Reuse steps
// only when their absolute sample offsets match within the same capture.
let previousEmbeddings=new Map();
async function session(name){return ort.InferenceSession.create(base+name,{executionProviders:['wasm'],graphOptimizationLevel:'all'});}
async function init(){
 postMessage({type:'loading'});
 [mel,embedding]=await Promise.all(['melspectrogram.onnx','embedding_model.onnx'].map(session));
 for(const [command,filename] of Object.entries({
  hey:'hey_buddy_en_tiny.onnx',
  go:'go_buddy_en_medium.onnx',
  stop:'stop_buddy_en_medium.onnx',
 }))heads[command]=await session(filename);
 ready=true;postMessage({type:'ready'});
}
async function run(s,input,shape){const out=await s.run({[s.inputNames[0]]:new ort.Tensor('float32',input,shape)});return out[s.outputNames[0]];}
async function predict(snapshot,end,epoch){
 const start=performance.now();
 try{
  const raw=await run(mel,snapshot,[1,32000]),mf=raw.data,frames=Math.floor(mf.length/32);
  const starts=[];for(let i=0;i<=frames-76;i+=8)starts.push(i);
  if(starts.length<16)return;
  const offsets=starts.slice(-16);
  const keys=offsets.map(i=>end-snapshot.length+i*160);
  const missing=offsets.map((_,j)=>j).filter(j=>!previousEmbeddings.has(keys[j]));
  const fresh=new Map();
  if(missing.length){
   const size=76*32,input=new Float32Array(missing.length*size);
   for(const [n,j] of missing.entries()){
    for(let k=0;k<size;k++)input[n*size+k]=mf[offsets[j]*32+k]/10+2;
   }
   const emb=await run(embedding,input,[missing.length,76,32,1]);
   for(const [n,j] of missing.entries())fresh.set(keys[j],emb.data.slice(n*96,(n+1)*96));
  }
  if(epoch!==version)return;
  const next=new Map(),vec=new Float32Array(16*96);
  for(const [j,key] of keys.entries()){
   const step=fresh.get(key)||previousEmbeddings.get(key);next.set(key,step);vec.set(step,j*96);
  }
  previousEmbeddings=next;
  const scores={};
  for(const [command,head] of Object.entries(heads)){
   scores[command]=(await run(head,vec,[1,16,96])).data[0];
  }
  if(epoch===version)postMessage({type:'scores',end,scores,ms:performance.now()-start});
 }catch(e){postMessage({type:'error',message:String(e?.message||e)});}finally{busy=false;}
}
onmessage=e=>{
 if(e.data.type==='init'){init().catch(err=>postMessage({type:'error',message:String(err?.message||err)}));return;}
 if(e.data.type==='reset'){version++;previousEmbeddings.clear();ring.fill(0);filled=0;total=0;last=0;return;}
 if(e.data.type==='window'&&ready){if(busy){postMessage({type:'skipped'});return;}busy=true;void predict(new Float32Array(e.data.samples),e.data.end,version);return;}
 if(e.data.type!=='audio'||!ready)return;
 const x=new Float32Array(e.data.samples);total+=x.length;
 if(x.length>=ring.length){ring.set(x.subarray(x.length-ring.length));filled=ring.length;}
 else{ring.copyWithin(0,x.length);ring.set(x,ring.length-x.length);filled=Math.min(ring.length,filled+x.length);}
 if(!busy&&filled>=16000&&total-last>=3200){busy=true;last=total;void predict(ring.slice(),total,version);}
};
