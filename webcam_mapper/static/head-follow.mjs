// Same shallow ellipsoid as cartoon_face/projection.py. Apply to interpolated
// SVG geometry so existing audio analyses and all 101 rig points stay usable.
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));

export function viewerHead(gaze,amount){
  const strength=clamp(amount,0,1)*gaze.weight;
  const x=clamp(gaze.headX,-1,1)*strength,y=clamp(gaze.headY,-1,1)*strength;
  return {x,y,yaw:x*.48,pitch:y*.30,roll:x*(1.6+1.4*Math.max(0,y))};
}

// Aim at a shallow cone IN FRONT of the screen. Subtract the head's actual
// rotation in 3D: a turned head needs a counter-gaze to keep addressing a nearby
// viewer. Camera coordinates alone are not a gaze angle toward the room's side.
export function viewerEyes(gaze,head,amount,roll=head.roll*Math.PI/180){
  const follow=clamp(amount,0,1);
  if(!follow)return {...gaze};
  const tx=clamp(gaze.x,-1,1)*.28,ty=clamp(gaze.y,-1,1)*.18;
  const cr=Math.cos(roll),sr=Math.sin(roll),cp=Math.cos(head.pitch),sp=Math.sin(head.pitch);
  const cy=Math.cos(head.yaw),sy=Math.sin(head.yaw);
  // Inverse roll, pitch, then yaw, matching the curved face projection.
  const rx=cr*tx+sr*ty,ry=-sr*tx+cr*ty;
  const py=cp*ry-sp,pz=sp*ry+cp;
  const localX=cy*rx-sy*pz,localZ=sy*rx+cy*pz;
  const yaw=Math.atan2(localX,localZ),pitch=Math.atan2(py,Math.hypot(localX,localZ));
  const x=clamp(Math.sin(yaw)/Math.sin(.52),-.8,.8);
  const y=clamp(Math.sin(pitch)/Math.sin(.44),-.75,.75);
  return {...gaze,x:gaze.x+(x-gaze.x)*follow,y:gaze.y+(y-gaze.y)*follow};
}

export class FaceProjection {
  constructor(yaw,pitch){
    yaw=clamp(yaw,-.85,.85);pitch=clamp(pitch,-.55,.55);
    this.cy=Math.cos(yaw);this.sy=Math.sin(yaw);
    this.cp=Math.cos(pitch);this.sp=Math.sin(pitch);
  }
  point(px,py,nose=false){
    const x=px-725,y=py-375,radius=(x/820)**2+(y/650)**2;
    const z=245*Math.sqrt(Math.max(.16,1-radius))+(nose?110:0);
    let xx=this.cy*x+this.sy*z,zz=-this.sy*x+this.cy*z;
    let yy=this.cp*y+this.sp*zz;zz=-this.sp*y+this.cp*zz;
    const perspective=(1650-z)/(1650-zz);
    return [725+xx*perspective*(1+.24*this.sy**2),375+yy*perspective];
  }
  // Compose the local tangent with the ellipse's existing rotation/projection.
  // Its clip copy gets the identical matrix, preserving pupil occlusion.
  ellipse(matrix,cx,cy){
    const [a,b,c,d,e,f]=matrix,x=a*cx+c*cy+e,y=b*cx+d*cy+f;
    const p=this.point(x,y),xp=this.point(x+1,y),xm=this.point(x-1,y);
    const yp=this.point(x,y+1),ym=this.point(x,y-1);
    const ja=(xp[0]-xm[0])/2,jb=(xp[1]-xm[1])/2,jc=(yp[0]-ym[0])/2,jd=(yp[1]-ym[1])/2;
    const aa=ja*a+jc*b,bb=jb*a+jd*b,cc=ja*c+jc*d,dd=jb*c+jd*d;
    return [aa,bb,cc,dd,p[0]-aa*cx-cc*cy,p[1]-bb*cx-dd*cy];
  }
}

export function ellipseMatrix(node){
  const transforms=node.transform.baseVal;
  let result=[1,0,0,1,0,0];
  for(let i=0;i<transforms.numberOfItems;i++){
    const m=transforms.getItem(i).matrix,[a,b,c,d,e,f]=result;
    result=[a*m.a+c*m.b,b*m.a+d*m.b,a*m.c+c*m.d,b*m.c+d*m.d,a*m.e+c*m.f+e,b*m.e+d*m.f+f];
  }
  return result;
}
