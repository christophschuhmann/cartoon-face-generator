'use strict';
// Optional human review. No model-generated recognition score is substituted.
let manifest,rows,reviews={};const cards=document.getElementById('cards');
function updateStatus(){const prefix=document.getElementById('sampleChoice').value+':';document.getElementById('galleryStatus').textContent=`${Object.entries(reviews).filter(([key,r])=>key.startsWith(prefix)&&r.recognized_slug).length} / ${rows.length} bewertet (${Object.values(reviews).filter(r=>r.recognized_slug).length} insgesamt)`;}
function draw(){cards.replaceChildren();const variant=document.getElementById('sampleChoice').value==='variation';
for(const row of rows){const key=(variant?'variation':'archetype')+':'+row.slug;const card=document.createElement('article');card.className='card';
const image=document.createElement('img');image.loading='lazy';image.alt='Cartoon-Gesicht zur Bewertung';image.src='/emotion-assets/'+(variant?row.samples[0].png:row.archetype+'.png');
const name=document.createElement('h2');name.className='target';name.textContent=`${row.id}. ${row.label_de}`;
const cue=document.createElement('p');cue.className='target';cue.textContent=row.label;
const select=document.createElement('select');select.setAttribute('aria-label','Erkannte Emotion');select.add(new Option('Dein Eindruck …',''));select.add(new Option('Unklar / keiner dieser Ausdrücke','unclear'));for(const category of manifest.categories)select.add(new Option(category.label_de,category.slug));
select.value=reviews[key]?.recognized_slug||'';select.onchange=()=>{reviews[key]={...reviews[key],sample_id:key,target_slug:row.slug,recognized_slug:select.value,confidence:reviews[key]?.confidence||3,target_name_hidden_when_rated:document.getElementById('hideTargets').checked};updateStatus();};
const rating=document.createElement('label');rating.className='rating';rating.textContent='Sicherheit';const confidence=document.createElement('select');for(let i=1;i<=5;i++)confidence.add(new Option(String(i),String(i)));confidence.value=reviews[key]?.confidence||3;confidence.onchange=()=>{reviews[key]={...reviews[key],sample_id:key,target_slug:row.slug,recognized_slug:select.value,confidence:+confidence.value,target_name_hidden_when_rated:document.getElementById('hideTargets').checked};updateStatus();};rating.append(confidence);
card.append(image,name,cue,select,rating);cards.append(card);}updateStatus();}
fetch('/api/emotion_manifest').then(r=>r.json()).then(data=>{manifest=data;rows=[...data.categories];draw();});
document.getElementById('hideTargets').onchange=e=>cards.classList.toggle('hide-labels',e.target.checked);
document.getElementById('sampleChoice').onchange=draw;
document.getElementById('shuffleCards').onclick=()=>{for(let i=rows.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[rows[i],rows[j]]=[rows[j],rows[i]];}draw();};
document.getElementById('exportReviews').onclick=()=>{const data={schema_version:'1.0',taxonomy_id:manifest.taxonomy_id,method:'manual viewer judgments; target names optionally hidden',target_names_hidden:document.getElementById('hideTargets').checked,reviews:Object.values(reviews).filter(r=>r.recognized_slug)};const link=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));link.href=url;link.download='emotion_reviews.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
