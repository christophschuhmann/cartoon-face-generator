// Optional microphone preprocessing. Selection persists; voice audio never does.
export class InputIsolationControls {
 constructor(client) {
  this.client=client;this.buddy=false;this.select=document.getElementById('input-isolation-model');
  this.status=document.getElementById('input-isolation-status');this.last=null;
  this.desired='off';try {const v=localStorage.getItem('robby.inputIsolation');if(['off','voxlock','scicom'].includes(v))this.desired=v;}catch{}
  this.select.value=this.desired;
  this.select.onchange=()=>this.choose(this.select.value);
  document.getElementById('input-isolation-learn').onclick=async()=>{
   try {await client.start(true);client.stopAudio();client.send('interrupt');
    this.status.textContent='Speak alone for four seconds…';client.send('isolation:'+JSON.stringify({action:'learn'}));
   }catch(e){this.status.textContent=e.message;}
  };
  document.getElementById('input-isolation-clear').onclick=async()=>{
   try {await client.start(false);client.send('isolation:'+JSON.stringify({action:'clear'}));}catch(e){this.status.textContent=e.message;}
  };
 }
 setBuddyMode(enabled){
  this.buddy=enabled;
  this.select.disabled=enabled;
  this.select.value=enabled?'off':this.desired;
  document.getElementById('input-isolation-learn').disabled=enabled;
  if(enabled)this.status.textContent='OFF in Buddy mode. Go Buddy sends the original microphone recording. Your normal-mode filter is saved.';
  else if(this.last&&!this.last.paused_for_buddy)this.message(this.last);
  else this.status.textContent='Normal microphone mode · '+this.desired;
 }
 async choose(model) {
  this.desired=model;this.select.value=model;
  try{localStorage.setItem('robby.inputIsolation',model);}catch{}
  this.status.textContent=model==='off'?'Returning to original microphone…':'Loading on GPU 1; microphone stays unfiltered until ready…';
  try {await this.client.start(false);this.client.send('isolation:'+JSON.stringify({model}));}
  catch(e){this.status.textContent=e.message;}
 }
 message(m) {
  if(m.type==='ready') {
   const socket=this.client.ws;
   socket?.addEventListener('close',()=>{
    if(this.client.ws && this.client.ws!==socket)return;
    this.last=null;this.status.textContent='DISCONNECTED · filter released. Your voice reference is cleared; the selected option applies on reconnect.';
    document.getElementById('input-isolation-learn').disabled=this.buddy;
   },{once:true});
   if(m.input_isolation)this.message(m.input_isolation);
   if(this.desired!==(m.input_isolation?.preferred||'off'))this.client.send('isolation:'+JSON.stringify({model:this.desired}));
  }
  if(m.type!=='input_isolation')return;
  this.last=m;
  if(this.buddy){this.setBuddyMode(true);return;}
  const mode=m.active?`ACTIVE · ${m.selected==='voxlock'?'VoxLock':'Scicom Agent'} · CUDA ${m.gpu} · 40-ms chunks`:
   m.phase==='off'?'OFF · original microphone':`${m.phase.replaceAll('_',' ').toUpperCase()} · original microphone`;
  const ref=m.reference_s?` · reference ${m.reference_s.toFixed(1)} s (${m.reference_name||'current voice'})`:'';
  const perf=m.active&&m.compute_ms!=null?` · last chunk ${m.compute_ms.toFixed(1)} ms compute · ${m.held_audio_ms.toFixed(0)} ms buffered · ${m.chunks} chunks`:'';
  const known=(m.known_voices||[]).map(v=>`${v.name}: ${v.ready?'ready':v.seconds.toFixed(1)+' / 4 s'}`).join(' · ');
  const recovery=m.raw_wake_recovery?.error?' · Wake check: '+m.raw_wake_recovery.error:'';
  this.status.textContent=mode+ref+perf+'. '+m.reason+(m.phase==='capturing'?` (${m.capture_s.toFixed(1)} / 4.0 s)`:'')+(known?' Registered voices · '+known:'')+recovery;
  document.getElementById('input-isolation-learn').disabled=m.phase==='capturing';
 }
}
