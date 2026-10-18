/** Independent Robby display rig; MIT. No 101-keypoint topology is implied. */
export const REQUIRED_IDS = ['body', 'head', 'eye-left', 'eye-right', 'brow-left',
  'brow-right', 'smile', 'mouth-open', 'heart', 'heart-halo'];
const bounded = (v, lo, hi) => Math.max(lo, Math.min(hi, Number.isFinite(v) ? v : 0));

/** Controls are display-space x/y, degrees roll, and [0,1] expression strengths.
 * eyeLeft / blinkLeft mean the eye on the LEFT OF THE IMAGE, not anatomy.
 * This intentionally differs from the original cartoon rig's anatomical IDs.
 */
export function normalizeControls(c = {}) {
  return {x: bounded(c.x, -1, 1), y: bounded(c.y, -1, 1),
    roll: bounded(c.roll, -35, 35), blinkLeft: bounded(c.blinkLeft, 0, 1),
    blinkRight: bounded(c.blinkRight, 0, 1), smile: bounded(c.smile, 0, 1),
    jaw: bounded(c.jaw, 0, 1), audioLevel: bounded(c.audioLevel, 0, 1)};
}

/** MediaPipe semantic blendshapes -> authored display controls, not emotions. */
export function controlsFromFace(result) {
  const p = result?.faceLandmarks?.[0];
  if (!p?.[263]) return normalizeControls();
  const b = Object.fromEntries((result.faceBlendshapes?.[0]?.categories || [])
    .map(x => [x.categoryName, x.score]));
  return normalizeControls({x: (.5 - p[1].x) * 4, y: (p[1].y - .5) * 3,
    roll: Math.atan2(p[263].y-p[33].y, p[263].x-p[33].x) * 180 / Math.PI,
    blinkLeft: b.eyeBlinkRight, blinkRight: b.eyeBlinkLeft,
    smile: ((b.mouthSmileLeft || 0)+(b.mouthSmileRight || 0))/2, jaw: b.jawOpen});
}

export function createRobbyRig(svg) {
  const nodes = Object.fromEntries(REQUIRED_IDS.map(id => [id, svg.querySelector('#'+id)]));
  const missing = REQUIRED_IDS.filter(id => !nodes[id]);
  if (missing.length) throw new Error('Missing Robby SVG IDs: '+missing.join(', '));
  let smooth = normalizeControls();
  return {
    /** dtMs makes smoothing independent of display refresh rate. */
    update(controls = {}, dtMs = 16.7, timeMs = 0) {
      const target = normalizeControls(controls);
      const alpha = 1-Math.exp(-bounded(dtMs, 0, 1000)/100);
      for (const k of Object.keys(smooth)) smooth[k] += alpha*(target[k]-smooth[k]);
      const c = smooth, breath = Math.sin(timeMs/2100)*1.2;
      nodes.head.setAttribute('transform', `translate(${c.x*8} ${breath+c.y*3}) rotate(${c.roll*.3} 400 290)`);
      nodes['eye-left'].setAttribute('transform', `translate(${270+c.x*6} ${267+c.y*5}) scale(1 ${Math.max(.08,1-c.blinkLeft)})`);
      nodes['eye-right'].setAttribute('transform', `translate(${530+c.x*6} ${267+c.y*5}) scale(1 ${Math.max(.08,1-c.blinkRight)})`);
      const opening = Math.max(c.audioLevel, c.jaw*.8);
      nodes['mouth-open'].setAttribute('ry', String(1+opening*28));
      nodes['mouth-open'].setAttribute('opacity', String(Math.min(1,opening*5)));
      nodes.smile.setAttribute('d', `M360 346 Q400 ${375+c.smile*13} 440 346`);
      nodes.smile.setAttribute('opacity', String(Math.max(.05,1-opening*3)));
      nodes['heart-halo'].setAttribute('opacity', String(.3+c.audioLevel*.5+.12*Math.sin(timeMs/1000)));
      return {...c};
    },
    reset() { smooth = normalizeControls(); this.update({}, 1000, 0); }
  };
}
