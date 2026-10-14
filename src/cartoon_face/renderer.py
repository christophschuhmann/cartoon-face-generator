"""The ONLY renderer: CLI, optimizer, and local editor all use this implementation."""
import html,io
from pathlib import Path
import xml.etree.ElementTree as ET
import cairosvg
from PIL import Image
from .model import validate_pose,WIDTH,HEIGHT,topology
from .components import *

def all_shapes(p):
    s=[]
    for side in ('left','right'):
        s+=render_eyebrow(p,side)+render_eye(p,side)+render_details(p,side)+render_moustache(p,side)
    return s+render_nose(p)+render_mouth(p)

def shape_xml(s):
    common=f'id="{s["id"]}" fill="{s["fill"]}" opacity="{s.get("opacity",1):.6f}"'
    if 'clip' in s and s['kind']=='path':common+=f' clip-path="url(#{s["clip"]})"'
    if s.get('stroke'):common+=f' stroke="{s["stroke"]}" stroke-width="{s["stroke_width"]:.5f}" stroke-linecap="round" stroke-linejoin="round"'
    if s['kind']=='path':return f'<path {common} d="{s["d"]}"/>'
    x,y=s['center'];element=f'<ellipse {common} cx="{x:.5f}" cy="{y:.5f}" rx="{s["rx"]:.5f}" ry="{s["ry"]:.5f}" transform="rotate({s["angle"]:.5f} {x:.5f} {y:.5f})"/>'
    # Clip coordinates are canonical canvas coordinates. Putting the clip on a
    # rotated ellipse would rotate the lid opening too, producing angular pupils
    # outside their lids. Keep the clip on an untransformed parent instead.
    if 'clip' in s:element=f'<g clip-path="url(#{s["clip"]})">{element}</g>'
    return element

def render_svg(p,width=None,height=None):
    validate_pose(p);w=p['canvas']['width'] if width is None else width;h=p['canvas']['height'] if height is None else height
    if not all(isinstance(v,int) and 1<=v<=8192 for v in (w,h)):raise ValueError('Render dimensions outside 1..8192')
    defs=[]
    for side in ('left','right'):
        defs.append(f'<clipPath id="{side}_eye_clip"><path d="{eye_opening(p,side)}"/></clipPath>')
        pupil=ellipse(p,side+'_pupil');pupil['fill']='white';pupil['opacity']=1;pupil['id']=side+'_pupil_geometry'
        defs.append(f'<clipPath id="{side}_pupil_clip">{shape_xml(pupil)}</clipPath>')
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {WIDTH} {HEIGHT}" preserveAspectRatio="none">',
      '<title>'+html.escape(p.get('name','Cartoon face'))+'</title>',f'<defs>{"".join(defs)}</defs>',f'<rect width="{WIDTH}" height="{HEIGHT}" fill="white"/>']
    parts += [shape_xml(s) for s in all_shapes(p)];parts.append('</svg>')
    return '\n'.join(parts)+'\n'

def rasterize(svg,width=None,height=None):
    data=cairosvg.svg2png(bytestring=svg.encode(),output_width=width,output_height=height,background_color='white')
    return Image.open(io.BytesIO(data)).convert('RGB')

def render_files(p,svg_path,png_path=None,width=None,height=None):
    svg=render_svg(p,width,height);dest=Path(svg_path);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(svg)
    if png_path:rasterize(svg).save(png_path)
    return svg
