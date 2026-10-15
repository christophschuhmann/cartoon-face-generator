import {AudioPerformance} from './audio-player.mjs';
import {AudioViewer} from './audio-viewer.mjs';
const $=id=>document.getElementById(id);

export function installAudioMode({motion,stop,waitProcessing,post,show}) {
  let modeToken=0,audioToken=0,audioUrl=null,audioData=null,cancelPending=Promise.resolve(),ready=false,busy=false,switching=false;
  let preferences={};try{preferences=JSON.parse(localStorage.getItem('audio-preferences')||'{}');}catch{}
  if(['base','medium'].includes(preferences.model))$('audio-model').value=preferences.model;
  $('audio-eye-contact').checked=preferences.eyeContact!==false;
  $('audio-head-follow').checked=preferences.headFollow===true;
  $('audio-head-follow').disabled=!$('audio-eye-contact').checked;
  $('audio-dynamics').value=String(preferences.dynamics??100);$('audio-transition').value=String(preferences.transition??450);
  const savePreferences=()=>{try{localStorage.setItem('audio-preferences',JSON.stringify({model:$('audio-model').value,eyeContact:$('audio-eye-contact').checked,headFollow:$('audio-head-follow').checked,dynamics:Number($('audio-dynamics').value),transition:Number($('audio-transition').value)}));}catch{}};
  function updateAnalyze(){ $('audio-analyze').disabled=!ready || busy || switching || !$('audio-file').files[0]; }
  async function checkReady(){
    try{
      const response=await fetch('/api/audio/ready');if(!response.ok)throw Error('Status nicht verfügbar');
      const status=await response.json(),wasReady=ready;ready=Boolean(status.variants?.[$('audio-model').value] ?? status.ready);
      if(!busy && !audioData && (!ready || !wasReady))$('audio-status').textContent=ready?status.message:'Das gewählte Audiomodell wird eingerichtet und geprüft. Base steht als schnellere Option zur Verfügung.';
    }catch{ready=false;}
    updateAnalyze();
  }
  checkReady();
  const readinessTimer=setInterval(()=>{if(!ready && !busy)checkReady();},3000);
  const playback=$('audio-playback');
  const styleLabels={ranting:'Ranting / schimpfend',whispering:'Flüsternd',dramatic:'Dramatisch',playful:'Verspielt',monotone:'Monoton',assertive:'Bestimmt',conversational:'Gesprächig',narrative:'Erzählend',tension:'Anspannung',emphasis:'Betonung',attack:'Harter Stimmeinsatz',tempo:'Tempo'};
  const performance=new AudioPerformance($('avatar'),playback,(segment)=>{
    $('audio-emotion').textContent=segment?.label || 'Ruhepose';
    $('audio-emotion').title=segment?`Mimik: ${segment.label}. Höchster Modellwert: ${segment.model_label || segment.label}.` : '';
    $('audio-arousal').textContent=segment?`Aktivierung ${Math.round(segment.arousal*100)} %`:'Aktivierung –';
    $('audio-valence').textContent=segment?`Valenz ${segment.valence>=0?'+':''}${segment.valence.toFixed(2)}`:'Valenz –';
    const styles=Object.entries(segment?.styles||{}).sort((a,b)=>b[1].z-a[1].z);
    $('audio-style').textContent=styles.filter(([,v])=>v.z>=.5).slice(0,2).map(([k,v])=>`${styleLabels[k]||k} · z ${v.z.toFixed(2)}`).join(' / ') || 'Kein deutlich hervorgehobener Sprechstil';
    const scores=Object.entries(segment?.scores_z||segment?.scores_raw||{}).sort((a,b)=>b[1]-a[1]);
    const acting=segment?.affect?`Mimik: ${segment.label} · höchster Modellwert: ${segment.model_label}\nAusdrucksgewicht Ärger/Anspannung: ${Math.round(segment.affect.aggression*100)} % (Animationsgewicht)\n\n`:'';
    $('audio-scores').textContent=acting+(segment?.normalization||'')+'\n'+scores.map(([k,v])=>`${k.replace('emo_','')}: ${segment?.scores_z?'z ':''}${v.toFixed(2)} · roh ${segment.scores_raw[k].toFixed(2)}`).join('\n')+'\n\n'+styles.map(([k,v])=>`${styleLabels[k]||k}: z ${v.z.toFixed(2)} · roh ${v.raw.toFixed(2)}`).join('\n');
  });
  const viewer=new AudioViewer(position=>performance.setViewer(position),status=>$('audio-viewer-status').textContent=status);
  const headSetting=()=>{performance.headFollow=$('audio-head-follow').checked && $('audio-eye-contact').checked;savePreferences();};
  $('audio-head-follow').onchange=headSetting;headSetting();
  const settings=()=>{performance.dynamics=Number($('audio-dynamics').value)/100;performance.transition=Number($('audio-transition').value)/1000;
    $('audio-dynamics-value').value=$('audio-dynamics').value+' %';$('audio-transition-value').value=$('audio-transition').value+' ms';
    if(audioData)performance.paint(playback.currentTime);savePreferences();};
  $('audio-dynamics').oninput=settings;$('audio-transition').oninput=settings;settings();
  $('audio-model').onchange=()=>{checkReady();savePreferences();
    if(audioData)$('audio-status').textContent='Modell geändert. Audio erneut analysieren, um die neuen Emotionswerte zu verwenden.';};
  $('audio-eye-contact').onchange=()=>{$('audio-head-follow').disabled=!$('audio-eye-contact').checked;headSetting();if($('audio-eye-contact').checked && !playback.paused)viewer.start();else{viewer.stop();performance.clearViewer();$('audio-viewer-status').textContent='Blickkontakt aus · Webcam freigegeben.';}};
  playback.addEventListener('play',()=>{if($('audio-eye-contact').checked && document.body.dataset.mode==='audio')viewer.start();});
  for(const event of ['pause','ended'])playback.addEventListener(event,()=>{viewer.stop();$('audio-viewer-status').textContent='Webcam freigegeben · startet beim nächsten Abspielen.';});
  document.querySelector('.layout').append($('audio-panel'));
  async function setMode(next) {
    switching=true;
    viewer.stop();performance.clearViewer();
    const token=++modeToken;document.body.dataset.mode=next;stop();playback.pause();performance.stop();motion.suspended=next==='audio';
    $('audio-panel').hidden=next!=='audio';$('preview-card').hidden=next==='audio';
    if(next==='audio')document.body.classList.remove('avatar-only');
    audioToken++;
    busy=false;updateAnalyze();$('audio-model').disabled=false;$('audio-cancel').disabled=true;
    await post('/api/audio/cancel').catch(()=>{});
    await waitProcessing().catch(()=>{});
    if(token!==modeToken)return;
    await post('/api/mode',JSON.stringify({mode:next}),{'Content-Type':'application/json'});
    if(token!==modeToken)return;
    switching=false;updateAnalyze();
    $('audio-panel').hidden=next!=='audio';$('preview-card').hidden=next==='audio';
    $('start').parentElement.hidden=next==='audio';$('speech-options').hidden=next==='audio';
    document.querySelector('.expression-panel').hidden=next==='audio';document.querySelector('.tuning').hidden=next==='audio';
    document.querySelector('.details').hidden=next==='audio';
    for(const kind of ['webcam','audio']){$('mode-'+kind).classList.toggle('primary',kind===next);$('mode-'+kind).setAttribute('aria-pressed',String(kind===next));}
    if(next==='audio'){
      show('Audio-Modus bereit · Webcam startet bei Wiedergabe für den Blickkontakt.');$('gestures').textContent='Die Stimme steuert Mimik und Bewegung.';
      if(audioData)performance.load(audioData);
    }else{const config=await (await fetch('/api/config')).json();motion.setSvg(config.svg,true);show('Webcam-Modus bereit.');}
  }
  for(const kind of ['webcam','audio'])$('mode-'+kind).onclick=()=>setMode(kind).catch(e=>show(e.message));
  $('audio-file').onchange=()=>{
    const file=$('audio-file').files[0];playback.pause();performance.stop();audioData=null;audioToken++;
    cancelPending=post('/api/audio/cancel').catch(()=>{});busy=false;updateAnalyze();$('audio-model').disabled=false;$('audio-cancel').disabled=true;
    if(audioUrl)URL.revokeObjectURL(audioUrl);
    audioUrl=file?URL.createObjectURL(file):null;playback.src=audioUrl || '';playback.hidden=true;
    $('audio-transcript').replaceChildren();$('audio-words').textContent='';$('audio-progress').value=0;
    $('audio-status').textContent=file?`${file.name} · ${ready?'bereit zur Analyse':'Audioanalyse wird noch eingerichtet und geprüft'}`:'Noch keine Datei ausgewählt.';
  };
  $('audio-analyze').onclick=async()=>{
    const file=$('audio-file').files[0];if(!file || !ready || busy || switching)return;
    if(file.size>100*1024*1024){$('audio-status').textContent='Bitte eine Datei unter 100 MB wählen.';return;}
    const token=++audioToken,started=Date.now();playback.pause();performance.stop();playback.hidden=true;
    busy=true;viewer.stop();updateAnalyze();$('audio-model').disabled=true;$('audio-cancel').disabled=false;
    try{
      await cancelPending;if(token!==audioToken)return;
      const res=await fetch('/api/audio/analyze?variant='+encodeURIComponent($('audio-model').value),{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});
      const job=await res.json();if(!res.ok)throw Error(job.error);
      while(token===audioToken){
        const response=await fetch('/api/audio/status/'+job.id),status=await response.json();
        if(token!==audioToken)return;
        if(!response.ok)throw Error(status.error);
        $('audio-progress').value=status.progress || 0;
        const labels={decode:'Audiodatei lesen',asr:'Sprache und Wortzeitstempel erkennen',emotions:'Emotionen pro Abschnitt erkennen',animation:'Cartoon-Bewegungen vorbereiten'};
        $('audio-status').textContent=(labels[status.stage] || status.stage)+(status.segment?` · ${status.segment}/${status.segments}`:'')+` · ${Math.round((Date.now()-started)/1000)} s`;
        if(status.state==='error')throw Error(status.error);
        if(status.state==='cancelled')return;
        if(status.state==='ready')break;
        await new Promise(resolve=>setTimeout(resolve,600));
      }
      if(token!==audioToken)return;
      const result=await fetch('/api/audio/result/'+job.id);if(!result.ok)throw Error('Analyse konnte nicht geladen werden.');
      const data=await result.json();if(token!==audioToken)return;audioData=data;
      playback.currentTime=0;playback.hidden=false;performance.load(data);
      $('audio-status').textContent=data.words.length?`Bereit · ${data.words.length} Wörter · ${data.segments.length} Emotionsabschnitte · Analyse ${data.analysis_seconds.toFixed(1)} s. Jetzt abspielen.`:'Keine Sprache erkannt. Das Audio kann mit ruhendem Avatar abgespielt werden.';
      $('audio-transcript').replaceChildren(...data.segments.map(segment=>{
        const button=document.createElement('button');button.textContent=`${segment.start.toFixed(2)} s · ${segment.text} · ${segment.label}`;
        button.style.margin='4px';button.onclick=()=>{playback.currentTime=segment.start;};
        button.title=Object.entries(segment.scores).map(([k,v])=>`${k}: ${segment.score_scale==='z'?'z ':''}${v.toFixed(2)}`).join('\n');return button;
      }));
    }catch(error){if(token===audioToken)$('audio-status').textContent=`Analyse fehlgeschlagen: ${error.message}`;}
    finally{if(token===audioToken){busy=false;updateAnalyze();$('audio-model').disabled=false;$('audio-cancel').disabled=true;}}
  };
  $('audio-cancel').onclick=()=>{audioToken++;cancelPending=post('/api/audio/cancel').catch(()=>{});busy=false;$('audio-model').disabled=false;$('audio-status').textContent='Analyse abgebrochen.';updateAnalyze();$('audio-cancel').disabled=true;};
  playback.ontimeupdate=()=>{if(audioData)$('audio-words').textContent=audioData.words.filter(w=>playback.currentTime>=w.start && playback.currentTime<w.end).map(w=>w.word).join(' ');};
  window.addEventListener('pagehide',()=>{viewer.stop();clearInterval(readinessTimer);playback.pause();performance.stop();navigator.sendBeacon('/api/audio/cancel');});
  return {setMode};
}
