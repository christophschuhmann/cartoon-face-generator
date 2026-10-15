import {AvatarMotion} from './avatar-motion.mjs';
import {installAudioMode} from './audio-ui.mjs';

const $ = id => document.getElementById(id);
const video = $('camera'), canvas = $('capture'), ctx = canvas.getContext('2d');
const motion = new AvatarMotion($('avatar'));
let stream = null, running = false, starting = false, timer = null, targetFps = 24;
let serverMaxFps = 30, generation = 0, lastFrameTime = null, measuredFps = 0;
let processing = null;
let settingsTimer = null, settingsQueue = Promise.resolve(), previewGeneration = 0;
const sensitivityKeys = ['brows', 'frown', 'speech', 'gaze', 'tongue', 'squint'];
const squintTuning=document.createElement('label');
squintTuning.innerHTML='Augen zusammenkneifen <output id="squint-value">1,70×</output><input id="sensitivity-squint" type="range" min="0.5" max="3" value="1.7" step="0.05">';
document.querySelector('.tuning-grid').append(squintTuning);
const mouthTuning=document.createElement('label');
mouthTuning.innerHTML='Zungenerkennung <select id="mouth-detector"><option value="babble">Babble · Mundmodell</option><option value="siglip">SigLIP · Vergleich mit Textbeschreibungen</option><option value="geometry">Farbe + Mundform</option><option value="off">Zunge aus</option></select><span id="mouth-status" class="subtle"></span>';
document.querySelector('.tuning-grid').append(mouthTuning);
const gainControl = key => $('sensitivity-' + key);
const show = message => $('status').textContent = message;
if (matchMedia('(prefers-reduced-motion: reduce)').matches) {motion.smoothing = 0; $('smoothing').value = '0'; $('smoothing-value').value = '0 ms';}

function showExpression(e = {}) {
  $('expression-label').textContent = !e.enabled ? 'Direkte Mimik · Emotionen aus' : e.state === 'no_face' ? 'Warte auf dein Gesicht …' : e.archetype || 'Noch kein klarer Ausdruck';
  $('expression-meta').textContent = e.cnn ? `CNN-Schätzung: ${e.cnn.label} · ${e.source} · effektiv ${Math.round(e.effective_strength * 100)} %` : e.cnn_error ? 'CNN nicht verfügbar · direkte Gesten bleiben aktiv.' : e.source || 'Archetypen sind Ausdrucksstile; feine Bedeutungen bleiben kontextabhängig.';
  const deep = e.empathic;
  if (deep?.state === 'active' && deep.scores && Number.isFinite(deep.age_seconds)) {
    $('engine-status').textContent = `40 Kategorien aktiv · ${(deep.inference_ms / 1000).toFixed(1)} s pro Schätzung · Bild vor ${deep.age_seconds.toFixed(1)} s`;
    $('expression-meta').textContent = `${e.source} · effektiv ${Math.round(e.effective_strength * 100)} % · direkte Mimik bleibt live`;
    if ($('scores40').open) for (const [slug, score] of Object.entries(deep.scores)) {
      const meter = $('score-' + slug), output = $('score-value-' + slug);
      if (meter) {meter.value = Math.max(0, score.adjusted); output.value = score.adjusted.toFixed(1);}
    }
  } else {
    $('engine-status').textContent = !e.enabled ? 'Emotionserkennung ausgeschaltet.' : e.backend !== 'empathic' ? 'Direkte Mimik und ähnliche Ausdrucksstile aktiv.' : deep?.state === 'error' ? `40er-Modell: ${deep.error} · direkte Mimik bleibt aktiv.` : '40-Kategorien-Modell wird vorbereitet … direkte Mimik läuft weiter.';
  }
  $('expression-candidates').replaceChildren(...(e.candidates || []).map(item => {
    const chip = document.createElement('span'); chip.className = 'chip';
    chip.textContent = item.label; chip.title = 'Ähnliche Cartoon-Mimik, keine gemessene Emotionswahrscheinlichkeit'; return chip;
  }));
  $('learning-status').textContent = e.learning_remaining ? `Ausdruck halten … noch ${e.learning_remaining} Bilder` : `${e.reference_count || 0} eigene Mimikmuster in dieser Sitzung.`;
}

function currentSettings() {
  return {expressions: {enabled: $('emotion-enabled').checked, strength: Number($('emotion-strength').value) / 100,
    social: $('social-enabled').checked, manual: $('archetype').value, backend: $('expression-engine').value,
    variant: $('empathic-variant').value},
    sensitivity: Object.fromEntries(sensitivityKeys.map(key => [key, Number(gainControl(key).value)])),
    animation:{speech:$('speech-assist').checked,release_ms:Number($('speech-release').value)},mouth:{mode:$('mouth-detector').value}};
}

function settingsLabels() {
  motion.speech.enabled=$('speech-assist').checked;
  motion.speech.releaseMs=Number($('speech-release').value);
  if(!motion.speech.enabled)motion.stopSpeech();
  const strength = Number($('emotion-strength').value);
  $('emotion-value').value = `${strength} % Archetyp · ${100 - strength} % Mimik`;
  $('emotion-strength').disabled = !$('emotion-enabled').checked;
  $('empathic-variant').disabled = $('expression-engine').value !== 'empathic';
  for (const key of sensitivityKeys) $(key + '-value').value = `${Number(gainControl(key).value).toFixed(2).replace('.', ',')}×`;
}

function saveSettings() {
  settingsLabels(); clearTimeout(settingsTimer);
  settingsTimer = setTimeout(() => {
    const data = currentSettings();
    settingsQueue = settingsQueue.catch(() => {}).then(async () => {
      await post('/api/settings', JSON.stringify(data), {'Content-Type': 'application/json'});
      try {localStorage.setItem('mimikstudio-v2', JSON.stringify({...data, expressions: {...data.expressions, manual: ''}}));} catch {}
      if (!data.expressions.enabled) showExpression({enabled: false});
    }).catch(error => show(`Einstellung konnte nicht übernommen werden: ${error.message}`));
  }, 120);
}

async function previewArchetype() {
  const token = ++previewGeneration, slug = $('preview-expression').value;
  try {
    const response = await fetch('/api/archetype/' + encodeURIComponent(slug));
    const data = await response.json();
    if (!response.ok) throw Error(data.error);
    if (token !== previewGeneration) return;
    const doc = new DOMParser().parseFromString(data.svg, 'image/svg+xml');
    $('gallery-avatar').replaceChildren(document.importNode(doc.documentElement, true));
    const group = $('preview-expression').selectedOptions[0].parentElement.label;
    $('gallery-note').textContent = `${group} · Archetyp im gemeinsamen 101-Punkt-Rig`;
  } catch (error) {show(error.message);}
}

function showGestures(data) {
  const detector=data.mouth_detector;
  if(detector)$('mouth-status').textContent=detector.error || `${detector.mode} · ${detector.state}${Number.isFinite(detector.ms)?' · '+Math.round(detector.ms)+' ms':''}`;
  if (!data.tracking) {$('gestures').textContent = 'Warte auf dein Gesicht …'; return;}
  const a = data.controls, labels = [];
  const left = a.eye_open + a.eye_asym / 2, right = a.eye_open - a.eye_asym / 2;
  if (left < .18 && right > .5) labels.push('Dein linkes Auge zwinkert');
  else if (right < .18 && left > .5) labels.push('Dein rechtes Auge zwinkert');
  else if (left < .18 && right < .18) labels.push('Augen geschlossen');
  const direction = (x, y) => [y < -.2 ? 'oben' : y > .2 ? 'unten' : '', x < -.2 ? 'links' : x > .2 ? 'rechts' : ''].filter(Boolean).join(' ');
  const gazeL = direction(a.gaze_x_left, a.gaze_y_left), gazeR = direction(a.gaze_x_right, a.gaze_y_right);
  if (gazeL && gazeL === gazeR) labels.push(`Blick ${gazeL}`);
  else if (gazeL || gazeR) labels.push(`Blick: linkes Auge ${gazeL || 'geradeaus'}, rechtes Auge ${gazeR || 'geradeaus'}`);
  if (Math.abs(a.head_roll) > .12) labels.push('Kopf geneigt');
  if (Math.abs(a.head_yaw) > .16) labels.push('Kopf gedreht');
  if (Math.abs(a.head_pitch) > .14) labels.push('Kopf nach oben/unten');
  if (a.tongue_out > .35) labels.push('Zunge erkannt');
  if (a.lip_pout > .40) labels.push('Schmollmund / Lippen vorgeschoben');
  if (a.squint > .35) labels.push('Augen zusammengekniffen');
  if (a.frown > .25) labels.push('Stirn gerunzelt');
  if (Math.abs(a.brow_raise_left-a.brow_raise_right)>.25)labels.push('Einzelne Augenbraue gehoben');
  $('gestures').textContent = labels.join(' · ') || 'Kopf, Augen und Mimik werden verfolgt.';
}

async function post(url, body, headers) {
  const response = await fetch(url, {method: 'POST', body, headers, signal: AbortSignal.timeout(10000)});
  const data = await response.json();
  if (!response.ok) throw Object.assign(Error(data.error || response.statusText),{status:response.status});
  return data;
}

async function loop(token) {
  if (!running || token !== generation) return;
  const started = performance.now();
  try {
    if (video.readyState >= 2) {
      const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight));
      const width = Math.round(video.videoWidth * scale), height = Math.round(video.videoHeight * scale);
      if (canvas.width !== width || canvas.height !== height) {canvas.width = width; canvas.height = height;}
      ctx.drawImage(video, 0, 0, width, height); // Inference input stays unmirrored.
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .8));
      if (!running || token !== generation) return;
      if (!blob) throw Error('Webcam-Bild konnte nicht gelesen werden.');
      const data = await post('/api/frame', blob, {'Content-Type': 'image/jpeg'});
      if (!running || token !== generation) return;
      motion.setSvg(data.svg);
      motion.track(data,started);
      showGestures(data);
      showExpression(data.expression);
      serverMaxFps = data.suggested_fps;
      const now = performance.now();
      if (lastFrameTime !== null) measuredFps = measuredFps ? .8 * measuredFps + .2 * 1000 / (now - lastFrameTime) : 1000 / (now - lastFrameTime);
      lastFrameTime = now;
      const tracking = data.tracking ? 'Gesicht erkannt' : 'Kein Gesicht · Avatar kehrt zur Ruhepose zurück';
      const calibration = data.calibration_remaining ? ` · neutral halten (${data.calibration_remaining})` : data.calibrated ? ' · kalibriert' : '';
      show(`${tracking}${calibration} · ${measuredFps.toFixed(1)} Hz · CPU ${data.inference_ms} ms · SVG ${data.mapping_render_ms} ms`);
    }
  } catch (error) {
    if(error.status===409 && running && token===generation){
      stop();show('Webcam ausgeschaltet: Die Audio-Bühne ist aktiv.');return;
    }
    if (running && token === generation) show(`Verbindung unterbrochen: ${error.message}. Neuer Versuch …`);
  }
  if (running && token === generation) {
    const period = 1000 / Math.max(.5, Math.min(targetFps, serverMaxFps));
    timer = setTimeout(() => {processing = loop(token);}, Math.max(0, period - (performance.now() - started)));
  }
}

function stop() {
  motion.stopSpeech();
  running = false; starting = false; generation++;
  clearTimeout(timer);
  if (stream) stream.getTracks().forEach(track => track.stop());
  stream = null; video.srcObject = null;
  $('start').disabled = false; $('stop').disabled = true; $('calibrate').disabled = true;
  $('hint').hidden = false;
  show('Webcam ist aus.');
  $('gestures').textContent = 'Kopf gerade halten, Augen öffnen und neutral kalibrieren.';
  const token = generation;
  Promise.resolve(processing).finally(() => {
    if (!running && token === generation) post('/api/stop').catch(() => {});
  });
}

$('start').onclick = async () => {
  if(document.body.dataset.mode==='audio')return;
  starting = true;
  const token = ++generation;
  $('start').disabled = true;
  $('stop').disabled = false;
  show('Webcam wird gestartet …');
  try {
    if (processing) await processing;
    if (!starting || token !== generation) return;
    const acquired = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 640}, height: {ideal: 480}, frameRate: {ideal: 30, max: 30}, facingMode: 'user'}, audio: false});
    if (!starting || token !== generation) {acquired.getTracks().forEach(track => track.stop()); return;}
    stream = acquired; video.srcObject = stream;
    await video.play();
    if (!starting || token !== generation) return;
    starting = false; running = true; lastFrameTime = null; measuredFps = 0;
    $('hint').hidden = true; $('calibrate').disabled = false;
    stream.getVideoTracks()[0].addEventListener('ended', stop, {once: true});
    processing = loop(token);
  } catch (error) {
    if (token !== generation) return;
    stop();
    const explanation = {NotAllowedError: 'Bitte erlaube den Kamerazugriff im Browser.', NotFoundError: 'Keine Webcam gefunden.', NotReadableError: 'Die Webcam ist eventuell in einem anderen Programm geöffnet.'};
    show(`Webcam konnte nicht starten: ${explanation[error.name] || error.message}`);
  }
};
$('stop').onclick = stop;
$('calibrate').onclick = async () => {
  try {await post('/api/calibrate'); show('Entspannt geradeaus schauen und kurz stillhalten …');} catch (error) {show(error.message);}
};
$('reset').onclick = async () => {
  try {const data = await post('/api/reset'); motion.setSvg(data.svg); show('Kalibrierung zurückgesetzt.');} catch (error) {show(error.message);}
};
$('fps').onchange = () => targetFps = Number($('fps').value);
$('smoothing').oninput = () => {motion.smoothing = Number($('smoothing').value); $('smoothing-value').value = `${motion.smoothing} ms`;};
$('focus').onclick = () => {$('focus').textContent = document.body.classList.toggle('avatar-only') ? 'Webcam anzeigen' : 'Nur Avatar';};
$('fullscreen').onclick = async () => {try {if (document.fullscreenElement) await document.exitFullscreen(); else await $('avatar-card').requestFullscreen();} catch (error) {show(error.message);}};
window.addEventListener('pagehide', stop);
for (const id of ['emotion-enabled', 'social-enabled', 'emotion-strength', 'expression-engine', 'empathic-variant', ...sensitivityKeys.map(key => 'sensitivity-' + key)]) $(id).addEventListener('input', saveSettings);
$('archetype').onchange = saveSettings;
for(const id of ['speech-assist','speech-release','mouth-detector'])$(id).addEventListener('input',saveSettings);
$('gallery-open').onclick = () => {$('gallery').showModal(); $('preview-expression').value = $('archetype').value || $('preview-expression').options[0].value; previewArchetype();};
$('gallery-close').onclick = () => $('gallery').close();
$('preview-expression').onchange = previewArchetype;
for (const [id, step] of [['gallery-prev', -1], ['gallery-next', 1]]) $(id).onclick = () => {
  const select = $('preview-expression'); select.selectedIndex = (select.selectedIndex + step + select.options.length) % select.options.length; previewArchetype();
};
$('gallery-apply').onclick = () => {$('archetype').value = $('preview-expression').value; $('emotion-enabled').checked = true; saveSettings(); $('gallery').close();};
$('learn-expression').onclick = async () => {
  if (!$('archetype').value) {show('Wähle zuerst einen Archetyp, zu dem du deine Mimik anlernen möchtest.'); return;}
  if (!running) {show('Starte zuerst die Webcam, um einen Ausdruck anzulernen.'); return;}
  try {
    await post('/api/reference', JSON.stringify({slug: $('archetype').value}), {'Content-Type': 'application/json'});
    $('archetype').value = ''; saveSettings(); show('Deinen Ausdruck kurz halten – danach wird er im automatischen Modus wiedererkannt.');
  } catch (error) {show(error.message);}
};
$('clear-references').onclick = async () => {
  try {await post('/api/reference', JSON.stringify({clear: true}), {'Content-Type': 'application/json'}); $('learning-status').textContent = 'Alle eigenen Muster gelöscht.';} catch (error) {show(error.message);}
};

try {
  const response = await fetch('/api/config');
  if (!response.ok) throw Error('Lokaler Server antwortet nicht.');
  const data = await response.json();
  if (!Array.isArray(data.catalog) || !data.expressions || !data.sensitivity) {
    throw Error('Der Avatar-Server läuft noch mit einer älteren Version. Bitte Start-Avatar.cmd erneut öffnen.');
  }
  for (const [taxonomy, label] of [['emonet_face_40_v1', '40 EmoNet-Emotionen'], ['cartoon_social_60_v1', '60 soziale Cartoon-Ausdrücke']]) {
    for (const id of ['archetype', 'preview-expression']) {
      const group = document.createElement('optgroup'); group.label = label;
      for (const item of data.catalog.filter(item => item.taxonomy === taxonomy)) group.append(new Option(item.label, item.slug));
      $(id).append(group);
    }
  }
  for (const item of data.catalog.filter(item => item.taxonomy === 'emonet_face_40_v1')) {
    const row = document.createElement('div'); row.className = 'score-row';
    const name = document.createElement('span'); name.textContent = item.label;
    const meter = document.createElement('meter'); meter.id = 'score-' + item.slug; meter.min = 0; meter.max = 4; meter.value = 0;
    const output = document.createElement('output'); output.id = 'score-value-' + item.slug; output.value = '–';
    row.append(name, meter, output); $('score-grid').append(row);
  }
  let settings = {expressions: data.expressions, sensitivity: data.sensitivity,animation:data.animation,mouth:data.mouth};
  try {
    const saved = JSON.parse(localStorage.getItem('mimikstudio-v2'));
    if (saved) {
      if(saved.expressions?.backend==='fast')saved.expressions.backend='motion';
      const response = await post('/api/settings', JSON.stringify(saved), {'Content-Type': 'application/json'});
      settings = response;
    }
  } catch {}
  $('emotion-enabled').checked = settings.expressions.enabled;
  $('speech-assist').checked=settings.animation?.speech || false;
  $('mouth-detector').value=settings.mouth?.mode || 'geometry';
  for(const option of $('mouth-detector').options)option.disabled=!data.mouth?.available?.[option.value];
  $('speech-release').value=String(settings.animation?.release_ms || 400);
  $('social-enabled').checked = settings.expressions.social;
  $('emotion-strength').value = settings.expressions.strength * 100;
  $('archetype').value = settings.expressions.manual || '';
  $('expression-engine').value = settings.expressions.backend || 'motion';
  $('empathic-variant').value = settings.expressions.variant || 'small';
  for (const option of $('empathic-variant').options) option.disabled = !data.expressions.empathic_variants?.[option.value];
  $('expression-engine').querySelector('[value="empathic"]').disabled = !data.expressions.empathic_available;
  for (const key of sensitivityKeys) gainControl(key).value = settings.sensitivity[key];
  settingsLabels();
  targetFps = data.target_fps;
  if (![5, 10, 15, 24, 30].includes(targetFps)) $('fps').add(new Option(`${targetFps} Hz`, targetFps));
  $('fps').value = String(targetFps);
  motion.setSvg(data.svg, true);
  $('start').disabled = false; $('reset').disabled = false;
  show('Bereit. Starte die Webcam und erlaube den Kamerazugriff.');
  const audioMode=installAudioMode({motion,stop,waitProcessing:()=>Promise.resolve(processing),post,show});
  if(data.mode==='audio' || new URLSearchParams(location.search).get('mode')==='audio')await audioMode.setMode('audio');
  else if (new URLSearchParams(location.search).get('autostart') === '1') $('start').click();
} catch (error) {show(`Start fehlgeschlagen: ${error.message}`);}
