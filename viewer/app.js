'use strict';
// This file handles editing and API calls only. All face geometry lives in Python.
const $ = id => document.getElementById(id);
let pose, base, svg, catalog, requestId = 0, drag = null, timer;
const specs = [
  ['left_eye_openness','Linkes Auge · Öffnung',0,1.5,1], ['right_eye_openness','Rechtes Auge · Öffnung',0,1.5,1],
  ['left_squint','Links · Zusammenkneifen',0,1,0], ['right_squint','Rechts · Zusammenkneifen',0,1,0],
  ['left_brow_raise','Linke Braue · Höhe',-.5,.5,0], ['right_brow_raise','Rechte Braue · Höhe',-.5,.5,0],
  ['left_brow_tilt','Linke Braue · Neigung',-1,1,0], ['right_brow_tilt','Rechte Braue · Neigung',-1,1,0],
  ['gaze_x','Blick · horizontal',-1,1,0], ['gaze_y','Blick · vertikal',-1,1,0],
  ['smile','Mund · Krümmung',-1,1,0], ['mouth_open','Mund · Öffnung',0,.8,0],
  ['left_moustache_curl','Linke Wangenlinie · Locke',-1,1,0], ['right_moustache_curl','Rechte Wangenlinie · Locke',-1,1,0],
  ['left_moustache_width','Linke Wangenlinie · Dicke',.6,1.3,1], ['right_moustache_width','Rechte Wangenlinie · Dicke',.6,1.3,1],
  ['left_pupil_scale','Linke Pupille · Größe',.5,1.25,1], ['right_pupil_scale','Rechte Pupille · Größe',.5,1.25,1]
];
async function api(url, body) {
  const r = await fetch(url, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
  if (!r.ok) {const e=await r.json(); throw Error(e.error || r.statusText);}
  return r.json();
}
function status(text) {$('status').textContent=text;}
function resetControls() {for (const [id,,, ,v] of specs) {$(id).value=v; $(id+'_out').textContent=v.toFixed(2);}}
function controls() {return Object.fromEntries(specs.filter(([id,,, ,v])=>+$(id).value!==v).map(([id])=>[id,+$(id).value]));}
function readSeed() {
  if ($('emotionSeed').value==='') return null;
  const seed=+$('emotionSeed').value;
  if (!Number.isSafeInteger(seed) || seed<0) throw Error('Seed muss eine nichtnegative ganze Zahl sein.');
  return seed;
}
function selectedTarget() {
  const value=$('emotion').value;
  if (!value.startsWith('emonet:') && !value.startsWith('social:')) throw Error('Für Mischungen eine Emotion oder einen sozialen Ausdruck auswählen.');
  return value;
}
function drawPoints() {
  const layer=$('landmarks'); layer.replaceChildren();
  layer.style.pointerEvents=$('showPoints').checked?'auto':'none';
  if (!$('showPoints').checked || !pose) return;
  for (const def of catalog.topology.keypoints) {
    const k=pose.keypoints[def.name];
    if (k.state==='absent' && !$('showAbsent').checked) continue;
    const [x,y]=k.xy, point=document.createElementNS('http://www.w3.org/2000/svg','circle');
    for (const [key,value] of Object.entries({cx:x*1450,cy:y*750,r:6,fill:k.state==='visible'?'#3977da':'#b6bfce',class:'point'})) point.setAttribute(key,value);
    point.dataset.name=def.name;
    const title=document.createElementNS('http://www.w3.org/2000/svg','title');
    title.textContent=`${def.id}: ${def.name} (${k.state})\n${def.meaning}\n${def.edit_effect||''}`;
    point.append(title);
    point.onpointerdown=e=>{e.preventDefault();drag=def.name;layer.setPointerCapture(e.pointerId);$('selected').textContent=title.textContent;};
    layer.append(point);
    if ($('showLabels').checked) {
      const label=document.createElementNS('http://www.w3.org/2000/svg','text');
      for (const [key,value] of Object.entries({x:x*1450+8,y:y*750-7,'font-size':10,fill:'#325a96'})) label.setAttribute(key,value);
      label.textContent=`${def.id} ${def.name}`;label.style.pointerEvents='none';layer.append(label);
    }
  }
}
function describeEmotion() {
  const expression=pose?.expression;
  if (expression?.catalog_id) {
    const profile=catalog.social.find(p=>p.slug===expression.slug);
    const parts=expression.mixture ? [...(pose.emotion?.mixture||[]),...expression.mixture].map(x=>`${x.slug} ${(x.weight*100).toFixed(0)} %`).join(' + ') : '';
    $('emotionMeaning').textContent=parts ? 'Ausdrucksmischung: '+parts+' · Übergang, keine validierte neue Kategorie' : `Sozialer Ausdruck: ${profile?.label_de||expression.label_de}. ${profile?.visual_cues_de||''}`;
    return;
  }
  const emotion=pose?.emotion;
  if (!emotion?.taxonomy_id) return $('emotionMeaning').textContent='';
  if (emotion.mixture) {
    const parts=emotion.mixture.map(x=>`${x.slug} ${(x.weight*100).toFixed(0)} %`).join(' + ');
    $('emotionMeaning').textContent='Mischziel: '+parts+' · '+(emotion.compatibility?.kind||'Übergang');
  } else {
    const profile=catalog.emonet.find(p=>p.slug===emotion.slug);
    $('emotionMeaning').textContent=`Ziel: ${profile?.label_de||emotion.label}. ${profile?.visual_cues_de||''}`;
  }
}
function syncDetails() {
  for (const e of $('optionalDetails').querySelectorAll('input')) e.checked=pose.rig[e.dataset.component].opacity>.5;
  for (const e of $('variants').querySelectorAll('select')) e.value=pose.variants[e.dataset.name];
  for (const [id,c] of [['tongue','tongue'],['crease','tongue_crease'],['chin','chin']]) $(id).checked=pose.rig[c].opacity>.5;
  for (const side of ['left','right']) {const slider=$(side+'_underBlend');if(slider){slider.value=pose.rig[side+'_hatching'].foldness??(pose.rig[side+'_hatching'].opacity>.5?1:0);$(side+'_underBlendOut').textContent=(+slider.value).toFixed(2);}}
  describeEmotion();
}
async function render(source=base,withControls=true,manualEdit=false) {
  const id=++requestId;
  try {
    const r=await api('/api/render',{pose:source,controls:withControls?controls():{},manual_edit:manualEdit});
    if (id!==requestId) return;
    pose=r.pose;svg=r.svg;$('drawing').innerHTML=svg;drawPoints();syncDetails();
    status('SVG aktualisiert · vollständiger Zustand exportierbar');
  } catch (e) {status(e.message);}
}
async function loadReference(name) {
  try {base=await api('/api/pose/'+name);resetControls();$('overlay').src='/reference/'+name+'.png';await render(base,false);}
  catch (e) {status(e.message);}
}
function debounceRender() {clearTimeout(timer);timer=setTimeout(()=>render(),90);}
function download(data,name,type) {
  const u=URL.createObjectURL(new Blob([data],{type}));const a=document.createElement('a');
  a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),2000);
}
async function loadEmotion(variation=false) {
  try {
    const value=$('emotion').value;
    const procedural=value.startsWith('emonet:') || value.startsWith('social:');
    const body=procedural ? {taxonomy:value.split(':')[0],name:value.slice(7),seed:variation?readSeed():null,variation:.85} : {name:value};
    const r=await api('/api/emotion',body);base=r.pose;resetControls();await render(base,false);
    if (variation && body.seed!==null && procedural) $('emotionSeed').value=body.seed+1;
  } catch (e) {status(e.message);}
}
async function loadMixture() {
  try {const r=await api('/api/mix',{a:selectedTarget(),b:$('mixEmotion').value,weight:+$('mixWeight').value});base=r.pose;resetControls();await render(base,false);}
  catch (e) {status(e.message);}
}
async function init() {
  catalog=await api('/api/catalog');
  for (const n of catalog.references) $('reference').add(new Option(n,n));
  const emonet=document.createElement('optgroup');emonet.label='EmoNet-Face · 40 Kategorien';
  for (const p of catalog.emonet) {emonet.append(new Option(`${p.id} · ${p.label_de}`,'emonet:'+p.slug));$('mixEmotion').add(new Option(p.label_de,p.slug));}
  $('emotion').append(emonet);$('mixEmotion').value='teasing';
  const social=document.createElement('optgroup');social.label='Soziale & clowneske Ausdrücke · 60';
  const socialMix=document.createElement('optgroup');socialMix.label=social.label;
  for (const p of catalog.social) {social.append(new Option(`${p.id} · ${p.label_de}`,'social:'+p.slug));socialMix.append(new Option(p.label_de,'social:'+p.slug));}
  $('emotion').append(social);$('mixEmotion').append(socialMix);
  const legacy=document.createElement('optgroup');legacy.label='Bisherige Referenz-Ausdrücke';
  for (const n of catalog.emotions) legacy.append(new Option(n,n));$('emotion').append(legacy);
  for (const [id,label,min,max,value] of specs) {
    const row=document.createElement('label');row.className='control';
    const text=document.createElement('span');text.textContent=label;const out=document.createElement('output');out.id=id+'_out';out.textContent=value.toFixed(2);
    const input=document.createElement('input');Object.assign(input,{id,type:'range',min,max,step:.02,value});
    input.oninput=()=>{out.textContent=(+input.value).toFixed(2);debounceRender();};row.append(text,out,input);$('controls').append(row);
  }
  for (const side of ['left','right']) for (const [suffix,opts] of [['under_eye',['none','continuous','hatching','mixed']],['highlight',['round','heart']]]) {
    const name=side+'_'+suffix,label=document.createElement('label');label.className='variant';
    label.textContent=(side==='left'?'Links':'Rechts')+(suffix==='under_eye'?' · Unterauge':' · Reflex');
    const select=document.createElement('select');select.dataset.name=name;for (const v of opts) select.add(new Option(v,v));
    select.onchange=async()=>{const r=await api('/api/render',{pose,variants:{[name]:select.value}});base=r.pose;resetControls();await render(base,false);};
    label.append(select);$('variants').append(label);
  }
  for (const side of ['left','right']) {
    const label=document.createElement('label');label.className='control';
    const text=document.createElement('span');text.textContent=(side==='left'?'Links':'Rechts')+' · Unterauge: Kurve → Falten';
    const input=document.createElement('input');Object.assign(input,{id:side+'_underBlend',type:'range',min:0,max:1,step:.01,value:0});
    const out=document.createElement('output');out.id=side+'_underBlendOut';out.textContent='0.00';
    input.oninput=()=>{out.textContent=(+input.value).toFixed(2);clearTimeout(timer);timer=setTimeout(async()=>{try{const r=await api('/api/render',{pose,controls:{[side+'_under_eye_blend']:+input.value}});base=r.pose;resetControls();await render(base,false);}catch(e){status(e.message);}},60);};
    label.append(text,out,input);$('variants').append(label);
  }
  for (const side of ['left','right']) for (const [suffix,text] of [['lid_accent_inner','Innerer Lid-Akzent'],['lid_accent_outer','Äußerer Lid-Akzent'],['brow_accent','Brauen-Akzent'],['lash','Wimper'],['secondary_highlight','Zweiter Reflex']]) {
    const c=side+'_'+suffix,label=document.createElement('label');label.className='variant';
    const input=document.createElement('input');input.type='checkbox';input.dataset.component=c;
    label.append(input,document.createTextNode((side==='left'?'Links':'Rechts')+' · '+text));
    input.onchange=()=>{base=structuredClone(pose);base.rig[c].opacity=input.checked?1:0;resetControls();render(base,false,true);};$('optionalDetails').append(label);
  }
  $('reference').onchange=()=>loadReference($('reference').value);$('reset').onclick=()=>loadReference($('reference').value);
  $('emotionLoad').onclick=()=>loadEmotion();$('variationLoad').onclick=()=>loadEmotion(true);$('mixLoad').onclick=loadMixture;
  $('mixWeight').oninput=()=>{$('mixWeightOut').textContent=(+$('mixWeight').value).toFixed(2);clearTimeout(timer);timer=setTimeout(loadMixture,100);};
  for (const id of ['showPoints','showLabels','showAbsent']) $(id).onchange=drawPoints;
  $('overlayOpacity').oninput=()=>{$('overlay').hidden=+$('overlayOpacity').value===0;$('overlay').style.opacity=$('overlayOpacity').value;};
  for (const [id,c] of [['tongue','tongue'],['crease','tongue_crease'],['chin','chin']]) $(id).onchange=()=>{base=structuredClone(pose);base.rig[c].opacity=$(id).checked?1:0;resetControls();render(base,false,true);};
  $('jsonExport').onclick=()=>download(JSON.stringify(pose,null,2)+'\n','face.json','application/json');
  $('svgExport').onclick=()=>download(svg,'face.svg','image/svg+xml');
  $('pngExport').onclick=async()=>{const r=await fetch('/api/png',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pose})});if (!r.ok) return status('PNG-Export fehlgeschlagen');download(await r.arrayBuffer(),'face.png','image/png');};
  $('jsonImport').onchange=async()=>{try {base=JSON.parse(await $('jsonImport').files[0].text());resetControls();await render(base,false);} catch(e) {status(e.message);}};
  $('landmarks').onpointermove=e=>{
    if (!drag) return;const rect=$('landmarks').getBoundingClientRect();
    pose.keypoints[drag].xy=[Math.min(.999,Math.max(.001,(e.clientX-rect.left)/rect.width)),Math.min(.999,Math.max(.001,(e.clientY-rect.top)/rect.height))];
    base=structuredClone(pose);resetControls();drawPoints();clearTimeout(timer);timer=setTimeout(()=>render(base,false,true),35);
  };
  $('landmarks').onpointerup=()=>{if (drag) {drag=null;render(base,false,true);}};
  $('landmarks').onpointercancel=()=>{drag=null;};
  await loadReference(catalog.references[0]);
  const target=new URLSearchParams(location.search).get('expression');
  if (target && [...$('emotion').options].some(o=>o.value===target)) {$('emotion').value=target;await loadEmotion();}
}
init().catch(e=>status(e.message));
