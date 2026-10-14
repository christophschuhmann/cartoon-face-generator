"""Generate the readable ID catalog and complete pose JSON Schema from the registry."""
import json
from pathlib import Path
from cartoon_face.model import topology
from cartoon_face.seeds import seed_pose

t=topology();p=seed_pose('smile')
lines=['# Topologie cartoon_face_v1','', '101 stabile Landmark-IDs. Links = linke Seite der Figur = rechte Bildhälfte. Rechts = rechte Seite der Figur = linke Bildhälfte.','',
 'Die Reihenfolge dieses Registers ist die Tensor-Reihenfolge. Die JSON-Objektreihenfolge ist nicht verbindlich; `id` bleibt verbindlich. Alle Punkte verwenden [u,v] in [0,1] mit Ursprung links oben. Anker der Brauen laufen außen→innen; Ober-/Unterlider und Wangenbänder innen→außen (Wangenband weiter durch die Spirale). Mundoberkante und Unterkante rechts→links aus Sicht der Figur. Die drei Untermundpunkte werden durch die beiden Obermundwinkel ergänzt.', '',
 '## Status', '', '`visible`: semantischer Punkt gehört zur sichtbaren Komponente. `occluded`: Pupillen-/Reflexzentrum liegt außerhalb der tatsächlichen Lidöffnung bzw. des Pupillen-Clips oder das Auge ist geschlossen. `absent`: optionale Komponente ist ausgeschaltet; die Koordinate bleibt erhalten und wird niemals einem anderen Strich zugewiesen. Bei Teildeckkraft >0.01 gilt die Komponente als sichtbar. Pupillen-/Reflexzentren werden geometrisch gegen die Render-Clips geprüft. Andere Anker verwenden Komponentensichtbarkeit; das ist keine pixelgenaue Sichtbarkeitssegmentierung.', '',
 '## Komponenten', '', '| Komponente | Geometrie | Anker | Bedeutung |','|---|---|---|---|']
for n,c in t['components'].items():lines.append(f"| {n} | {c['kind']} | {len(c['anchors'])} | {c['description']} |")
lines+=['','## Vollständiger ID-Katalog','','| ID | Name | Region / Rolle | Bedeutung und Steuerwirkung |','|---|---|---|---|']
for k in t['keypoints']:lines.append(f"| {k['id']} | `{k['name']}` | {k['region']} / {k['landmark_role']} | {k['meaning']} **Steuerwirkung:** {k['edit_effect']} |")
lines+=['','## Nummerierte Abbildungen und Datenformat','',
 '[Übersicht aller 101 Punkte](landmarks/overview.png), [Brauen](landmarks/brows.png), [linkes Auge](landmarks/eye_left.png), [rechtes Auge](landmarks/eye_right.png), [Wangenbänder](landmarks/moustache.png), [Mund/Nase/Zunge](landmarks/mouth_nose_tongue.png).', '',
 'Die vollständige Erklärung der Einheiten, Sichtbarkeitscodes, Rig-Werte und Serialisierung steht in [data_format.md](data_format.md).']
Path('docs/topology.md').write_text('\n'.join(lines)+'\n')

def infer(v):
 if isinstance(v,dict):return {'type':'object','properties':{k:infer(x) for k,x in v.items()},'required':list(v)}
 if isinstance(v,list):return {'type':'array','minItems':len(v),'maxItems':len(v),'items':infer(v[0]) if v else {}}
 if isinstance(v,str):return {'type':'string'}
 return {'type':'number'}
keyprops={k['name']:{'type':'object','required':['id','xy','state'],'additionalProperties':False,'properties':{'id':{'const':k['id']},'xy':{'type':'array','minItems':2,'maxItems':2,'items':{'type':'number','minimum':0,'maximum':1}},'state':{'enum':['visible','occluded','absent']}}} for k in t['keypoints']}
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:cartoon-face:pose:1.0','title':'Cartoon face complete pose',
 'type':'object','required':['schema_version','topology_id','coordinate_system','canvas','keypoints','rig','variants','style'],
 'properties':{'schema_version':{'const':'1.0'},'topology_id':{'const':'cartoon_face_v1'},'coordinate_system':{'const':'normalized'},
 'canvas':{'type':'object','required':['width','height'],'properties':{n:{'type':'integer','minimum':1,'maximum':8192} for n in ('width','height')}},
 'keypoints':{'type':'object','properties':keyprops,'required':list(keyprops),'additionalProperties':False},'rig':infer(p['rig']),
 'variants':{'type':'object','required':list(p['variants']),'additionalProperties':False,'properties':{n:{'enum':['none','continuous','hatching','mixed'] if n.endswith('under_eye') else (['round','heart'] if n.endswith('highlight') else ['dark','white'])} for n in p['variants']}},
 'style':{'const':{'background':'white','ink':'black'}},
 'geometry':{'type':'object','description':'Optional smooth_v1 style. Absence preserves legacy SVG geometry.',
   'required':['version','ribbon_smoothing','mouth_rounding'],'additionalProperties':False,
   'properties':{'version':{'const':'smooth_v1'},'ribbon_smoothing':{'type':'number','minimum':0,'maximum':1},
     'mouth_rounding':{'type':'number','minimum':0,'maximum':1}}},
 'emotion':{'description':'Optional intended EmoNet target; weights are authoring controls, not probabilities.',
   'type':'object','properties':{
     'taxonomy_id':{'type':'string'},'category_id':{'type':['integer','null'],'minimum':1,'maximum':40},
     'weights':{'type':'array','minItems':40,'maxItems':40,'items':{'type':'number','minimum':0,'maximum':1}},
     'human_validated':{'type':'boolean'},'label_kind':{'type':'string'}}},
 'recipe':{'type':'object','description':'Generation provenance. Renderer consumes resolved geometry instead of reapplying recipe.'}}}
# Count is continuous for interpolation, even though the editor selects integer examples.
for name,c in schema['properties']['rig']['properties'].items():
 c['properties']['opacity'].update(minimum=0,maximum=1)
 if 'widths' in c['properties']:c['properties']['widths']['items'].update(minimum=0,maximum=130)
 if 'tangent_scales' in c['properties']:c['properties']['tangent_scales']['items'].update(minimum=.1,maximum=3)
 if name.endswith('hatching'):c['properties']['count'].update(minimum=0,maximum=8)
Path('src/cartoon_face/topology/pose.schema.json').write_text(json.dumps(schema,indent=2)+'\n')
