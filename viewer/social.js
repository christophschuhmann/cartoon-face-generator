'use strict';
let manifest;const $=id=>document.getElementById(id);
const families={playful:'Neckisch & spielerisch',welcoming:'Zugewandt & im Gespräch',hurt:'Verletzt & versöhnlich',theatrical:'Theatralisch & komödiantisch',goofy:'Albern & eigenwillig',subtle:'Feine soziale Signale'};
function draw(){
  $('cards').replaceChildren();const query=$('search').value.trim().toLocaleLowerCase('de');
  const rows=manifest.categories.filter(r=>(!$('family').value || r.family===$('family').value) && (!query || [r.label_de,r.slug,r.visual_cues_de].join(' ').toLocaleLowerCase('de').includes(query)));
  for(const row of rows){
    const variant=$('sampleChoice').value==='variation',prefix=variant?row.samples[0].pose.slice(0,-5):row.archetype;
    const card=document.createElement('article');card.className='card';card.dataset.slug=row.slug;
    const img=document.createElement('img');img.loading='lazy';img.alt=row.label_de;img.src='/social-assets/'+prefix+'.png';
    const title=document.createElement('h2');title.textContent=`${row.id}. ${row.label_de}`;
    const cue=document.createElement('p');cue.textContent=row.visual_cues_de;
    const nav=document.createElement('nav');
    for(const [text,href] of [['Im Editor öffnen','/?expression=social:'+row.slug],['SVG','/social-assets/'+prefix+'.svg'],['PNG','/social-assets/'+prefix+'.png'],['JSON','/social-assets/'+prefix+'.json']]){const a=document.createElement('a');a.textContent=text;a.href=href;nav.append(a);}
    card.append(img,title,cue,nav);$('cards').append(card);
  }
  $('galleryStatus').textContent=`${rows.length} / 60 Ausdrücke`;
}
fetch('/api/social_manifest').then(r=>{if(!r.ok)throw Error('Galerie konnte nicht geladen werden');return r.json();}).then(data=>{manifest=data;for(const [id,label] of Object.entries(families))$('family').add(new Option(label,id));draw();}).catch(e=>$('galleryStatus').textContent=e.message);
for(const id of ['family','sampleChoice'])$(id).onchange=draw;
$('search').oninput=()=>{if(manifest)draw();};
