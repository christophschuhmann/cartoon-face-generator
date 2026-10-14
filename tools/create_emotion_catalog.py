"""Author the forty compact cartoon recipes, in the verified official category order.
Recipes describe intentional graphic cues. They are not universal FACS diagnoses.
"""
import json
from pathlib import Path
BASE={'brow_raise':0.,'brow_inner':0.,'brow_outer':0.,'brow_arch':0.,'brow_asym':0.,'frown':0.,'eye_open':1.,'eye_asym':0.,'squint':0.,'lid_curve':.2,'lid_tilt':0.,'gaze_x':0.,'gaze_y':0.,'pupil_scale':1.,'mouth_width':1.,'smile':0.,'mouth_open':0.,'mouth_asym':0.,'mouth_tension':0.,'mouth_y':0.,'cheek_lift':0.,'nose_lift':0.,'curl':0.,'warmth':.35}
# Each profile specifies a different constellation, rather than relabeling one smile.
ROWS=[
('amusement','Heiterkeit','positive','dark','continuous','inside','round',{'eye_open':.5,'squint':.85,'lid_curve':.9,'mouth_width':1.18,'smile':.9,'mouth_open':.5,'mouth_asym':.3,'cheek_lift':.7},'Lachende enge Augen, angehobene Wangen und ein offenes leicht schiefes Lachen.','elation','medium'),
('elation','Hochgefühl','positive','dark','continuous','inside','round',{'brow_raise':.7,'brow_arch':.5,'eye_open':1.2,'pupil_scale':1.07,'mouth_width':1.35,'smile':1.,'mouth_open':.7,'cheek_lift':.8},'Wache weite Augen, hochgezogene Brauen und breites freudiges Grinsen.','triumph','medium'),
('pleasure_ecstasy','Genuss / Ekstase','positive','dark','none','none','round',{'brow_inner':.4,'brow_arch':.35,'eye_open':.055,'lid_curve':.9,'mouth_width':.65,'smile':.6,'mouth_open':.2,'cheek_lift':.5},'Geschlossene weich gewölbte Lider und entspanntes kleines offenes Lächeln.','contentment','contextual'),
('contentment','Zufriedenheit','positive','closed','continuous','none','round',{'brow_raise':-.2,'eye_open':.38,'lid_curve':.7,'squint':.2,'mouth_width':.8,'smile':.55},'Ruhige halb geschlossene Augen und ein symmetrisches sanftes Lächeln.','relief','contextual'),
('gratitude','Dankbarkeit','social','closed','mixed','none','round',{'brow_inner':.65,'brow_arch':.2,'eye_open':.68,'squint':.3,'gaze_y':-.15,'mouth_width':.72,'smile':.72,'cheek_lift':.45},'Weicher innerer Brauenanstieg, freundlicher Blick und zurückhaltendes warmes Lächeln.','affection','contextual'),
('affection','Zuneigung','social','closed','continuous','none','round',{'brow_inner':.25,'eye_open':.78,'squint':.45,'pupil_scale':1.12,'gaze_x':.25,'mouth_width':.95,'smile':.8,'cheek_lift':.5},'Warmer großer Blick mit Wangenheben und breiterem liebevollem Lächeln.','gratitude','contextual'),
('infatuation','Verliebtheit','social','dark','hatching','inside','heart',{'brow_raise':.2,'brow_inner':.35,'eye_open':1.,'pupil_scale':1.12,'mouth_width':.82,'smile':.8,'mouth_open':.45,'cheek_lift':.55},'Herzreflexe als bewusste Cartoon-Konvention, Errötungsschraffuren und offenes verträumtes Lächeln.','affection','stylized'),
('hope','Hoffnung / Optimismus','positive','closed','continuous','none','round',{'brow_raise':.6,'brow_inner':.6,'eye_open':1.08,'gaze_y':-.6,'pupil_scale':1.05,'mouth_width':.96,'smile':.66},'Erwartungsvoller aufwärts gerichteter Blick, angehobene innere Brauen und ein optimistisches Lächeln.','interest','contextual'),
('triumph','Triumph','positive','teeth','mixed','none','round',{'brow_raise':.65,'brow_outer':.65,'brow_inner':-.35,'eye_open':.7,'squint':.65,'lid_tilt':.25,'mouth_width':1.4,'smile':1.,'mouth_open':.35,'cheek_lift':.85},'Überzeichnetes Siegergrinsen, enge selbstsichere Augen und kraftvoll angehobene äußere Brauen.','pride','contextual'),
('pride','Stolz','social','closed','continuous','none','round',{'brow_outer':.5,'brow_asym':.18,'eye_open':.7,'gaze_y':-.15,'mouth_width':1.04,'smile':.48,'mouth_asym':.35},'Ruhiger selbstbewusster Blick und ein kontrolliertes leicht asymmetrisches Lächeln.','triumph','contextual'),
('interest','Interesse','cognitive','closed','none','none','round',{'brow_raise':.35,'brow_outer':.15,'eye_open':1.17,'pupil_scale':1.14,'mouth_width':.72,'smile':.15},'Aufmerksame offene Augen und ein kleines empfängliches Lächeln.','concentration','contextual'),
('awe','Staunen / Ehrfurcht','positive','round','none','none','round',{'brow_raise':.75,'brow_inner':.4,'eye_open':1.25,'gaze_y':-.35,'pupil_scale':1.1,'mouth_width':.54,'mouth_open':.4,'cheek_lift':.1},'Weite weiche Augen mit aufwärts gerichtetem Blick und kleinem offenem O-Mund.','surprise','medium'),
('surprise','Überraschung','basic','round','continuous','none','round',{'brow_raise':1.,'brow_outer':.4,'eye_open':1.4,'pupil_scale':.7,'mouth_width':.72,'mouth_open':.85},'Plötzlich weit geöffnete Augen, hohe Brauen, kleine Pupillen und großer runder O-Mund.','fear','medium'),
('concentration','Konzentration','cognitive','closed','none','none','round',{'brow_raise':-.4,'frown':.42,'eye_open':.72,'lid_tilt':.15,'gaze_y':.25,'pupil_scale':.9,'mouth_width':.63,'smile':-.03,'mouth_tension':.15},'Leicht zusammengezogene Brauen, fixierter Blick und schmale gepresste Mundlinie.','contemplation','contextual'),
('contemplation','Nachdenklichkeit','cognitive','pucker','continuous','none','round',{'brow_asym':.65,'brow_inner':.3,'eye_open':.86,'eye_asym':.16,'gaze_x':-.65,'gaze_y':-.42,'mouth_width':.44,'mouth_asym':-.25,'mouth_open':.08},'Blick schräg nach oben, eine erhöhte Braue und ein kleiner nachdenklich gespitzter Mund.','doubt','contextual'),
('relief','Erleichterung','positive','round','continuous','none','round',{'brow_inner':.4,'brow_raise':-.12,'eye_open':.3,'lid_curve':.55,'mouth_width':.52,'mouth_open':.17,'smile':.2},'Entspannte sinkende Lider und kleiner weicher Ausatem-Mund.','contentment','contextual'),
('longing','Sehnsucht','social','closed','continuous','none','round',{'brow_inner':.75,'eye_open':.83,'gaze_x':.58,'gaze_y':-.42,'pupil_scale':1.08,'mouth_width':.78,'smile':-.32,'mouth_asym':.16},'Weicher seitlicher Fernblick, erhöhte innere Brauen und zurückhaltend wehmütiger Mund.','sadness','contextual'),
('teasing','Necken','social','dark','hatching','out','round',{'brow_asym':.45,'eye_open':.54,'eye_asym':-.98,'lid_curve':.8,'gaze_x':.25,'mouth_width':1.05,'smile':.75,'mouth_open':.2,'mouth_asym':.65,'cheek_lift':.55},'Ein geschlossenes zwinkerndes Auge, schiefes Grinsen und kurze herausgestreckte Zunge.','amusement','stylized'),
('impatience','Ungeduld / Gereiztheit','negative','closed','mixed','none','round',{'brow_raise':-.15,'brow_asym':.35,'frown':.65,'eye_open':.58,'lid_tilt':.3,'gaze_x':-.55,'mouth_width':.87,'smile':-.26,'mouth_asym':-.3,'mouth_tension':.45},'Gereizter Seitenblick, gesenkte innere Brauen und angespannte schiefe Mundlinie.','anger','contextual'),
('lust','Begehren','social','dark','hatching','none','round',{'brow_outer':.15,'eye_open':.45,'eye_asym':.12,'gaze_x':.15,'pupil_scale':1.15,'mouth_width':.7,'smile':.42,'mouth_open':.15,'mouth_asym':.35,'cheek_lift':.15},'Schwere halb geschlossene Lider, direkter großer Blick und ein leicht geöffnetes flirtendes Lächeln.','infatuation','contextual'),
('doubt','Zweifel','cognitive','closed','continuous','none','round',{'brow_asym':.9,'frown':.22,'eye_open':.75,'eye_asym':.42,'gaze_x':.55,'mouth_width':.82,'smile':-.22,'mouth_asym':.35},'Eine deutlich höhere Braue, ein zusammengekniffenes Auge und skeptisch verzogener Mund.','confusion','contextual'),
('fear','Angst','basic','teeth','mixed','none','round',{'brow_raise':.65,'brow_inner':1.,'frown':.4,'eye_open':1.32,'pupil_scale':.72,'mouth_width':1.15,'smile':-.12,'mouth_open':.42,'mouth_tension':.45},'Hochgezogene zusammengezogene Brauen, weit offene Augen und horizontal gespannter weißer Mund.','surprise','medium'),
('distress','Bedrängnis / Unruhe','negative','dark','mixed','none','round',{'brow_inner':.95,'frown':.65,'eye_open':1.02,'eye_asym':.14,'pupil_scale':.92,'mouth_width':1.,'smile':-.5,'mouth_open':.36,'mouth_tension':.5},'Besorgte zusammengezogene Brauen, unruhige Augen und offener abwärts verzogener Mund.','helplessness','contextual'),
('confusion','Verwirrung','cognitive','dark','continuous','none','round',{'brow_asym':.95,'brow_raise':.2,'eye_open':1.2,'eye_asym':.28,'gaze_x':-.3,'mouth_width':.62,'smile':-.04,'mouth_open':.3,'mouth_asym':.5,'mouth_tension':.4},'Ungleiche hohe Brauen, suchender offener Blick und ein schief geöffneter kleiner Mund.','doubt','contextual'),
('embarrassment','Verlegenheit','social','closed','hatching','none','round',{'brow_inner':.45,'brow_asym':.25,'eye_open':.74,'gaze_x':-.7,'gaze_y':.42,'mouth_width':.85,'smile':.38,'mouth_asym':.45,'mouth_tension':.2,'cheek_lift':.2},'Seitlich ausweichender Blick, Errötungsschraffuren und ein unsicheres schiefes Lächeln.','shame','contextual'),
('shame','Scham','social','closed','hatching','none','round',{'brow_inner':.75,'brow_raise':-.15,'frown':.2,'eye_open':.48,'gaze_y':.78,'mouth_width':.5,'smile':-.38,'mouth_tension':.1},'Gesenkter enger Blick, angehobene innere Brauen und kleiner zurückgenommener trauriger Mund.','embarrassment','contextual'),
('disappointment','Enttäuschung','negative','closed','continuous','none','round',{'brow_raise':-.35,'brow_inner':.3,'eye_open':.58,'gaze_y':.3,'mouth_width':.94,'smile':-.4},'Sinkende Lider und Brauen mit breiter flacher abwärts gewölbter Mundlinie.','sadness','contextual'),
('sadness','Traurigkeit','basic','closed','continuous','none','round',{'brow_inner':1.,'frown':.18,'eye_open':.73,'gaze_y':.48,'lid_curve':-.2,'mouth_width':.9,'smile':-.8},'Starker innerer Brauenanstieg, weicher gesenkter Blick und deutlicher symmetrischer trauriger Mundbogen.','disappointment','medium'),
('bitterness','Verbitterung','negative','closed','mixed','none','round',{'brow_raise':-.18,'brow_inner':.3,'brow_asym':.24,'frown':.55,'eye_open':.62,'gaze_x':.35,'mouth_width':1.,'smile':-.4,'mouth_asym':.62,'mouth_tension':.25},'Mischung aus gesenktem missmutigem Blick und einseitig angespanntem Mundwinkel.','contempt','contextual'),
('contempt','Verachtung','negative','closed','continuous','none','round',{'brow_outer':.45,'brow_asym':.5,'eye_open':.57,'eye_asym':.18,'lid_tilt':.18,'gaze_y':.2,'mouth_width':.9,'smile':.1,'mouth_asym':.95},'Halb geschlossener herablassender Blick und ein deutlich einseitig hochgezogener Mundwinkel.','pride','contextual'),
('disgust','Ekel','basic','teeth','mixed','none','round',{'brow_raise':-.1,'frown':.55,'eye_open':.54,'eye_asym':.24,'lid_curve':-.2,'squint':.3,'nose_lift':1.,'mouth_width':.9,'smile':-.55,'mouth_open':.26,'mouth_asym':.35,'mouth_tension':.55},'Zusammengezogene Lider, angehobene Nasenlinie und asymmetrische abwärts gezogene weiße Mundöffnung.','sourness','medium'),
('anger','Zorn','basic','teeth','mixed','none','round',{'brow_raise':-.15,'brow_inner':-.6,'frown':1.,'eye_open':.65,'lid_tilt':.85,'squint':.2,'pupil_scale':.88,'mouth_width':1.25,'smile':-.1,'mouth_open':.27,'mouth_tension':.25},'Tief gesenkte innere Brauen, schräger harter Blick und breiter zusammengebissener weißer Mund.','impatience','medium'),
('malice','Boshaftigkeit','negative','closed','mixed','none','round',{'brow_inner':-.3,'brow_asym':.28,'frown':.88,'eye_open':.51,'lid_tilt':.75,'gaze_x':.3,'pupil_scale':.88,'mouth_width':1.3,'smile':.8,'mouth_asym':.5,'cheek_lift':.3},'Wütend geneigte Brauen und schmale Augen kombiniert mit bewusst überzeichnetem boshaftem Grinsen.','anger','stylized'),
('sourness','Säure-Reaktion','physical','pucker','mixed','none','round',{'brow_inner':.55,'frown':.35,'eye_open':.32,'eye_asym':-.48,'lid_curve':-.8,'nose_lift':.8,'mouth_width':.4,'mouth_open':.12,'mouth_asym':.28,'mouth_tension':.65},'Ein stark zusammengekniffenes Auge, gekräuselte kleine Lippen und angehobene Nase.','disgust','stylized'),
('pain','Schmerz','physical','dark','mixed','none','round',{'brow_raise':-.15,'brow_inner':.6,'frown':1.,'eye_open':.055,'lid_curve':-1.,'squint':.75,'nose_lift':.25,'mouth_width':1.1,'smile':-.25,'mouth_open':.62,'mouth_tension':.65},'Fest zusammengepresste abwärts gebogene Lider, zusammengezogene Brauen und offene Schmerzgrimasse.','fear','medium'),
('helplessness','Hilflosigkeit','negative','dark','continuous','none','round',{'brow_inner':.95,'frown':.3,'eye_open':.86,'gaze_y':.5,'mouth_width':.74,'smile':-.7,'mouth_open':.33},'Hochgezogene innere Brauen, gesenkter bittender Blick und kleiner offener trauriger Mund.','distress','contextual'),
('fatigue','Müdigkeit / Erschöpfung','physical','round','continuous','none','round',{'brow_raise':-.4,'brow_arch':-.4,'eye_open':.22,'lid_curve':-.2,'gaze_y':.4,'pupil_scale':.9,'mouth_width':.48,'mouth_open':.34,'cheek_lift':-.2},'Schwere sinkende Lider, flach entspannte Brauen und kleiner gähnender O-Mund.','numbness','medium'),
('numbness','Emotionale Leere','physical','closed','none','none','round',{'brow_raise':-.2,'brow_arch':-.65,'eye_open':.63,'lid_curve':0.,'pupil_scale':.9,'mouth_width':.77,'smile':0.,'mouth_tension':0.},'Unbewegter gerader Blick, reduzierte Brauenwölbung und waagerechte neutrale Mundlinie.','fatigue','contextual'),
('intoxication','Benommenheit','physical','dark','mixed','none','round',{'brow_asym':.7,'brow_arch':-.25,'eye_open':.53,'eye_asym':.5,'gaze_x':-.35,'gaze_y':.25,'pupil_scale':1.06,'mouth_width':1.,'smile':.35,'mouth_open':.22,'mouth_asym':.85,'mouth_tension':.25},'Ungleiche schwere Lider, lockere ungleiche Brauen und entspannt schief geöffneter Mund.','confusion','contextual'),
('envy','Eifersucht / Neid','social','closed','mixed','none','round',{'brow_asym':.35,'brow_inner':-.15,'frown':.75,'eye_open':.65,'eye_asym':-.12,'lid_tilt':.45,'gaze_x':-.82,'mouth_width':.83,'smile':-.35,'mouth_asym':-.5,'mouth_tension':.25},'Harter seitlicher Blick mit zusammengezogenen Brauen und gepresstem missgünstigem Mund.','bitterness','contextual')]
source=json.loads(Path('src/cartoon_face/emotions/taxonomy_source.json').read_text())
# Recipe 1.1: small expression adjustments, not a new character or an added
# smile on every negative emotion. Signed mouth/brow cues remain in place.
REFINEMENTS={
 'anger':{'frown':.92,'brow_inner':-.52,'eye_open':.68,'pupil_scale':.92,'smile':-.18,'mouth_asym':.10,'warmth':.30},
 'fear':{'pupil_scale':.78,'brow_asym':.08,'smile':-.20,'mouth_open':.36,'mouth_tension':.30,'mouth_asym':.12,'warmth':.42},
 'sadness':{'eye_open':.77,'pupil_scale':1.06,'smile':-.76,'mouth_asym':.10,'warmth':.42},
 'disgust':{'frown':.52,'eye_asym':.30,'mouth_width':.88,'smile':-.50},
 'pain':{'mouth_open':.60,'warmth':.40},
 'doubt':{'lid_curve':.28,'frown':.20,'mouth_asym':.40},
 'gratitude':{'brow_inner':.70,'eye_open':.72,'warmth':.40},
 'longing':{'eye_open':.87,'pupil_scale':1.10,'smile':-.35,'warmth':.40},
 'pride':{'mouth_asym':.28,'cheek_lift':.08},
 'malice':{'frown':.84,'brow_inner':-.27,'pupil_scale':.93,'smile':.78,'warmth':.24},
 'contentment':{'lid_curve':.72},
 'distress':{'mouth_tension':.42,'warmth':.42},
 'helplessness':{'warmth':.42},
}
profiles=[]
for i,(slug,de,family,mouth,under,tongue,highlight,actions,cues,contrast,confidence) in enumerate(ROWS):
    aa={**BASE,**actions,**REFINEMENTS.get(slug,{})}
    # One latent drives both arousal and tension; gaze and asymmetry are paired, not 101 independent draws.
    variation={'strength':.28,'asymmetry':.22,'gaze':.34,'mouth':.22,'style':.055}
    if slug in ('pain','pleasure_ecstasy'):variation['strength']=.035
    if slug=='teasing':variation['strength']=.04
    if family=='cognitive':variation['gaze']=.23
    profiles.append({'id':i+1,'slug':slug,'label':source['labels'][i],'label_de':de,'family':family,'actions':aa,
      'options':{'mouth':mouth,'under_eye':under,'tongue':tongue,'highlight':highlight},'variation':variation,
      'visual_cues_de':cues,'contrast_with':contrast,'interpretation':confidence,
      'review_status':'requires_human_recognition_review','human_recognition':'unmeasured'})
catalog={'schema_version':'1.0','taxonomy_id':source['taxonomy_id'],'recipe_version':'1.1','source':source,'neutral_is_extra':True,
 'interpretation':'Procedural cartoon design hypotheses, not universal facial codes or expert-validated ground-truth emotions','profiles':profiles}
Path('src/cartoon_face/emotions/catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
print(len(profiles),'authored emotion profiles')
