import {numericAttribute} from './avatar-motion.mjs';
import {ellipseMatrix} from './head-follow.mjs';
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const ease=x=>{x=clamp(x);return x*x*(3-2*x);};

export function viewerDirection(position,mirror=true){
  return {x:clamp((position.x-.5)*2.8*(mirror?-1:1),-1,1),y:clamp((position.y-.40)*3,-1,1)};
}

// Eyes acquire a person first; the slower head follows without copying camera
// noise. All times are monotonic milliseconds, independent of audio seeking.
export class GazeFollower {
  constructor(){this.reset();}
  reset(){
    this.target=null;this.seen=-Infinity;
    this.state={x:0,y:0,headX:0,headY:0,weight:0};
  }
  observe(position,now){
    if(!position || !Number.isFinite(position.x) || !Number.isFinite(position.y))return;
    const next=viewerDirection(position);
    if(!this.target || now-this.seen>=850)this.target=next;
    else for(const axis of ['x','y']){
      const delta=next[axis]-this.target[axis],deadband=.024;
      if(Math.abs(delta)>deadband)this.target[axis]=next[axis]-Math.sign(delta)*deadband;
    }
    this.seen=now;
  }
  clear(){this.target=null;this.seen=-Infinity;}
  step(now,seconds){
    const dt=clamp(seconds,0,.1),fresh=this.target && now-this.seen<850;
    for(const axis of ['x','y']){
      const target=fresh?this.target[axis]:0,head=axis==='x'?'headX':'headY';
      const distance=Math.abs(target-this.state[axis]);
      const eyeTime=fresh?(distance>.18?.10:.16):.48;
      this.state[axis]+=(target-this.state[axis])*(1-Math.exp(-dt/eyeTime));
      this.state[head]+=(target-this.state[head])*(1-Math.exp(-dt/(fresh?.36:.65)));
    }
    this.state.weight+=((fresh?1:0)-this.state.weight)*(1-Math.exp(-dt/(fresh?.18:.55)));
    return this.state;
  }
}

export function blinkSchedule(words,duration){
  const result=[];
  for(let t=2.8;t<duration;t+=3.8+.7*Math.sin(t*1.7)){
    const nearby=words.find(w=>Math.abs(w.end-t)<.45);
    result.push(nearby?nearby.end+.08:t);
  }
  return result;
}

export function coupledMotion(opening,previous,arousal,intensity,dynamics=1,affect={}){
  const drive=clamp((.72*opening+.28*previous)/.6)*dynamics;
  const attack=clamp((opening-previous)*3,-.5,.5)*dynamics;
  const aggression=clamp(affect.aggression||0),negative=clamp(affect.negative||0);
  // Negative speech keeps its downturned corners and brow tension instead of
  // adding the same cheerful cheek/brow lift to every syllable.
  return {drive,attack,eyeScale:1-(.12+.05*aggression)*drive,
    cheekY:-6*drive*(1-.85*negative),browY:(-7+17*aggression)*drive,
    noseY:-2.3*drive,headY:-(2.5+3*arousal)*drive-3*attack,
    mouthWidth:1+.035*drive,energy:(.4+.6*arousal)*intensity};
}

export class OrganicRig {
  constructor(container){
    this.root=container.querySelector('svg');this.head=this.root.querySelector('#avatar-head');
    // Room for lifted brows and emphatic head motion, retaining rig proportions.
    const [x,y,width,height]=this.root.getAttribute('viewBox').split(/\s+/).map(Number);
    this.root.setAttribute('viewBox',`${x-width*.09} ${y-height*.09} ${width*1.18} ${height*1.18}`);
    this.eyes={};this.brows={};this.cheeks={};
    const ns='http://www.w3.org/2000/svg';
    const wrap=(id,match)=>{
      const group=document.createElementNS(ns,'g');group.id=id;
      const nodes=[...this.head.children].filter(n=>match(n.id || n.querySelector('[id]')?.id || ''));
      if(nodes.length){this.head.insertBefore(group,nodes[0]);nodes.forEach(n=>group.append(n));}
      return group;
    };
    for(const side of ['left','right']){
      this.eyes[side]=wrap('organic-'+side+'-eye',id=>id.startsWith(side+'_') && /_(eye_|pupil|highlight|secondary_highlight|heart|lash|lid_accent|under_eye|hatch_|lower_accent)/.test(id));
      this.brows[side]=wrap('organic-'+side+'-brow',id=>id.startsWith(side+'_brow'));
      this.cheeks[side]=wrap('organic-'+side+'-cheek',id=>id===side+'_moustache');
    }
    this.mouth=wrap('organic-mouth',id=>/^(mouth_|tongue)/.test(id));
    this.nose=wrap('organic-nose',id=>id==='nose');
  }
  apply(motion,blink,gaze){
    this.mouth.setAttribute('transform',`translate(725 550) scale(${motion.mouthWidth} 1) translate(-725 -550)`);
    this.nose.setAttribute('transform',`translate(0 ${motion.noseY})`);
    for(const side of ['left','right']){
      const upper=this.root.querySelector('#'+side+'_eye_upper').getBBox();
      const lower=this.root.querySelector('#'+side+'_eye_lower').getBBox();
      const cx=upper.x+upper.width/2,cy=(upper.y+lower.y+lower.height)/2;
      const sy=Math.max(.035,motion.eyeScale*(1-.965*blink));
      this.eyes[side].setAttribute('transform',`translate(0 ${motion.cheekY*.55}) translate(${cx} ${cy}) scale(1 ${sy}) translate(${-cx} ${-cy})`);
      this.brows[side].setAttribute('transform',`translate(0 ${motion.browY+blink*1.8})`);
      this.cheeks[side].setAttribute('transform',`translate(0 ${motion.cheekY})`);
      if(gaze.weight<.0001)continue;
      const pupil=this.root.querySelector('#'+side+'_pupil');
      const [a,b,c,d,e,f]=ellipseMatrix(pupil),px=Number(pupil.getAttribute('cx')),py=Number(pupil.getAttribute('cy'));
      // Move iris and its clipping geometry together; the eye opening stays put.
      const dx=(cx+gaze.x*upper.width*.28-(a*px+c*py+e))*gaze.weight;
      const height=Math.max(24,lower.y+lower.height-upper.y);
      const dy=(cy+gaze.y*height*.38-(b*px+d*py+f))*gaze.weight;
      for(const suffix of ['pupil','pupil_geometry','highlight','secondary_highlight']){
        const node=this.root.querySelector('#'+side+'_'+suffix);
        if(node)node.setAttribute('transform',`translate(${dx} ${dy}) `+(node.getAttribute('transform')||''));
      }
      const heart=this.root.querySelector('#'+side+'_heart');
      if(heart){const d=numericAttribute(heart.getAttribute('d'));let value=d.parts[0];
        d.values.forEach((v,i)=>value+=(v+(i%2?dy:dx)).toFixed(4)+d.parts[i+1]);heart.setAttribute('d',value);}
    }
  }
}

export function blinkAt(schedule,t){
  let strength=0;
  for(const center of schedule){const d=t-center;
    if(d>=-.07 && d<0)strength=Math.max(strength,ease((d+.07)/.07));
    else if(d>=0 && d<.13)strength=Math.max(strength,1-ease(d/.13));
  }
  return strength;
}
