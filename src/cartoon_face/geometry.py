"""Smooth cubic geometry. Widths and tangent handles are rig data, not landmarks."""
import numpy as np
from scipy.interpolate import PchipInterpolator, CubicSpline

def tangents(points, scales=None):
    p=np.asarray(points,float);d=np.empty_like(p)
    d[0]=p[1]-p[0];d[-1]=p[-1]-p[-2]
    if len(p)>2:
        # Centripetal chord weighting prevents large overshoots on tightly curled tips.
        a=np.linalg.norm(p[1:-1]-p[:-2],axis=1);b=np.linalg.norm(p[2:]-p[1:-1],axis=1)
        d[1:-1]=((p[1:-1]-p[:-2])*b[:,None]+(p[2:]-p[1:-1])*a[:,None]) / np.maximum(a+b,1e-6)[:,None]
    if scales is not None:d*=np.asarray(scales)[:,None]
    return d

def cubic_segments(points, scales=None, end_tangents=None):
    p=np.asarray(points,float);d=tangents(p,scales)
    if end_tangents is not None:d[[0,-1]]=np.asarray(end_tangents,float)
    return np.stack([p[:-1],p[:-1]+d[:-1]/3,p[1:]-d[1:]/3,p[1:]],axis=1)

def sample_cubics(segments, samples=12):
    t=np.linspace(0,1,samples,endpoint=False)[None,:,None];s=np.asarray(segments)
    p=(1-t)**3*s[:,None,0]+3*(1-t)**2*t*s[:,None,1]+3*(1-t)*t*t*s[:,None,2]+t**3*s[:,None,3]
    d=3*(1-t)**2*(s[:,None,1]-s[:,None,0])+6*(1-t)*t*(s[:,None,2]-s[:,None,1])+3*t*t*(s[:,None,3]-s[:,None,2])
    return np.concatenate([p.reshape(-1,2),s[-1,3:4]]),np.concatenate([d.reshape(-1,2),3*(s[-1,3:4]-s[-1,2:3])])

def ribbon_edges(points, widths, scales=None, samples=8, end_tangents=None):
    s=cubic_segments(points,scales,end_tangents);p,d=sample_cubics(s,samples)
    n=np.stack([-d[:,1],d[:,0]],axis=1)/np.maximum(np.linalg.norm(d,axis=1)[:,None],1e-8)
    u=np.linspace(0,len(points)-1,len(p));w=PchipInterpolator(np.arange(len(points)),np.maximum(widths,0))(u)
    return p+n*w[:,None]/2,p-n*w[:,None]/2

def _split_segments(segments):
    """Exact de Casteljau subdivision, keeping legacy geometry during a fade."""
    q=np.asarray(segments);a=(q[:,0]+q[:,1])/2;b=(q[:,1]+q[:,2])/2;c=(q[:,2]+q[:,3])/2
    d=(a+b)/2;e=(b+c)/2;m=(d+e)/2
    return np.stack([np.stack([q[:,0],a,d,m],axis=1),np.stack([m,e,c,q[:,3]],axis=1)],axis=1).reshape(-1,4,2)


def _smooth_edge(coords,start_direction,end_direction):
    """C2 offset interpolation in arc length, with cap-aligned end directions.

    Dense offset samples keep the fit local even around curls. The centerline
    anchors and positive width profile remain unchanged. Unit end derivatives
    make the edge and circular cap meet tangentially rather than at a tiny kink.
    """
    q=np.asarray(coords);u=np.r_[0,np.cumsum(np.maximum(np.linalg.norm(np.diff(q,axis=0),axis=1),1e-5))]
    unit=lambda d:np.asarray(d)/max(np.linalg.norm(d),1e-8)
    spline=CubicSpline(u,q,axis=0,bc_type=((1,unit(start_direction)),(1,unit(end_direction))))
    deriv=spline(u,1);step=np.diff(u)[:,None]
    return np.stack([q[:-1],q[:-1]+deriv[:-1]*step/3,q[1:]-deriv[1:]*step/3,q[1:]],axis=1)


def outline_cubics(points, widths, scales=None, smoothing=0, end_tangents=None):
    # Offset samples become C1 cubic chains. Only the centerline anchors are semantic.
    a,b=ribbon_edges(points,widths,scales,samples=4,end_tangents=end_tangents)
    p=np.asarray(points,float);d=tangents(p,scales)
    if end_tangents is not None:d[[0,-1]]=np.asarray(end_tangents,float)
    def cap(start,end,center,direction):
        radius=np.linalg.norm(start-center);normal=(start-center)/max(radius,1e-8)
        direction=direction/max(np.linalg.norm(direction),1e-8);tip=center+direction*radius;k=.55228475*radius
        return np.array([[start,start+direction*k,tip+normal*k,tip],[tip,tip-normal*k,end+direction*k,end]])
    edge_a=cubic_segments(a);edge_b=cubic_segments(b[::-1])
    cap_end=cap(a[-1],b[-1],p[-1],d[-1]);cap_start=cap(b[0],a[0],p[0],-d[0])
    legacy=np.concatenate([edge_a,cap_end,edge_b,cap_start])
    if smoothing<=0:return legacy
    a,b=ribbon_edges(points,widths,scales,samples=8,end_tangents=end_tangents)
    smooth=np.concatenate([_smooth_edge(a,d[0],d[-1]),cap_end,
      _smooth_edge(b[::-1],-d[-1],-d[0]),cap_start])
    if smoothing>=1:return smooth
    # Equal segment counts allow a continuous style transition to old poses.
    refined=np.concatenate([_split_segments(edge_a),cap_end,_split_segments(edge_b),cap_start])
    return (1-smoothing)*refined+smoothing*smooth

def fmt(p):return f'{p[0]:.5f},{p[1]:.5f}'

def path_data(segments, close=False):
    s=np.asarray(segments);parts=['M '+fmt(s[0,0])]
    last=s[0,0]
    for q in s:
        if np.linalg.norm(q[0]-last)>1e-6:parts.append('L '+fmt(q[0]))
        parts.append('C '+fmt(q[1])+' '+fmt(q[2])+' '+fmt(q[3]));last=q[3]
    if close:parts.append('Z')
    return ' '.join(parts)

def ribbon_path(points,widths,scales=None,smoothing=0,end_tangents=None):
    return path_data(outline_cubics(points,widths,scales,smoothing,end_tangents),True)


def mouth_curves(upper,lower,upper_scales=None,lower_scales=None,rounding=0):
    """Two open chains sharing mouth corners, with optional rounded tangency.

    Both returned chains run image-left to image-right. Fill traversal reverses
    the lower chain. At rounding=1 both sides meet with a vertical tangent,
    preserving corner landmarks while removing polygonal O-mouth corners.
    """
    u=np.asarray(upper);l=np.vstack([u[0],lower,u[-1]])
    du=tangents(u,upper_scales)[[0,-1]];dl=tangents(l,lower_scales)[[0,-1]]
    height=max(float(l[:,1].max()-u[:,1].min()),6)
    # A quarter of the ellipse circumference spans two 45-degree segments:
    # the matching endpoint derivative is about .8*radius, not .9*diameter.
    width=np.linalg.norm(u[-1]-u[0]);vertical=np.clip(height*.4,5,width*.75)
    target=np.array([[0,-vertical],[0,vertical]])
    du=(1-rounding)*du+rounding*target;dl=(1-rounding)*dl-rounding*target
    return cubic_segments(u,upper_scales,du),cubic_segments(l,lower_scales,dl),du,dl

def contour_path(points,scales=None):return path_data(closed_cubics(points,scales),True)


def closed_cubics(points,scales=None):
    p=np.asarray(points,float);d=(np.roll(p,-1,axis=0)-np.roll(p,1,axis=0))/2
    if scales is not None:d*=np.asarray(scales)[:,None]
    return np.stack([p,p+d/3,np.roll(p,-1,axis=0)-np.roll(d,-1,axis=0)/3,np.roll(p,-1,axis=0)],axis=1)
