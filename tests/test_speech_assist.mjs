import assert from 'node:assert/strict';
import {test} from 'node:test';
import {SpeechAssist} from '../webcam_mapper/static/speech-assist.mjs';
import {speechOpening,envelopeAt,performanceWeights} from '../webcam_mapper/static/audio-player.mjs';
import {coupledMotion,viewerDirection,blinkAt,blinkSchedule,GazeFollower} from '../webcam_mapper/static/audio-organic.mjs';

test('speech bridge needs repeated movement and expires at exactly its deadline',()=>{
  const s=new SpeechAssist();s.enabled=true;
  s.observe(0,0);s.observe(.3,100);s.observe(.02,200);
  assert.equal(s.sample(210),null);
  s.observe(.3,300);s.observe(.02,400);
  assert.ok(s.sample(470).openness>0);
  assert.ok(s.sample(790));assert.equal(s.sample(800),null);
  s.observe(.02,900);assert.equal(s.sample(920),null);
});

test('speech impulses drive cheeks, lids and head together without idle mouth movement',()=>{
  const quiet=coupledMotion(0,0,.6,.8),spoken=coupledMotion(.4,.3,.6,.8);
  assert.ok(quiet.cheekY===0);assert.equal(quiet.eyeScale,1);
  assert.ok(spoken.cheekY<0 && spoken.browY<0 && spoken.eyeScale<1 && spoken.headY<0);
  assert.deepEqual(coupledMotion(.4,.3,.6,.8,0),coupledMotion(0,0,.6,.8,0));
});
test('viewer directions match mirrored webcam coordinates and vertical screen direction',()=>{
  assert.ok(viewerDirection({x:.2,y:.2}).x>0);
  assert.ok(viewerDirection({x:.8,y:.7}).x<0);
  assert.ok(viewerDirection({x:.5,y:.2}).y<0);
  assert.ok(viewerDirection({x:.5,y:.7}).y>0);
  const schedule=blinkSchedule([{start:2,end:2.8}],10);
  assert.equal(blinkAt(schedule,schedule[0]),1);assert.equal(blinkAt(schedule,0),0);
});

test('negative speech keeps tense brows, restrained cheeks and synchronized articulation',()=>{
  const happy=coupledMotion(.4,.3,.8,.9);
  const angry=coupledMotion(.4,.3,.8,.9,1,{aggression:.8,negative:.9});
  assert.ok(angry.browY>0 && happy.browY<0);
  assert.ok(Math.abs(angry.cheekY)<Math.abs(happy.cheekY)*.3);
  assert.ok(angry.eyeScale<happy.eyeScale);
  assert.equal(angry.drive,happy.drive);assert.equal(angry.mouthWidth,happy.mouthWidth);
  const sad=coupledMotion(.4,.3,.4,.9,1,{aggression:0,negative:1});
  assert.ok(sad.browY<0); // Worried/sad brows stay raised, unlike anger.
  assert.equal(coupledMotion(0,0,.8,.9,1,{aggression:1,negative:1}).browY,0);
});
test('three overlapping short emotion segments do not jump at boundaries',()=>{
  const segments=[{start:1,end:1.12},{start:1.13,end:1.25},{start:1.26,end:1.4}];
  for(const s of segments)for(const t of [s.start,s.end])for(const target of segments){
    const weight=at=>performanceWeights(segments,at).find(v=>v.segment===target)?.weight||0;
    assert.ok(Math.abs(weight(t-1e-6)-weight(t+1e-6))<.0001);
  }
});

test('gaze eyes lead the head, reject jitter, and return gently after tracking loss',()=>{
  const gaze=new GazeFollower();gaze.observe({x:.2,y:.2},0);
  for(let t=0;t<=200;t+=20)gaze.step(t,.02);
  assert.ok(gaze.state.x>gaze.state.headX*1.5);
  assert.ok(Math.abs(gaze.state.y)>Math.abs(gaze.state.headY)*1.5);
  const target={...gaze.target};
  for(let t=220;t<=800;t+=20){
    gaze.observe({x:.2+(t%40?.003:-.003),y:.2},t);gaze.step(t,.02);
  }
  assert.deepEqual(gaze.target,target);
  const before=gaze.state.x;gaze.observe(null,900);gaze.step(900,.02);
  assert.ok(gaze.state.x>=before); // Brief missed detections retain eye contact.
  for(let t=1000;t<=6000;t+=20)gaze.step(t,.02);
  assert.ok(Math.abs(gaze.state.x)<.001 && Math.abs(gaze.state.headX)<.002 && gaze.state.weight<.001);
  gaze.observe({x:NaN,y:Infinity},6010);assert.deepEqual(gaze.target,target);
  gaze.observe({x:-100,y:100},6020);
  for(let t=6020;t<6800;t+=20)gaze.step(t,.02);
  assert.ok(Object.values(gaze.state).every(v=>Number.isFinite(v) && Math.abs(v)<=1));
});
test('a held-open mouth, jitter, tongue and lost tracking never cause speech loops',()=>{
  for(const value of [.3,.008]){
    const s=new SpeechAssist();s.enabled=true;
    for(let i=0;i<10;i++)s.observe(i%2?value:Math.max(0,value-.01),i*100);
    assert.equal(s.sample(950),null);
  }
  const s=new SpeechAssist();s.enabled=true;
  for(let i=0;i<6;i++)s.observe(i%2?.3:.01,i*100);
  assert.ok(s.sample(570));s.observe(.1,600,{tongue:.6});assert.equal(s.sample(620),null);
});
test('audio articulation is silent outside words; loudness and arousal increase it',()=>{
  const words=[{start:2,end:4}],pattern={tempo:3,aperture:1};
  const quiet={step:.1,values:Array(60).fill(.2)},loud={step:.1,values:Array(60).fill(.8)};
  assert.equal(speechOpening(1,words,loud,pattern,.8),0);
  assert.equal(speechOpening(4.1,words,loud,pattern,.8),0);
  assert.ok(speechOpening(2.5,words,loud,pattern,.5)>speechOpening(2.5,words,quiet,pattern,.5));
  assert.equal(envelopeAt({step:1,values:[0,1]},.5),.5);
  assert.equal(speechOpening(2.5,words,{step:.1,values:Array(60).fill(0)},pattern,.8),0);
});
test('expression weights remain continuous across pauses and short segments',()=>{
  for(const gap of [0,.2,.5,1]){
    const a={start:1,end:2},b={start:2+gap,end:2.1+gap},segments=[a,b];
    const weight=(t,s)=>performanceWeights(segments,t).filter(x=>x.segment===s).reduce((v,x)=>v+x.weight,0);
    assert.ok(Math.abs(weight(b.start-1e-6,a)-weight(b.start+1e-6,a))<1e-4);
    for(let t=0;t<4;t+=.017){
      const values=performanceWeights(segments,t).map(x=>x.weight);
      assert.ok(values.every(v=>v>=0 && v<=1));assert.ok(Math.abs(values.reduce((a,b)=>a+b,0)-1)<1e-9);
    }
    assert.ok(Math.abs(weight(b.end-1e-6,b)-weight(b.end+1e-6,b))<1e-4);
  }
});
