export async function attachSystemGuide(){
 try{const r=await fetch('/static/system-guide-fragment.html');if(!r.ok)throw Error('Guide unavailable');
  const template=document.createElement('template');template.innerHTML=await r.text();
  document.querySelector('footer').before(template.content);
 }catch{/* The conversation must still work if its explanatory guide cannot load. */}
}
