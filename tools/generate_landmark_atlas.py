"""Build vector documentation figures from the real renderer plus numbered anchors."""
from pathlib import Path
import html
import xml.etree.ElementTree as ET
from cartoon_face.model import topology,load_pose,xy
from cartoon_face.renderer import render_svg,rasterize
from cartoon_face.reference import ROOT

NS='{http://www.w3.org/2000/svg}'
ET.register_namespace('',NS[1:-1])
OUT=ROOT/'docs/landmarks';OUT.mkdir(exist_ok=True)
BOOK=topology()['keypoints']

def color(region):
    if 'brow' in region:return '#7c3aed'
    if 'moustache' in region:return '#087f72'
    if 'pupil' in region or 'highlight' in region:return '#df8b00'
    if 'eye' in region or 'lash' in region or 'lid' in region or 'hatching' in region:return '#176cd4'
    return '#cc354d'


def figure(name,source,ids,overview=False):
    p=load_pose(ROOT/f'poses/{source}.json');selected=[k for k in BOOK if k['id'] in ids]
    coords=[xy(p,k['name']) for k in selected]
    xs=[q[0] for q in coords];ys=[q[1] for q in coords]
    box=(0,0,1450,750) if overview else (max(0,min(xs)-55),max(0,min(ys)-55),min(1450,max(xs)+55),min(750,max(ys)+55))
    x0,y0,x1,y1=box;width=x1-x0;height=y1-y0
    root=ET.fromstring(render_svg(p));root.set('viewBox',f'{x0} {y0} {width} {height}')
    root.set('width','1200');root.set('height',str(round(1200*height/width)))
    for child in root:
        if child.tag not in (NS+'defs',NS+'title',NS+'rect'):child.set('opacity','.35')
    group=ET.SubElement(root,NS+'g',{'id':'documentation-landmarks'})
    used=[]
    for k,q in zip(selected,coords):
        visible=p['keypoints'][k['name']]['state']=='visible';c=color(k['region']) if visible else '#6b7280'
        radius=4.8 if overview else 3.4
        circle=ET.SubElement(group,NS+'circle',{'cx':str(q[0]),'cy':str(q[1]),'r':str(radius),'fill':c,'stroke':'white','stroke-width':'1'})
        ET.SubElement(circle,NS+'title').text=f"{k['id']}: {k['name']} — {k['meaning']}"
        size=13 if overview else 10
        best=None
        for dx,dy in [(8,-8),(8,17),(-25,-8),(-25,17),(9,-24),(-27,-24),(9,31),(-27,31)]:
            rect=(q[0]+dx,q[1]+dy-size,q[0]+dx+size*1.9,q[1]+dy)
            collisions=sum(not(rect[2]<r[0] or rect[0]>r[2] or rect[3]<r[1] or rect[1]>r[3]) for r in used)
            score=collisions*100+abs(dx)+abs(dy)
            if best is None or score<best[0]:best=(score,dx,dy,rect)
        _,dx,dy,rect=best;used.append(rect)
        ET.SubElement(group,NS+'line',{'x1':str(q[0]),'y1':str(q[1]),'x2':str(q[0]+dx),'y2':str(q[1]+dy-3),'stroke':c,'stroke-width':'.6'})
        ET.SubElement(group,NS+'text',{'x':str(q[0]+dx),'y':str(q[1]+dy),'font-size':str(size),'font-family':'sans-serif','font-weight':'bold','fill':c}).text=str(k['id'])
    svg=ET.tostring(root,encoding='unicode');(OUT/f'{name}.svg').write_text(svg);rasterize(svg).save(OUT/f'{name}.png')

figure('overview','smile',range(101),True)
figure('brows','smile',[k['id'] for k in BOOK if 'brow' in k['region']])
for side in ('left','right'):
    figure('eye_'+side,'smile',[k['id'] for k in BOOK if k['name'].startswith(side+'_') and not any(s in k['region'] for s in ('brow','moustache'))])
figure('moustache','smile',[k['id'] for k in BOOK if 'moustache' in k['region']])
figure('mouth_nose_tongue','tongue',range(80,101))
print('Generated six numbered SVG/PNG landmark figures')
