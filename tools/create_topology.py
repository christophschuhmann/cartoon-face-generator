"""Generate the checked-in topology: IDs are the explicit list order, never sorted."""
import json
from pathlib import Path
components={};keys=[]
semantics=json.loads(Path('src/cartoon_face/topology/landmark_semantics.json').read_text())
def add(name,kind,suffixes,description,side=None):
    prefix=(side+'_') if side else ''
    names=[prefix+s for s in suffixes]
    components[name]={'kind':kind,'anchors':names,'description':description}
    for n in names:keys.append({'id':len(keys),'name':n,'region':name,'component':name,'meaning':semantics[n[len(prefix):]][0], 'edit_effect':semantics[n[len(prefix):]][1], 'landmark_role':semantics[n[len(prefix):]][2],'optional':kind=='hatching' or ('highlight' in name) or any(x in name for x in ('accent','under','tongue','chin'))})
for side in ('left','right'):
    add(side+'_brow','ribbon',['brow_outer','brow_outer_arch','brow_apex','brow_inner_arch','brow_inner'],'Brauenmittellinie von außen nach innen',side)
    add(side+'_eye_upper','ribbon',['eye_inner_corner','eye_upper_inner','eye_upper_center','eye_upper_outer','eye_outer_corner'],'Oberlidmittellinie von innen nach außen, einschließlich seitlichem Abstieg',side)
    add(side+'_eye_lower','ribbon',['eye_lower_inner_corner','eye_lower_center','eye_lower_outer_corner'],'Unterlidmittellinie von innen nach außen; bewusst separate Endpunkte für den offenen Zeichenstil',side)
    add(side+'_eye_side','derived',['eye_side_end'],'Seitlicher Lidabschluss; Startpunkt wird vom Oberlid übernommen',side)
    add(side+'_lash','derived',['eye_lash_tip'],'Äußere Wimpernspitze; Ansatz wird aus Oberlidkurve abgeleitet',side)
    add(side+'_pupil','ellipse',['pupil_center'],'Pupillenmittelpunkt, Größe im Rig; bei geschlossenem Auge verdeckt',side)
    add(side+'_highlight','ellipse',['highlight_center'],'Primärer runder Reflex; Herz separat aber an derselben Pupille verankert',side)
    add(side+'_secondary_highlight','ellipse',['secondary_highlight_center'],'Sekundärer weißer Reflex mit fester ID',side)
    add(side+'_under_eye','ribbon',['under_eye_inner','under_eye_center','under_eye_outer'],'Durchgehende Unteraugenfalte',side)
    add(side+'_hatching','hatching',['hatch_inner','hatch_outer'],'Endpunkte der Schraffurzone, keine Umbenennung einzelner Striche',side)
    add(side+'_lid_accent_inner','ribbon',['lid_accent_inner_start','lid_accent_inner_mid','lid_accent_inner_end'],'Innerer Akzentbogen über dem Lid',side)
    add(side+'_lid_accent_outer','ribbon',['lid_accent_outer_start','lid_accent_outer_mid','lid_accent_outer_end'],'Äußerer Akzentbogen über dem Lid',side)
    add(side+'_brow_accent','ribbon',['brow_accent_start','brow_accent_mid','brow_accent_end'],'Optionaler kleiner Bogen am inneren Brauenende',side)
    add(side+'_moustache','ribbon',['moustache_inner_tip','moustache_shoulder','moustache_sweep','moustache_belly','moustache_outer_turn','moustache_curl_top','moustache_curl_inner','moustache_curl_tip'],'Wangenband: acht Mittellinienanker bis zur eingerollten Spitze',side)
add('nose','ribbon',['nose_lower','nose_center','nose_tip'],'Kleine stilisierte Nasenlinie')
add('mouth_upper','ribbon',['mouth_right_corner','mouth_upper_right','mouth_upper_center','mouth_upper_left','mouth_left_corner'],'Mundoberkante, rechts nach links aus Sicht der Figur')
add('mouth_lower','ribbon',['mouth_lower_right','mouth_lower_center','mouth_lower_left'],'Untere Mundgrenze; Eckpunkte vom Obermund übernommen')
add('tongue','contour',['tongue_root_right','tongue_side_right','tongue_tip','tongue_side_left','tongue_root_left','tongue_root_center'],'Optionaler geschlossener Zungenumriss')
add('tongue_crease','derived',['tongue_crease_tip'],'Zungenmittellinie: Start am abgeleiteten Zungenansatz')
add('chin','ribbon',['chin_right','chin_center','chin_left'],'Optionaler Unterlippenakzent')
t={'schema_version':'1.0','topology_id':'cartoon_face_v1','coordinate_system':'normalized','canonical_canvas':{'width':1450,'height':750},
'side_convention':'Anatomical: left is the character\'s left (viewer right). right is viewer left.',
'landmark_states':{'visible':'Component opacity > 0.01, landmark concept present','occluded':'Pupil/reflex center hidden by the lid opening or pupil clipping geometry','absent':'Optional component not present; xy stays stable'},
'keypoints':keys,'components':components}
Path('src/cartoon_face/topology/face_topology.json').write_text(json.dumps(t,indent=2,ensure_ascii=False)+'\n')
print(len(keys),'stable landmarks')
