// Interpolate the shared renderer's fixed-topology SVG curves, including clips.
// Retarget from the displayed geometry, so incoming poses never jump.
const NUMBER = /[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g;
const ATTRIBUTES = ['d', 'cx', 'cy', 'rx', 'ry', 'transform', 'opacity', 'stroke-width'];
import {SpeechAssist} from './speech-assist.mjs';

export function numericAttribute(value) {
  return {parts: value.split(NUMBER), values: (value.match(NUMBER) || []).map(Number)};
}

export function advance(current, target, dt, tau) {
  const alpha = tau <= 0 ? 1 : -Math.expm1(-Math.max(0, dt) / tau);
  return current + (target - current) * alpha;
}

export class AvatarMotion {
  constructor(container) {
    this.container = container;
    this.fields = [];
    this.smoothing = 45;
    this.lastTime = null;
    this.pending = false;
    this.speech = new SpeechAssist();
    this.speechBasis = null;
    this.tick = this.tick.bind(this);
  }

  track(data, captured) {
    if(!data.tracking || !data.speech_basis)this.stopSpeech();
    const a = data.controls;
    this.speech.observe(a.mouth_open, captured, {tracking:data.tracking, tongue:a.tongue_out, pout:a.lip_pout});
    this.speechBasis = data.speech_basis || null;
    if (!this.pending && this.speech.sample(performance.now())) {
      this.lastTime = performance.now(); this.pending = true; requestAnimationFrame(this.tick);
    }
  }

  stopSpeech() {
    this.speech.reset();
    for(const field of this.fields)if(['mouth_fill','mouth_upper','mouth_lower'].includes(field.node.id)){
      for(const attr of field.attributes){
        let value=attr.parts[0];for(let i=0;i<attr.current.length;i++)value+=attr.current[i].toFixed(4)+attr.parts[i+1];
        if(attr.current.length)field.node.setAttribute(attr.name,value);
      }
    }
    this.speechBasis=null;
  }

  setSvg(source, immediate = false) {
    this.suspended = false;
    const next = new DOMParser().parseFromString(source, 'image/svg+xml').documentElement;
    if (next.localName !== 'svg') throw Error('Ungültige SVG-Antwort.');
    const selector = 'path,ellipse,g#avatar-head';
    const incoming = [...next.querySelectorAll(selector)];
    let existing = [...this.container.querySelectorAll(selector)];
    const sameTopology = existing.length === incoming.length && existing.every((node, i) =>
      node.localName === incoming[i].localName && node.id === incoming[i].id);
    if (!sameTopology || immediate) {
      this.container.replaceChildren(document.importNode(next, true));
      existing = [...this.container.querySelectorAll(selector)];
      this.fields = [];
    }
    const previous = new Map(this.fields.map(field => [field.node, field]));
    this.fields = [];
    for (let i = 0; i < incoming.length; i++) {
      const node = existing[i], before = previous.get(node);
      const field = {node, attributes: [], fast: /eye_|pupil|highlight|lash|mouth_|tongue/.test(node.id) || !!node.closest('clipPath')};
      for (const name of ATTRIBUTES) {
        if (!incoming[i].hasAttribute(name)) continue;
        const target = numericAttribute(incoming[i].getAttribute(name));
        const old = before?.attributes.find(attribute => attribute.name === name);
        const current = old ? {parts: old.parts, values: old.current} : numericAttribute(node.getAttribute(name) || '');
        if (current.parts.join('#') !== target.parts.join('#') || current.values.length !== target.values.length) {
          node.setAttribute(name, incoming[i].getAttribute(name));
          continue;
        }
        field.attributes.push({name, parts: target.parts, current: current.values.slice(), target: target.values});
      }
      this.fields.push(field);
    }
    if (!this.pending) {
      this.lastTime = performance.now();
      this.pending = true;
      requestAnimationFrame(this.tick);
    }
  }

  tick(now) {
    if(this.suspended){this.pending=false;return;}
    // Leave CPU time for inference on older two-core laptops.
    if (now - this.lastTime < 1000 / 30 - 1) {requestAnimationFrame(this.tick); return;}
    const dt = Math.min(100, now - this.lastTime);
    this.lastTime = now;
    let moving = false;
    const speech = this.speechBasis && this.speech.sample(now);
    for (const field of this.fields) {
      const tau = field.fast ? Math.min(18, this.smoothing) : this.smoothing;
      for (const attribute of field.attributes) {
        const basis = this.speechBasis;
        const isMouth = basis?.closed[field.node.id] && ['d','opacity'].includes(attribute.name);
        if (!isMouth && attribute.current.every((value, i) => value === attribute.target[i])) continue;
        const closed = isMouth ? numericAttribute(String(basis.closed[field.node.id][attribute.name])) : null;
        const opened = isMouth ? numericAttribute(String(basis.open[field.node.id][attribute.name])) : null;
        const morph = speech && closed?.values.length === attribute.current.length && opened?.values.length === attribute.current.length;
        let value = attribute.parts[0];
        for (let i = 0; i < attribute.target.length; i++) {
          const target = attribute.target[i];
          let current = advance(attribute.current[i], target, dt, tau);
          if (Math.abs(target - current) < (attribute.name === 'opacity' ? .001 : .02)) current = target;
          else moving = true;
          attribute.current[i] = current;
          let displayed = current;
          if (morph) {
            const fraction = Math.max(0, Math.min(1, speech.openness/basis.range));
            const predicted = closed.values[i] + (opened.values[i]-closed.values[i])*fraction;
            displayed += (predicted-current)*speech.weight;
          }
          value += displayed.toFixed(4) + attribute.parts[i + 1];
        }
        if (attribute.target.length) field.node.setAttribute(attribute.name, value);
      }
    }
    this.pending = moving || !!speech;
    if (this.pending) requestAnimationFrame(this.tick);
  }
}
