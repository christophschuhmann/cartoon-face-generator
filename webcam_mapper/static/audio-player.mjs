import {numericAttribute} from './avatar-motion.mjs';
import {OrganicRig,coupledMotion,blinkSchedule,blinkAt,GazeFollower} from './audio-organic.mjs';
import {FaceProjection,viewerHead,viewerEyes,ellipseMatrix} from './head-follow.mjs';
const selector = 'path,ellipse,g#avatar-head';
const attributes = ['d','cx','cy','rx','ry','transform','opacity','stroke-width'];
const clamp = (v,a=0,b=1) => Math.max(a,Math.min(b,v));
const ease = v => {v=clamp(v);return v*v*(3-2*v);};

function compile(svg, mouth = null) {
  const root = new DOMParser().parseFromString(svg,'image/svg+xml').documentElement;
  const fields = [...root.querySelectorAll(selector)].map(node => ({id:node.id,
    attributes:attributes.filter(a=>node.hasAttribute(a)).map(name=>({name,...numericAttribute(node.getAttribute(name))}))}));
  const basis = {};
  if (mouth) for (const id of Object.keys(mouth.closed)) {
    basis[id] = Object.fromEntries(['d','opacity'].map(name=>[name,{
      closed:numericAttribute(String(mouth.closed[id][name])).values,
      open:numericAttribute(String(mouth.open[id][name])).values,
    }]));
  }
  return {root,fields,basis,range:mouth?.range || .6};
}

export function envelopeAt(envelope,t) {
  const p=Math.max(0,t/envelope.step), i=Math.floor(p),v=envelope.values;
  return (v[i]||0)*(1-(p-i))+(v[i+1]||0)*(p-i);
}

export function speechOpening(t,words,envelope,pattern,arousal) {
  const word=words.find(w=>t>=w.start && t<w.end);
  if (!word) return 0;
  const attack=ease((t-word.start)/.025),release=ease((word.end-t)/.04);
  const rate=pattern.tempo*(.75+.65*arousal);
  const syllable=.50+.50*Math.sin((t-word.start)*Math.PI*rate)**2;
  return clamp(envelopeAt(envelope,t)*(.28+.40*arousal)*pattern.aperture*syllable*attack*release,0,.6);
}

// Preserve the preceding expression's actual decay across gaps. Reconstructing
// weights from the audio clock also makes seeking deterministic.
export function performanceWeights(segments,t,transition=.45) {
  // Overlapping influence curves retain all contributions across short phrases.
  // The expression can anticipate a word; articulation remains strictly timed.
  const states=[];let total=0;
  for(const segment of segments){
    const weight=ease((t-segment.start+.12)/transition)*(1-ease((t-segment.end)/.85));
    if(weight>0){states.push({segment,weight});total+=weight;}
  }
  const scale=Math.max(1,total);
  return [{segment:null,weight:Math.max(0,1-total)},...states.map(s=>({...s,weight:s.weight/scale}))];
}

export class AudioPerformance {
  constructor(container,audio,onSegment=()=>{}) {
    this.container=container;this.audio=audio;this.onSegment=onSegment;this.raf=null;this.lastIndex=-2;
    this.tick=this.tick.bind(this);this.data=null;this.lastPaint=-Infinity;
    this.dynamics=1;this.transition=.45;this.gaze=new GazeFollower();this.viewer=this.gaze.state;this.viewerClock=null;
    this.headFollow=false;this.headMix=0;
  }
  load(data) {
    this.stop();this.data=data;
    this.gaze.reset();this.viewer=this.gaze.state;this.viewerClock=null;
    this.headMix=this.headFollow?1:0;
    this.neutral=compile(data.neutral_svg,data.neutral_mouth);
    this.segments=data.segments.map(s=>({...s,compiled:s.poses.map(p=>compile(p.svg,p.mouth))}));
    this.container.replaceChildren(document.importNode(this.neutral.root,true));
    this.nodes=[...this.container.querySelectorAll(selector)];this.lastIndex=-2;
    this.rig=new OrganicRig(this.container);this.blinks=blinkSchedule(data.words,data.duration);
    this.paint(this.audio.currentTime);this.tick();
  }
  stop() {if(this.raf!==null)cancelAnimationFrame(this.raf);this.raf=null;this.data=null;}
  setViewer(position){this.gaze.observe(position,performance.now());}
  clearViewer(){this.gaze.clear();}
  tick(now=performance.now()) {
    if(!this.data)return;
    if(now-this.lastPaint>=1000/30-1){
      const dt=this.viewerClock===null?1/30:Math.max(0,Math.min(.1,(now-this.viewerClock)/1000));
      const headTarget=this.headFollow?1:0;
      this.headMix+=(headTarget-this.headMix)*(1-Math.exp(-dt/.22));
      if(Math.abs(headTarget-this.headMix)<.0001)this.headMix=headTarget;
      if(this.audio.paused!==true){
        this.viewer=this.gaze.step(now,dt);
      }
      this.viewerClock=now;this.paint(this.audio.currentTime);this.lastPaint=now;
    }
    this.raf=requestAnimationFrame(this.tick);
  }
  paint(t) {
    if(!this.data)return;
    const weighted=performanceWeights(this.segments,t,this.transition);
    const dominant=weighted.filter(s=>s.segment && s.weight>.01).sort((a,b)=>b.weight-a.weight)[0]?.segment;
    const labelKey=dominant?this.segments.indexOf(dominant):-1;
    if(labelKey!==this.lastIndex){this.lastIndex=labelKey;this.onSegment(dominant,labelKey);}
    const states=weighted.filter(s=>s.weight>0).map(({segment,weight})=>({
      weight,segment,lo:segment?.compiled[0] || this.neutral,hi:segment?.compiled[1] || this.neutral,
      pulse:.5,
    }));
    const opening=states.reduce((sum,s)=>sum+s.weight*speechOpening(t,this.data.words,this.data.envelope,
      s.segment?.pattern || {tempo:3,aperture:1},s.segment?.arousal ?? .5),0);
    const previous=states.reduce((sum,s)=>sum+s.weight*speechOpening(t-.075,this.data.words,this.data.envelope,
      s.segment?.pattern || {tempo:3,aperture:1},s.segment?.arousal ?? .5),0);
    const arousal=states.reduce((v,s)=>v+s.weight*(s.segment?.arousal ?? .5),0);
    const intensity=states.reduce((v,s)=>v+s.weight*(s.segment?.intensity || 0),0);
    const affect=Object.fromEntries(['aggression','negative'].map(key=>[key,
      states.reduce((v,s)=>v+s.weight*(s.segment?.affect?.[key] || 0),0)]));
    const muscle=coupledMotion(opening,previous,arousal,intensity,this.dynamics,affect);
    const head=viewerHead(this.viewer,this.headMix);
    const projection=Math.abs(head.yaw)+Math.abs(head.pitch)>1e-6?new FaceProjection(head.yaw,head.pitch):null;
    for(const state of states)state.pulse=clamp(.48+.42*muscle.drive+.12*muscle.attack);
    const value=(s,i,j,k)=>{
      const l=s.lo.fields[i].attributes[j],h=s.hi.fields[i].attributes[j];
      const id=s.lo.fields[i].id,name=l.name;
      const one=(pose,attribute)=>{
        const basis=pose.basis[id]?.[name];
        if(basis && basis.closed.length===attribute.values.length){
          const f=clamp(opening/pose.range);return basis.closed[k]+(basis.open[k]-basis.closed[k])*f;
        }
        return attribute.values[k];
      };
      return one(s.lo,l)*(1-s.pulse)+one(s.hi,h)*s.pulse;
    };
    for(let i=0;i<this.nodes.length;i++) {
      const reference=this.neutral.fields[i];
      for(let j=0;j<reference.attributes.length;j++){
        const attr=reference.attributes[j];let text=attr.parts[0];
        const values=attr.values.map((_,k)=>states.reduce((sum,s)=>sum+s.weight*value(s,i,j,k),0));
        if(projection && attr.name==='d')for(let k=0;k<values.length;k+=2){
          [values[k],values[k+1]]=projection.point(values[k],values[k+1],reference.id==='nose');
        }
        for(let k=0;k<values.length;k++)text+=values[k].toFixed(4)+attr.parts[k+1];
        if(reference.id==='avatar-head' && attr.name==='transform'){
          let roll=0,nod=0;
          for(const s of states){if(!s.segment)continue;
            const p=s.segment.pattern,phase=t*Math.PI*2*p.sway;
            const motion=s.weight*(.35+.65*s.segment.arousal)*s.segment.intensity;
            roll+=(.12*Math.sin(phase)+.40*muscle.attack)*p.roll*motion*this.dynamics;
            nod+=(-.25*muscle.drive+.30*muscle.attack)*p.nod*motion;
          }
          text+=` rotate(${roll+head.roll} 725 375) translate(0 ${nod+muscle.headY})`;
        }
        if(attr.values.length)this.nodes[i].setAttribute(attr.name,text);
      }
    }
    if(projection)for(const node of this.nodes)if(node.localName==='ellipse'){
      const matrix=projection.ellipse(ellipseMatrix(node),Number(node.getAttribute('cx')),Number(node.getAttribute('cy')));
      node.setAttribute('transform',`matrix(${matrix.join(' ')})`);
    }
    // Include the expression's head tilt, so eye contact survives diagonal poses.
    const headMatrix=ellipseMatrix(this.rig.head),roll=Math.atan2(headMatrix[1],headMatrix[0]);
    const eyes=viewerEyes(this.viewer,head,this.headMix,roll);
    this.rig.apply(muscle,blinkAt(this.blinks,t)*Math.min(1,this.dynamics),eyes);
  }
}
