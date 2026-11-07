const style=document.createElement('style');style.textContent='#tts-model-controls{display:flex;flex-wrap:wrap;align-items:center;gap:12px;max-width:1200px;margin:4px auto 14px;text-align:left;font-size:13px}#tts-model-controls label{display:flex;align-items:center;gap:8px}#tts-model-controls select{max-width:100%;padding:7px;border:1px solid var(--line);border-radius:8px;background:white}#tts-model-status{flex:1;margin:0;font-size:12px;color:var(--muted)}';document.head.append(style);
// Model choice contains no user audio, credentials or voiceprints.
const select=document.getElementById('tts-model'),status=document.getElementById('tts-model-status');
let pending=false,restored=false;
async function refresh(){
 try{
  const response=await fetch('/api/tts/models',{cache:'no-store'});
  if(!response.ok)throw Error('Voice model status unavailable');
  const data=await response.json();select.disabled=Boolean(data.loading)||pending;
  select.value=data.loading||data.selected;
  status.textContent=data.loading?'Loading '+data.loading+' and warming streaming kernels… You can keep this page open.':data.error||
   (select.selectedOptions[0]?.textContent+' ready · streaming'+(data.switch_seconds?' · last swap '+data.switch_seconds+' s':''));
  if(!restored&&!data.loading){
   restored=true;const saved=localStorage.getItem('robby.ttsModel');
   if(saved&&['small_rl','large17'].includes(saved)&&saved!==data.selected)await change(saved);
  }
 }catch(error){status.textContent=error.message;}
}
async function change(model){
 pending=true;select.disabled=true;status.textContent='Requesting model switch…';
 try{
  const response=await fetch('/api/tts/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model})});
  if(!response.ok)throw Error(await response.text());
  localStorage.setItem('robby.ttsModel',model);
 }catch(error){status.textContent=error.message;}
 finally{pending=false;}
}
select.addEventListener('change',()=>change(select.value));
await refresh();setInterval(refresh,2000);
