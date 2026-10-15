"""The ONLY renderer: CLI, optimizer, and local editor all use this implementation."""
import html,io
import copy
import math
import numpy as np
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image
from .model import validate_pose,WIDTH,HEIGHT,topology
from .components import *
from .projection import FaceProjection

def all_shapes(p):
    s=[]
    for side in ('left','right'):
        s+=render_eyebrow(p,side)+render_eye(p,side)+render_details(p,side)+render_moustache(p,side)
    return s+render_nose(p)+render_mouth(p)

def shape_xml(s):
    common=f'id="{s["id"]}" fill="{s["fill"]}" opacity="{s.get("opacity",1):.6f}"'
    if 'clip' in s and s['kind']=='path':common+=f' clip-path="url(#{s["clip"]})"'
    if 'translation' in s:common+=f' transform="translate({s["translation"][0]:.5f} {s["translation"][1]:.5f})"'
    if s.get('stroke'):common+=f' stroke="{s["stroke"]}" stroke-width="{s["stroke_width"]:.5f}" stroke-linecap="round" stroke-linejoin="round"'
    if s['kind']=='path':return f'<path {common} d="{s["d"]}"/>'
    x,y=s['center']
    transform='matrix('+ ' '.join(f'{v:.7f}' for v in s['matrix']) +')' if 'matrix' in s else f'rotate({s["angle"]:.5f} {x:.5f} {y:.5f})'
    element=f'<ellipse {common} cx="{x:.5f}" cy="{y:.5f}" rx="{s["rx"]:.5f}" ry="{s["ry"]:.5f}" transform="{transform}"/>'
    # Clip coordinates are canonical canvas coordinates. Putting the clip on a
    # rotated ellipse would rotate the lid opening too, producing angular pupils
    # outside their lids. Keep the clip on an untransformed parent instead.
    if 'clip' in s:element=f'<g clip-path="url(#{s["clip"]})">{element}</g>'
    return element

def head_transform(p):
    head=p.get('head_pose',{})
    yaw=float(np.clip(head.get('yaw',0),-.85,.85));pitch=float(np.clip(head.get('pitch',0),-.55,.55));roll=float(np.clip(head.get('roll',0),-.55,.55))
    if head.get('projection')=='curved_perspective_v2':yaw=pitch=0.
    # Project a cartoon face plane, then apply roll around its centre. A bounded
    # depth offset on the nose makes yaw readable without changing the rig IDs.
    fit=min(1.,660/(600*abs(math.cos(roll))+1150*abs(math.sin(roll))))
    sx=math.cos(yaw)*fit;sy=math.cos(pitch)*fit;shear=-math.sin(yaw)*math.sin(pitch)*fit
    c,s=math.cos(roll),math.sin(roll)
    a=c*sx;b=s*sx;cc=c*shear-s*sy;d=s*shear+c*sy
    cx,cy=WIDTH/2,HEIGHT/2
    tx=cx-a*cx-cc*cy+math.sin(yaw)*28
    ty=cy-b*cx-d*cy+math.sin(pitch)*24
    return f'matrix({a:.7f} {b:.7f} {cc:.7f} {d:.7f} {tx:.5f} {ty:.5f})'


def render_svg(p,width=None,height=None,live=False,id_prefix=''):
    if live:
        p=copy.copy(p)
        p['_live_preview']=True
    if not live:validate_pose(p)
    w=p['canvas']['width'] if width is None else width;h=p['canvas']['height'] if height is None else height
    if not all(isinstance(v,int) and 1<=v<=8192 for v in (w,h)):raise ValueError('Render dimensions outside 1..8192')
    defs=[]
    head=p.get('head_pose')
    projection=FaceProjection(head) if head and head.get('projection')=='curved_perspective_v2' else None
    if projection:
        p=copy.copy(p)
        p['_projection']=projection
    for side in ('left','right'):
        opening=eye_opening(p,side)
        defs.append(f'<clipPath id="{side}_eye_clip"><path d="{opening}"/></clipPath>')
        pupil=ellipse(p,side+'_pupil');pupil['fill']='white';pupil['opacity']=1;pupil['id']=side+'_pupil_geometry'
        if projection:pupil=projection.shape(pupil)
        defs.append(f'<clipPath id="{side}_pupil_clip">{shape_xml(pupil)}</clipPath>')
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {WIDTH} {HEIGHT}" preserveAspectRatio="none">',
      '<title>'+html.escape(p.get('name','Cartoon face'))+'</title>',f'<defs>{"".join(defs)}</defs>',f'<rect width="{WIDTH}" height="{HEIGHT}" fill="white"/>']
    if head:parts.append(f'<g id="avatar-head" transform="{head_transform(p)}">')
    shapes=all_shapes(p)
    for shape in shapes:
        if projection and shape['kind']=='ellipse':shape=projection.shape(shape)
        elif head and not projection and shape['id']=='nose':shape['translation']=[math.sin(head['yaw'])*75,math.sin(head['pitch'])*45]
        element=shape_xml(shape)
        # Highlights are the intersection of pupil AND opening. A glint must
        # never remain floating on a shut lid or above an upward-looking iris.
        if head and shape.get('clip','').endswith('_pupil_clip'):
            side=shape['id'].split('_')[0]
            element=f'<g clip-path="url(#{side}_eye_clip)">{element}</g>'
        parts.append(element)
    if head:parts.append('</g>')
    parts.append('</svg>')
    result='\n'.join(parts)+'\n'
    if id_prefix:
        if not id_prefix.replace('-','').replace('_','').isalnum():raise ValueError('Invalid SVG ID prefix')
        result=result.replace('id="',f'id="{id_prefix}').replace('url(#',f'url(#{id_prefix}')
    return result

def rasterize(svg,width=None,height=None):
    # Live SVG rendering needs no native Cairo installation (especially Windows).
    import cairosvg
    data=cairosvg.svg2png(bytestring=svg.encode(),output_width=width,output_height=height,background_color='white')
    return Image.open(io.BytesIO(data)).convert('RGB')

def render_files(p,svg_path,png_path=None,width=None,height=None):
    svg=render_svg(p,width,height);dest=Path(svg_path);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(svg)
    if png_path:rasterize(svg).save(png_path)
    return svg
