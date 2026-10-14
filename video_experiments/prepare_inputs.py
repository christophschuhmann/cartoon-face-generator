"""Render real SVG archetypes and intermediate poses as LTX conditioning images."""
from pathlib import Path
import json
from cartoon_face.emotion_library import emotion_pose40
from cartoon_face.animation import interpolate_pose
from cartoon_face.model import save_pose,points,set_xy,topology,WIDTH,HEIGHT,refresh_states
from cartoon_face.renderer import render_files,render_svg,rasterize
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent


def prepare():
    destination=ROOT/'inputs';destination.mkdir(exist_ok=True)
    pairs=[('happy_to_angry','amusement','anger',
        "The cartoon speaks German with a friendly, gently comic male voice. First he smiles warmly and says, 'Das ist ja wunderbar!' "
        "Then his eyebrows lower and his eyes narrow as he becomes softly indignant, saying, 'Moment, das ist unfair!' He holds the final angry but endearing expression."),
        ('sad_to_hopeful','sadness','hope',
        "The cartoon speaks German in a soft, expressive male voice. First he looks sad and says, 'Heute ist alles schwer.' "
        "His eyebrows and gaze gently lift, his mouth becomes an encouraging smile, and he says with renewed hope, 'Aber ich gebe nicht auf.'"),
        ('doubt_to_laughter','doubt','amusement',
        "The cartoon speaks German in a warm, gently comic male voice. First he raises one skeptical eyebrow and says, 'Meinst du das ernst?' "
        "Then his eyes smile and his mouth opens into amusement as he says, 'Na gut, ich muss lachen.' He finishes with a soft chuckle."),
        ('fear_to_relief','fear','relief',
        "The cartoon speaks German in a gentle comic male voice. First his eyes widen with mild surprise and fear as he says, 'Oh, was war das?' "
        "Then he exhales, his eyebrows soften, his eyes relax, and he smiles with relief, saying, 'Puh, alles wieder gut.'")]
    # The published taxonomy names the category 'relief', not an inferred emotion.
    common=("A fixed close-up of exactly the same flat black-and-white cartoon face as the reference images, "
        "drawn in smooth black ink on a completely uniform pure white background. Two large expressive outlined eyes, "
        "black pupils with small white highlights, thick curved eyebrows, a tiny nose, two distinctive curled moustache-like "
        "cheek lines, and a small speaking mouth. The face stays at exactly the same size and position. The camera is locked "
        "and motionless for the entire single shot. Only eyelids, eyebrows, pupils and mouth move naturally. "
        "The background stays pure white, the artwork remains monochrome and minimal. No scene change, text, head outline or body. ")
    rows=[]
    pairs.extend([
        ('happy_to_angry_clear','amusement','anger',pairs[0][3]),
        ('fear_to_relief_margin','fear','relief',pairs[3][3])])
    for slug,start_name,end_name,script in pairs:
        start=emotion_pose40(start_name);end=emotion_pose40(end_name);directory=destination/slug;directory.mkdir(exist_ok=True)
        padding=.1 if slug.endswith(('clear','margin')) else 0.
        if slug.endswith('clear'):
            # A video-only directing pose: slope the inner brow down more clearly.
            # Shared catalog/training recipes remain unchanged; all IDs are retained.
            for side in ('left','right'):
                q=points(end,side+'_brow');old=q[-1].copy()
                q[:,1]=[145,151,177,215,250]
                for name,point in zip(topology()['components'][side+'_brow']['anchors'],q):set_xy(end,name,point)
                accent=points(end,side+'_brow_accent')+q[-1]-old
                for name,point in zip(topology()['components'][side+'_brow_accent']['anchors'],accent):set_xy(end,name,point)
            end['provenance']['video_directing']='Lower inner eyebrows; shared emotion catalog untouched.'
            refresh_states(end)
        for label,t in [('start',0.),('quarter',.25),('middle',.5),('three_quarters',.75),('end',1.)]:
            pose=start if t==0 else end if t==1 else interpolate_pose(start,end,t)
            pose['canvas']={'width':1024,'height':512}
            save_pose(pose,directory/f'{label}.json');render_files(pose,directory/f'{label}.svg',directory/f'{label}.png')
            if padding:
                # Affine SVG composition adds breathing room, without editing pixels.
                # Pose JSON stays in rig space; conditioning_transform.json records
                # the exact conversion to this conditioning image's coordinates.
                root=ET.fromstring(render_svg(pose));ns='{http://www.w3.org/2000/svg}'
                group=ET.Element(ns+'g',{'transform':f'translate({WIDTH*padding} {HEIGHT*padding}) scale({1-2*padding})'})
                for element in list(root):
                    if element.tag not in (ns+'title',ns+'defs',ns+'rect'):root.remove(element);group.append(element)
                root.append(group);svg=ET.tostring(root,encoding='unicode')
                (directory/f'{label}.svg').write_text(svg+'\n');rasterize(svg).save(directory/f'{label}.png')
        (directory/'conditioning_transform.json').write_text(json.dumps({'coordinate_system':'normalized',
            'scale':1-2*padding,'translate':[padding,padding],
            'meaning':'conditioning_xy = pose_xy * scale + translate; pose JSON remains in canonical rig space'},indent=2)+'\n')
        prompt=common+script
        (directory/'prompt.txt').write_text(prompt+'\n')
        rows.append({'slug':slug,'from':start_name,'to':end_name,'prompt':prompt,'input_directory':str(directory.relative_to(ROOT))})
    (ROOT/'input_manifest.json').write_text(json.dumps({'renderer':'shared cartoon_face Python SVG renderer','pairs':rows},ensure_ascii=False,indent=2)+'\n')
    return rows


if __name__=='__main__':
    print(json.dumps(prepare(),ensure_ascii=False,indent=2))
