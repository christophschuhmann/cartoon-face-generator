import assert from 'node:assert/strict';
import {test} from 'node:test';
import {FaceProjection,viewerHead,viewerEyes} from '../webcam_mapper/static/head-follow.mjs';

test('head follow is optional and combines all eight viewer directions',()=>{
  const gaze={headX:.8,headY:-.7,weight:1};
  assert.ok(Object.values(viewerHead(gaze,0)).every(v=>v===0));
  assert.ok(Object.values(viewerHead({...gaze,weight:0},1)).every(v=>v===0));
  for(const x of [-1,0,1])for(const y of [-1,0,1]){
    const head=viewerHead({headX:x,headY:y,weight:1},1);
    const [px,py]=new FaceProjection(head.yaw,head.pitch).point(725,375,true);
    assert.equal(Math.sign(px-725),x);assert.equal(Math.sign(py-375),y);
    assert.ok(Math.abs(head.yaw)<=.48 && Math.abs(head.pitch)<=.30);
  }
});

test('neutral projection preserves geometry and turns retain nose depth',()=>{
  const neutral=new FaceProjection(0,0);
  for(const point of [[0,0],[725,375],[1450,750],[320,235]]){
    const projected=neutral.point(...point);
    projected.forEach((v,i)=>assert.ok(Math.abs(v-point[i])<1e-10));
  }
  const turn=new FaceProjection(.48,0);
  assert.ok(turn.point(725,375,true)[0]>turn.point(725,375)[0]);
  assert.ok(new FaceProjection(0,-.30).point(725,375,true)[1]<375);
});

test('settled eyes counter-turn toward a viewer in front in all eight directions',()=>{
  for(const x of [-1,0,1])for(const y of [-1,0,1]){
    const gaze={x,y,headX:x,headY:y,weight:1};
    const head=viewerHead(gaze,1),eyes=viewerEyes(gaze,head,1);
    if(x)assert.equal(Math.sign(eyes.x),-x);
    if(y)assert.equal(Math.sign(eyes.y),-y);
    assert.ok(Math.abs(eyes.x)<.6 && Math.abs(eyes.y)<.5);
    assert.deepEqual(viewerEyes(gaze,head,0),gaze); // Eyes-only behavior stays available.
  }
});

test('eyes lead a turn, counter it once settled, and compensate tilted heads',()=>{
  const moving={x:1,y:0,headX:0,headY:0,weight:1};
  assert.ok(viewerEyes(moving,viewerHead(moving,1),1).x>0);
  const arrived={...moving,headX:1};
  assert.ok(viewerEyes(arrived,viewerHead(arrived,1),1).x<0);
  const straight={x:0,y:0,headX:1,headY:0,weight:1};
  assert.ok(viewerEyes(straight,viewerHead(straight,1),1).x<0);
  const tilted=viewerEyes(moving,viewerHead(moving,1),1,Math.PI/6);
  assert.ok(tilted.x>0 && tilted.y<0); // Counter a clockwise screen-space tilt.
  for(let amount=0;amount<=1;amount+=.01){
    const eyes=viewerEyes(arrived,viewerHead(arrived,amount),amount);
    assert.ok(Number.isFinite(eyes.x) && Number.isFinite(eyes.y));
    assert.ok(Math.abs(eyes.x)<=1 && Math.abs(eyes.y)<=1);
  }
});

test('ellipse projection composes existing transforms and preserves its projected center',()=>{
  const projection=new FaceProjection(.48,.3),matrix=[.92,.2,-.18,.95,24,-8];
  const cx=410,cy=280,result=projection.ellipse(matrix,cx,cy);
  const expected=projection.point(matrix[0]*cx+matrix[2]*cy+matrix[4],matrix[1]*cx+matrix[3]*cy+matrix[5]);
  assert.ok(Math.abs(result[0]*cx+result[2]*cy+result[4]-expected[0])<1e-8);
  assert.ok(Math.abs(result[1]*cx+result[3]*cy+result[5]-expected[1])<1e-8);
  assert.ok(result.every(Number.isFinite));
  assert.ok(result[0]*result[3]-result[1]*result[2]>0); // No flipped irises.
  const left=projection.ellipse([1,0,0,1,0,0],400,300);
  const right=projection.ellipse([1,0,0,1,0,0],1050,300);
  assert.ok(Math.abs(left[0]-right[0])>.05); // Near/far perspective, not a flat squash.
});
