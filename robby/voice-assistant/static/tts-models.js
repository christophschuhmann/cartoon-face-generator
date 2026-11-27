const style=document.createElement('style');style.textContent='#tts-model-controls{display:flex;flex-wrap:wrap;align-items:center;gap:12px;max-width:1200px;margin:4px auto 14px;text-align:left;font-size:13px}#tts-model-controls label{display:flex;align-items:center;gap:8px}#tts-model-controls select{max-width:100%;padding:7px;border:1px solid var(--line);border-radius:8px;background:white}#tts-model-status{flex:1;margin:0;font-size:12px;color:var(--muted)}';document.head.append(style);
// Model choice contains no user audio, credentials or voiceprints.
const select=document.getElementById('tts-model'),status=document.getElementById('tts-model-status');
let pending=false,restored=false,requested=null,lastFailure=null;
async function refresh(){
 try{
  const response=await fetch('/api/tts/models',{cache:'no-store'});
  if(!response.ok)throw Error('Voice model status unavailable');
  const data=await response.json();select.disabled=Boolean(data.loading)||pending;
  select.value=data.loading||data.selected;
  if(requested&&!data.loading&&!pending){
   if(data.selected===requested&&!data.error){
    localStorage.setItem('robby.ttsModel',requested);requested=null;lastFailure=null;
   }else if(data.failed_model===requested){
    localStorage.setItem('robby.ttsModel',data.selected);requested=null;lastFailure=data.error;
   }
  }
  const activeLabel=select.selectedOptions[0]?.textContent||data.selected;
  status.textContent=data.loading?'Loading '+activeLabel+' and warming streaming kernels…':
   activeLabel+' selected · streaming'+(lastFailure?' · Last switch: '+lastFailure:'');
  if(!restored&&!data.loading){
   restored=true;const saved=localStorage.getItem('robby.ttsModel');
   if(saved&&['small_rl','large17'].includes(saved)&&saved!==data.selected){
    if(saved===data.failed_model){localStorage.setItem('robby.ttsModel',data.selected);lastFailure=data.error;}
    else await change(saved);
   }
  }
 }catch(error){status.textContent=error.message;}
}
async function change(model){
 pending=true;requested=model;lastFailure=null;select.disabled=true;status.textContent='Requesting model switch…';
 try{
  const response=await fetch('/api/tts/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model})});
  if(!response.ok)throw Error(await response.text());
 }catch(error){requested=null;lastFailure=error.message;status.textContent=lastFailure;}
 finally{pending=false;}
}
select.addEventListener('change',()=>change(select.value));
await refresh();setInterval(refresh,2000);
