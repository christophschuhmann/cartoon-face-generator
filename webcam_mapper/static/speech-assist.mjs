// Optional short extrapolation, never an audio/lip-sync claim. No microphone.
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export class SpeechAssist {
  constructor() {this.enabled = false; this.releaseMs = 400; this.reset();}
  reset() {
    this.samples = []; this.turns = []; this.direction = 0; this.anchor = null;
    this.lastMovement = -Infinity; this.lastCapture = -Infinity;
    this.armed = false; this.period = 320; this.amplitude = .15; this.origin = 0;
  }
  observe(value, captured, {tracking = true, tongue = 0, pout = 0} = {}) {
    if (!this.enabled || !tracking || tongue > .15 || pout > .45 || !Number.isFinite(value)) {this.reset(); return;}
    if (captured <= this.lastCapture) return;
    if (captured - this.lastCapture > 600) this.reset();
    this.lastCapture = captured;
    this.samples.push({value, time:captured});
    this.samples = this.samples.filter(s => captured - s.time < 1000);
    if (this.anchor === null) {this.anchor = value; return;}
    const delta = value - this.anchor;
    if (Math.abs(delta) >= .035) {
      const direction = Math.sign(delta);
      this.lastMovement = captured;
      if (this.direction && direction !== this.direction) this.turns.push(captured);
      this.direction = direction; this.anchor = value;
    }
    this.turns = this.turns.filter(t => captured - t < 1000);
    // Three reversals require repeated opening AND closing; a single yawn,
    // smile or a held-open mouth must never start a looping speech animation.
    if (this.turns.length >= 3) {
      if (!this.armed) this.origin = captured;
      this.armed = true;
      const t = this.turns;
      this.period = clamp(2 * (t.at(-1)-t[0])/(t.length-1), 230, 520);
      const values = this.samples.map(s => s.value);
      this.amplitude = clamp(Math.max(...values)-Math.min(...values), .08, .38);
    }
    if (captured - this.lastMovement >= this.releaseMs) this.armed = false;
  }
  sample(now) {
    const age = now - this.lastMovement;
    if (!this.enabled || !this.armed || age >= this.releaseMs || now-this.lastCapture > this.releaseMs) return null;
    const fade = clamp((this.releaseMs-age)/120, 0, 1);
    const attack = clamp((now-this.origin)/65, 0, 1);
    const phase = (now-this.origin) * Math.PI * 2 / this.period;
    return {openness: .015 + this.amplitude * (.5-.5*Math.cos(phase)), weight:.85*fade*attack};
  }
}
