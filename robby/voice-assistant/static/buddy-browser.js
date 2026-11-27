/* Browser-local Buddy wake word gating. Microphone audio stays here until Go. */
export class BrowserBuddy {
 constructor(client,onStatus){this.client=client;this.onStatus=onStatus;this.enabled=false;this.ready=false;this.state='waiting';this.blocks=[];this.ring=[];this.count=0;this.last=-1e9;this.lastProbe=0;this.pending=false;this.worker=null;this.timer=null;this.history=[];}
 setEnabled(value){
  this.enabled=!!value;this.reset();
  if(!this.enabled){this.worker?.terminate();this.worker=null;this.ready=false;return;}
  if(this.worker)return;
  this.onStatus('Loading local wakeword models…','loading');
  const w=this.worker=new Worker('/static/buddy-worker.js?v=buddy-admit-1');
  w.onmessage=e=>{const m=e.data;
   if(m.type==='ready'){this.ready=true;this.count=0;this.ring=[];this.onStatus('Listening locally: say “Hey Buddy”.','waiting');this.sync();}
   if(m.type==='error'){this.pending=false;this.ready=false;this.onStatus('Wakeword model failed: '+m.message+'. Turn Buddy mode off or reload.','error');}
   if(m.type==='skipped')this.pending=false;
   if(m.type==='scores'){this.pending=false;this.scores(m);}
  };
  w.onerror=e=>{this.ready=false;this.onStatus('Wakeword worker failed: '+e.message,'error');};
  w.postMessage({type:'init'});
 }
 sync(){if(this.enabled&&this.ready&&this.client.ws?.readyState===1)this.client.send('buddy:browser:ready');}
 reset(){clearTimeout(this.timer);this.state='waiting';this.blocks=[];this.ring=[];this.count=0;this.last=-1e9;this.lastProbe=0;this.pending=false;this.worker?.postMessage({type:'reset'});}
 audio(x){
  if(!this.enabled)return false;
  const start=this.count;this.count+=x.length;const copy=x.slice();this.ring.push({start,x:copy});
  while(this.ring.length&&this.ring[0].start+this.ring[0].x.length<this.count-48000)this.ring.shift();
  if(this.state==='recording'||this.state==='processing'){
   this.blocks.push(copy);
   if(this.blocks.reduce((n,a)=>n+a.length,0)>60*16000){this.state='waiting';this.blocks=[];this.client.send('buddy:browser:cancel');this.onStatus('Recording reached 60 seconds; say Hey Buddy again.','waiting');}
  }
  // Only one in-flight inference. While it runs, update the ring locally;
  // the next job uses the newest window rather than queued stale frames.
  const probeEnd=Math.floor(this.count/2560)*2560;
  if(this.worker&&this.ready&&!this.pending&&probeEnd>=16000&&probeEnd>this.lastProbe){
   const window=new Float32Array(32000),from=Math.max(0,probeEnd-32000);
   for(const part of this.ring){
    const start=Math.max(from,part.start),end=Math.min(probeEnd,part.start+part.x.length);
    if(end>start)window.set(part.x.subarray(start-part.start,end-part.start),32000-(probeEnd-start));
   }
   this.pending=true;this.lastProbe=probeEnd;this.worker.postMessage({type:'window',samples:window.buffer,end:probeEnd},[window.buffer]);
  }
  return true;
 }
 scores(m){
  const {hey,go,stop}=m.scores;
  this.history.push({state:this.state,end:m.end,scores:m.scores,ms:m.ms});if(this.history.length>180)this.history.shift();
  if(!this.enabled||!this.ready||this.state==='processing'||m.end-this.last<12000)return;
  let event=null;
  // Both Medium heads can score strongly on Stop. Give a clear Stop
  // priority and allow Go only with weak Stop evidence.
  if((this.state==='recording'||this.client.sources.length)&&stop>=.64)event='stop';
  else if(this.state==='waiting'&&hey>=.18&&hey>Math.max(go,stop)+.07)event='hey';
  else if(this.state==='recording'&&go>=.55&&stop<.30&&go>hey+.18)event='go';
  if(!event)return;this.last=m.end;
  if(event==='hey'){
   const from=Math.max(0,m.end-12800);this.blocks=this.ring.filter(z=>z.start+z.x.length>from).map(z=>z.x.slice(Math.max(0,from-z.start)));
   this.state='recording';this.onStatus('🔴 Hey Buddy detected. Speak, then say “Go Buddy” to send or “Stop Buddy” to discard.','recording');
  }else if(event==='stop'){
   this.state='waiting';this.blocks=[];this.client.send('buddy:browser:cancel');
   if(this.client.sources.length){this.client.stopAudio();this.client.send('interrupt');}
   this.onStatus('Stopped. Say “Hey Buddy” to begin again.','waiting');
  }else{
   this.state='processing';this.onStatus('Go Buddy detected. Preparing your recording…','processing');
   // The compact Go head can fire before the second syllable of Buddy.
   this.timer=setTimeout(()=>this.upload(),800);
  }
 }
 upload(){
  if(!this.enabled||this.state!=='processing')return;
  if(this.client.ws?.readyState!==1){this.state='recording';this.onStatus('Connection lost; recording kept locally. Reconnect and say Go Buddy.','error');return;}
  this.client.send('buddy:browser:begin');
  for(const x of this.blocks){const b=new ArrayBuffer(8+x.length*2),dv=new DataView(b),pcm=new Int16Array(b,8);dv.setInt32(0,0,true);dv.setInt32(4,-1,true);for(let i=0;i<x.length;i++)pcm[i]=Math.max(-32768,Math.min(32767,Math.round(x[i]*32767)));this.client.ws.send(b);this.client.sentMicSamples=(this.client.sentMicSamples||0)+x.length;}
  this.client.send('buddy:browser:go');this.onStatus('Checking the request…','processing');
 }
 message(m){
  if(!this.enabled||m.type!=='buddy_wake')return;
  if(m.state==='recording'&&m.command_hint){this.state='recording';this.onStatus('🔴 Still recording. Heard “'+m.command_hint+'”. Please say “Go Buddy” again.','recording');}
  else if(m.state==='recording'&&m.reason?.startsWith('Could not')){this.state='recording';this.onStatus(m.reason+'; repeat Go Buddy.','recording');}
  else if(m.state==='waiting'&&m.reason?.startsWith('Stop Buddy confirmed')){this.blocks=[];this.state='waiting';this.onStatus('Stopped. Say “Hey Buddy” to begin again.','waiting');}
  else if(m.state==='waiting'&&m.reason?.startsWith('Request submitted')){this.blocks=[];this.state='waiting';this.onStatus('Request transcribed. Say “Hey Buddy” for another request.','waiting');}
 }
}
