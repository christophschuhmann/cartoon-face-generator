# Topologie cartoon_face_v1

101 stabile Landmark-IDs. Links = linke Seite der Figur = rechte Bildhälfte. Rechts = rechte Seite der Figur = linke Bildhälfte.

Die Reihenfolge dieses Registers ist die Tensor-Reihenfolge. Die JSON-Objektreihenfolge ist nicht verbindlich; `id` bleibt verbindlich. Alle Punkte verwenden [u,v] in [0,1] mit Ursprung links oben. Anker der Brauen laufen außen→innen; Ober-/Unterlider und Wangenbänder innen→außen (Wangenband weiter durch die Spirale). Mundoberkante und Unterkante rechts→links aus Sicht der Figur. Die drei Untermundpunkte werden durch die beiden Obermundwinkel ergänzt.

## Status

`visible`: semantischer Punkt gehört zur sichtbaren Komponente. `occluded`: Pupillen-/Reflexzentrum liegt außerhalb der tatsächlichen Lidöffnung bzw. des Pupillen-Clips oder das Auge ist geschlossen. `absent`: optionale Komponente ist ausgeschaltet; die Koordinate bleibt erhalten und wird niemals einem anderen Strich zugewiesen. Bei Teildeckkraft >0.01 gilt die Komponente als sichtbar. Pupillen-/Reflexzentren werden geometrisch gegen die Render-Clips geprüft. Andere Anker verwenden Komponentensichtbarkeit; das ist keine pixelgenaue Sichtbarkeitssegmentierung.

## Komponenten

| Komponente | Geometrie | Anker | Bedeutung |
|---|---|---|---|
| left_brow | ribbon | 5 | Brauenmittellinie von außen nach innen |
| left_eye_upper | ribbon | 5 | Oberlidmittellinie von innen nach außen, einschließlich seitlichem Abstieg |
| left_eye_lower | ribbon | 3 | Unterlidmittellinie von innen nach außen; bewusst separate Endpunkte für den offenen Zeichenstil |
| left_eye_side | derived | 1 | Seitlicher Lidabschluss; Startpunkt wird vom Oberlid übernommen |
| left_lash | derived | 1 | Äußere Wimpernspitze; Ansatz wird aus Oberlidkurve abgeleitet |
| left_pupil | ellipse | 1 | Pupillenmittelpunkt, Größe im Rig; bei geschlossenem Auge verdeckt |
| left_highlight | ellipse | 1 | Primärer runder Reflex; Herz separat aber an derselben Pupille verankert |
| left_secondary_highlight | ellipse | 1 | Sekundärer weißer Reflex mit fester ID |
| left_under_eye | ribbon | 3 | Durchgehende Unteraugenfalte |
| left_hatching | hatching | 2 | Endpunkte der Schraffurzone, keine Umbenennung einzelner Striche |
| left_lid_accent_inner | ribbon | 3 | Innerer Akzentbogen über dem Lid |
| left_lid_accent_outer | ribbon | 3 | Äußerer Akzentbogen über dem Lid |
| left_brow_accent | ribbon | 3 | Optionaler kleiner Bogen am inneren Brauenende |
| left_moustache | ribbon | 8 | Wangenband: acht Mittellinienanker bis zur eingerollten Spitze |
| right_brow | ribbon | 5 | Brauenmittellinie von außen nach innen |
| right_eye_upper | ribbon | 5 | Oberlidmittellinie von innen nach außen, einschließlich seitlichem Abstieg |
| right_eye_lower | ribbon | 3 | Unterlidmittellinie von innen nach außen; bewusst separate Endpunkte für den offenen Zeichenstil |
| right_eye_side | derived | 1 | Seitlicher Lidabschluss; Startpunkt wird vom Oberlid übernommen |
| right_lash | derived | 1 | Äußere Wimpernspitze; Ansatz wird aus Oberlidkurve abgeleitet |
| right_pupil | ellipse | 1 | Pupillenmittelpunkt, Größe im Rig; bei geschlossenem Auge verdeckt |
| right_highlight | ellipse | 1 | Primärer runder Reflex; Herz separat aber an derselben Pupille verankert |
| right_secondary_highlight | ellipse | 1 | Sekundärer weißer Reflex mit fester ID |
| right_under_eye | ribbon | 3 | Durchgehende Unteraugenfalte |
| right_hatching | hatching | 2 | Endpunkte der Schraffurzone, keine Umbenennung einzelner Striche |
| right_lid_accent_inner | ribbon | 3 | Innerer Akzentbogen über dem Lid |
| right_lid_accent_outer | ribbon | 3 | Äußerer Akzentbogen über dem Lid |
| right_brow_accent | ribbon | 3 | Optionaler kleiner Bogen am inneren Brauenende |
| right_moustache | ribbon | 8 | Wangenband: acht Mittellinienanker bis zur eingerollten Spitze |
| nose | ribbon | 3 | Kleine stilisierte Nasenlinie |
| mouth_upper | ribbon | 5 | Mundoberkante, rechts nach links aus Sicht der Figur |
| mouth_lower | ribbon | 3 | Untere Mundgrenze; Eckpunkte vom Obermund übernommen |
| tongue | contour | 6 | Optionaler geschlossener Zungenumriss |
| tongue_crease | derived | 1 | Zungenmittellinie: Start am abgeleiteten Zungenansatz |
| chin | ribbon | 3 | Optionaler Unterlippenakzent |

## Vollständiger ID-Katalog

| ID | Name | Region / Rolle | Bedeutung und Steuerwirkung |
|---|---|---|---|
| 0 | `left_brow_outer` | left_brow / centerline_anchor | Äußerer Endpunkt der Brauenmittellinie, von der Nase abgewandt. **Steuerwirkung:** Verschieben verändert die äußere Brauenhöhe und -neigung; Breite und Endkappe stehen separat im Rig. |
| 1 | `left_brow_outer_arch` | left_brow / centerline_anchor | Anker im äußeren Viertel des Brauenbogens zwischen Außenende und zentralem Scheitel. **Steuerwirkung:** Steuert den äußeren Anstieg unabhängig von der inneren Brauenhälfte. |
| 2 | `left_brow_apex` | left_brow / centerline_anchor | Zentraler Bogenanker der Braue. Er ist der semantische Scheitel, nicht zwingend das mathematisch höchste Pixel jeder deformierten Pose. **Steuerwirkung:** Hebt oder senkt die Bogenmitte und verändert die emotionale Überzeichnung. |
| 3 | `left_brow_inner_arch` | left_brow / centerline_anchor | Anker der inneren Brauenhälfte unmittelbar vor dem zur Nase gerichteten Ende. **Steuerwirkung:** Steuert die innere Wölbung, beispielsweise besorgtes Anheben oder zorniges Absenken. |
| 4 | `left_brow_inner` | left_brow / centerline_anchor | Zur Nase gerichteter Endpunkt der Brauenmittellinie. **Steuerwirkung:** Bestimmt die innere Brauenhöhe. Zusammen mit dem Außenende beeinflusst er die emotionale Neigung. |
| 5 | `left_eye_inner_corner` | left_eye_upper / centerline_anchor | Zur Nase gerichteter Endpunkt der oberen Lidkurve. **Steuerwirkung:** Bestimmt den inneren Beginn des Oberlidbogens und eine Grenze des Pupillen-Clips; getrennt vom Unterlidende. |
| 6 | `left_eye_upper_inner` | left_eye_upper / centerline_anchor | Oberlidanker im inneren Viertel zwischen innerem Ende und Bogenmitte. **Steuerwirkung:** Verändert die innere Lidwölbung unabhängig von Mitte und äußerer Hälfte. |
| 7 | `left_eye_upper_center` | left_eye_upper / centerline_anchor | Zentraler Anker auf der Mittellinie des oberen Lidbogens. **Steuerwirkung:** Steuert die zentrale Augenöffnung und Wölbung; ist kein Ellipsenmittelpunkt. |
| 8 | `left_eye_upper_outer` | left_eye_upper / centerline_anchor | Oberlidanker im äußeren Viertel zwischen Bogenmitte und Außenende. **Steuerwirkung:** Verändert äußere Lidwölbung und den abgeleiteten Wimpernansatz. |
| 9 | `left_eye_outer_corner` | left_eye_upper / centerline_anchor | Äußerer Endpunkt der oberen Lidkurve, häufig bereits im seitlichen Abstieg des stilisierten Auges. **Steuerwirkung:** Bestimmt den äußeren Oberlidabschluss; der zusätzliche Seitenstrich startet hier. |
| 10 | `left_eye_lower_inner_corner` | left_eye_lower / centerline_anchor | Zur Nase gerichtetes Ende der separat gezeichneten unteren Lidkurve. **Steuerwirkung:** Steuert den inneren Unterlidabschluss und die untere Clip-Grenze. Eine kleine Lücke zum Oberlid ist beabsichtigt. |
| 11 | `left_eye_lower_center` | left_eye_lower / centerline_anchor | Zentraler Mittellinienanker des unteren Lidbogens. **Steuerwirkung:** Verändert Wangenheben und Unterlidspannung unabhängig von der oberen Augenöffnung. |
| 12 | `left_eye_lower_outer_corner` | left_eye_lower / centerline_anchor | Äußeres Ende der unteren Lidkurve, von der Nase abgewandt. **Steuerwirkung:** Steuert den äußeren Unterlidabschluss und die daraus abgeleiteten kleinen Winkelakzente. |
| 13 | `left_eye_side_end` | left_eye_side / endpoint_anchor | Freies Ende des zusätzlichen seitlichen Lidstrichs; sein Start ist der obere Außenwinkel. **Steuerwirkung:** Ändert Länge und Richtung dieses Abschlusses. Die Zwischenwölbung wird aus rig.bulge abgeleitet. |
| 14 | `left_eye_lash_tip` | left_lash / endpoint_anchor | Äußerste Spitze der dekorativen Wimper. **Steuerwirkung:** Ändert die Wimpernrichtung und -länge. Ansatzposition root_t, Krümmung bend und Breite sind interne Rig-Werte. |
| 15 | `left_pupil_center` | left_pupil / ellipse_center | Geometrischer Mittelpunkt der schwarzen Pupillenellipse vor dem Abschneiden durch die Lidöffnung. **Steuerwirkung:** Steuert den Blick. Radius und Rotation stehen im Rig; der Mittelpunkt bleibt auch bei verdeckter Pupille erhalten. |
| 16 | `left_highlight_center` | left_highlight / ellipse_center | Mittelpunkt des primären runden weißen Lichtreflexes. **Steuerwirkung:** Verschiebt den runden Reflex unabhängig von der Pupille. Das optionale Herz besitzt einen separaten internen Offset zum Pupillenmittelpunkt. |
| 17 | `left_secondary_highlight_center` | left_secondary_highlight / ellipse_center | Mittelpunkt eines zweiten kleinen runden weißen Reflexes mit dauerhaft eigener ID. **Steuerwirkung:** Verschiebt den Zusatzreflex. opacity=0 bedeutet absent, nicht eine Umdeutung in ein anderes Detail. |
| 18 | `left_under_eye_inner` | left_under_eye / centerline_anchor | Zur Nase gerichtetes Ende der längeren durchgehenden Unteraugenfalte. **Steuerwirkung:** Steuert Position und Länge der inneren Faltenhälfte. Im Modus hatching allein ist diese Komponente abwesend. |
| 19 | `left_under_eye_center` | left_under_eye / centerline_anchor | Mittlerer Anker der durchgehenden Unteraugenfalte. **Steuerwirkung:** Verändert deren Biegung unabhängig vom Unterlid und den Schraffuren. |
| 20 | `left_under_eye_outer` | left_under_eye / centerline_anchor | Von der Nase abgewandtes Ende der durchgehenden Unteraugenfalte. **Steuerwirkung:** Steuert den äußeren Abschluss; ist kein einzelner Schraffurstrich. |
| 21 | `left_hatch_inner` | left_hatching / zone_anchor | Innerer Endanker der Schraffurzone; bei mehreren Strichen deren erster Mittelpunktsort nahe der Nase. **Steuerwirkung:** Begrenzt die gemeinsame Zone. Die acht internen Strich-Slots werden dazwischen erzeugt; dieser Punkt bezeichnet keine wechselnde Strichspitze. |
| 22 | `left_hatch_outer` | left_hatching / zone_anchor | Äußerer Endanker der Schraffurzone, von der Nase abgewandt. **Steuerwirkung:** Zusammen mit hatch_inner bestimmt er Lage, Ausdehnung und Verlauf der Zone; Anzahl und Neigung der Striche stehen im Rig. |
| 23 | `left_lid_accent_inner_start` | left_lid_accent_inner / centerline_anchor | Erster Anker des kleinen inneren Akzentbogens oberhalb des Lids. **Steuerwirkung:** Verschiebt seinen Anfang. start/mid/end sind die feste Zeichenreihenfolge dieses Details, nicht allgemeine Augenwinkel. |
| 24 | `left_lid_accent_inner_mid` | left_lid_accent_inner / centerline_anchor | Mittlerer Anker des inneren Lid-Akzentbogens. **Steuerwirkung:** Verändert seine Wölbung und erhält dabei dessen Identität als optionales Detail. |
| 25 | `left_lid_accent_inner_end` | left_lid_accent_inner / centerline_anchor | Letzter Anker des inneren Lid-Akzentbogens. **Steuerwirkung:** Verändert Abschluss, Richtung und Länge dieses Akzents. |
| 26 | `left_lid_accent_outer_start` | left_lid_accent_outer / centerline_anchor | Erster Anker des äußeren Akzentbogens oberhalb des Lids. **Steuerwirkung:** Steuert seinen Anfang getrennt von Oberlid und innerem Akzent. |
| 27 | `left_lid_accent_outer_mid` | left_lid_accent_outer / centerline_anchor | Mittlerer Anker des äußeren Lid-Akzentbogens. **Steuerwirkung:** Verändert die äußere dekorative Wölbung. |
| 28 | `left_lid_accent_outer_end` | left_lid_accent_outer / centerline_anchor | Letzter Anker des äußeren Lid-Akzentbogens. **Steuerwirkung:** Steuert die äußere dekorative Endung; opacity bestimmt die Existenz des ganzen Details. |
| 29 | `left_brow_accent_start` | left_brow_accent / centerline_anchor | Erster Anker des kleinen, optionalen Strichs am inneren Brauenende. **Steuerwirkung:** Steuert den Anfang dieses separaten Strichs, nicht die schwarze Hauptbraue. |
| 30 | `left_brow_accent_mid` | left_brow_accent / centerline_anchor | Mittlerer Anker des optionalen Brauenakzents. **Steuerwirkung:** Verändert dessen Krümmung, beispielsweise einen kleinen Klammerbogen. |
| 31 | `left_brow_accent_end` | left_brow_accent / centerline_anchor | Letzter Anker des optionalen Brauenakzents. **Steuerwirkung:** Steuert Richtung und Länge seines Endes. |
| 32 | `left_moustache_inner_tip` | left_moustache / centerline_anchor | Zur Gesichtsmitte gerichtete, zulaufende Spitze des schwarzen Wangenbands. **Steuerwirkung:** Steuert dessen inneren Ansatz neben Nase und Mund. Dies ist die Spitze des Bandes, keine Mundwinkellandmark. |
| 33 | `left_moustache_shoulder` | left_moustache / centerline_anchor | Anker der breiteren inneren Schulter unmittelbar hinter der inneren Spitze. **Steuerwirkung:** Steuert den charakteristischen inneren Schwung; lokale Breite ist widths[1]. |
| 34 | `left_moustache_sweep` | left_moustache / centerline_anchor | Anker im langen mittleren Schwung des Wangenbands. **Steuerwirkung:** Steuert dessen S-Kurve zwischen Schulter und äußerem Bauch. |
| 35 | `left_moustache_belly` | left_moustache / centerline_anchor | Anker im äußeren Bauch vor der eingerollten Endung. **Steuerwirkung:** Verändert die ausladende Wangenkurve und ihren Übergang zur Spirale. |
| 36 | `left_moustache_outer_turn` | left_moustache / centerline_anchor | Anker am äußeren Richtungswechsel, wo das Band in die eingerollte Endung übergeht. **Steuerwirkung:** Dient auch als Drehzentrum des prozeduralen Curl-Controls; ist nicht das freie Ende des Pfads. |
| 37 | `left_moustache_curl_top` | left_moustache / centerline_anchor | Scheitelanker auf der äußeren Hälfte der eingerollten Endung. **Steuerwirkung:** Steuert Größe und Lage der Spirale. Bei gedrehter Spirale ist er nicht zwingend der oberste Bildpunkt. |
| 38 | `left_moustache_curl_inner` | left_moustache / centerline_anchor | Anker auf dem nach innen zurücklaufenden Teil der Spirale. **Steuerwirkung:** Bestimmt die Einrollung und den eleganten Übergang zur freien Spitze. |
| 39 | `left_moustache_curl_tip` | left_moustache / centerline_anchor | Freie Spitze am Ende der eingerollten Wangenlinie. **Steuerwirkung:** Steuert Endrichtung und Einrolltiefe. Breite widths[7] und Tangente entscheiden über den lokalen Abschluss. |
| 40 | `right_brow_outer` | right_brow / centerline_anchor | Äußerer Endpunkt der Brauenmittellinie, von der Nase abgewandt. **Steuerwirkung:** Verschieben verändert die äußere Brauenhöhe und -neigung; Breite und Endkappe stehen separat im Rig. |
| 41 | `right_brow_outer_arch` | right_brow / centerline_anchor | Anker im äußeren Viertel des Brauenbogens zwischen Außenende und zentralem Scheitel. **Steuerwirkung:** Steuert den äußeren Anstieg unabhängig von der inneren Brauenhälfte. |
| 42 | `right_brow_apex` | right_brow / centerline_anchor | Zentraler Bogenanker der Braue. Er ist der semantische Scheitel, nicht zwingend das mathematisch höchste Pixel jeder deformierten Pose. **Steuerwirkung:** Hebt oder senkt die Bogenmitte und verändert die emotionale Überzeichnung. |
| 43 | `right_brow_inner_arch` | right_brow / centerline_anchor | Anker der inneren Brauenhälfte unmittelbar vor dem zur Nase gerichteten Ende. **Steuerwirkung:** Steuert die innere Wölbung, beispielsweise besorgtes Anheben oder zorniges Absenken. |
| 44 | `right_brow_inner` | right_brow / centerline_anchor | Zur Nase gerichteter Endpunkt der Brauenmittellinie. **Steuerwirkung:** Bestimmt die innere Brauenhöhe. Zusammen mit dem Außenende beeinflusst er die emotionale Neigung. |
| 45 | `right_eye_inner_corner` | right_eye_upper / centerline_anchor | Zur Nase gerichteter Endpunkt der oberen Lidkurve. **Steuerwirkung:** Bestimmt den inneren Beginn des Oberlidbogens und eine Grenze des Pupillen-Clips; getrennt vom Unterlidende. |
| 46 | `right_eye_upper_inner` | right_eye_upper / centerline_anchor | Oberlidanker im inneren Viertel zwischen innerem Ende und Bogenmitte. **Steuerwirkung:** Verändert die innere Lidwölbung unabhängig von Mitte und äußerer Hälfte. |
| 47 | `right_eye_upper_center` | right_eye_upper / centerline_anchor | Zentraler Anker auf der Mittellinie des oberen Lidbogens. **Steuerwirkung:** Steuert die zentrale Augenöffnung und Wölbung; ist kein Ellipsenmittelpunkt. |
| 48 | `right_eye_upper_outer` | right_eye_upper / centerline_anchor | Oberlidanker im äußeren Viertel zwischen Bogenmitte und Außenende. **Steuerwirkung:** Verändert äußere Lidwölbung und den abgeleiteten Wimpernansatz. |
| 49 | `right_eye_outer_corner` | right_eye_upper / centerline_anchor | Äußerer Endpunkt der oberen Lidkurve, häufig bereits im seitlichen Abstieg des stilisierten Auges. **Steuerwirkung:** Bestimmt den äußeren Oberlidabschluss; der zusätzliche Seitenstrich startet hier. |
| 50 | `right_eye_lower_inner_corner` | right_eye_lower / centerline_anchor | Zur Nase gerichtetes Ende der separat gezeichneten unteren Lidkurve. **Steuerwirkung:** Steuert den inneren Unterlidabschluss und die untere Clip-Grenze. Eine kleine Lücke zum Oberlid ist beabsichtigt. |
| 51 | `right_eye_lower_center` | right_eye_lower / centerline_anchor | Zentraler Mittellinienanker des unteren Lidbogens. **Steuerwirkung:** Verändert Wangenheben und Unterlidspannung unabhängig von der oberen Augenöffnung. |
| 52 | `right_eye_lower_outer_corner` | right_eye_lower / centerline_anchor | Äußeres Ende der unteren Lidkurve, von der Nase abgewandt. **Steuerwirkung:** Steuert den äußeren Unterlidabschluss und die daraus abgeleiteten kleinen Winkelakzente. |
| 53 | `right_eye_side_end` | right_eye_side / endpoint_anchor | Freies Ende des zusätzlichen seitlichen Lidstrichs; sein Start ist der obere Außenwinkel. **Steuerwirkung:** Ändert Länge und Richtung dieses Abschlusses. Die Zwischenwölbung wird aus rig.bulge abgeleitet. |
| 54 | `right_eye_lash_tip` | right_lash / endpoint_anchor | Äußerste Spitze der dekorativen Wimper. **Steuerwirkung:** Ändert die Wimpernrichtung und -länge. Ansatzposition root_t, Krümmung bend und Breite sind interne Rig-Werte. |
| 55 | `right_pupil_center` | right_pupil / ellipse_center | Geometrischer Mittelpunkt der schwarzen Pupillenellipse vor dem Abschneiden durch die Lidöffnung. **Steuerwirkung:** Steuert den Blick. Radius und Rotation stehen im Rig; der Mittelpunkt bleibt auch bei verdeckter Pupille erhalten. |
| 56 | `right_highlight_center` | right_highlight / ellipse_center | Mittelpunkt des primären runden weißen Lichtreflexes. **Steuerwirkung:** Verschiebt den runden Reflex unabhängig von der Pupille. Das optionale Herz besitzt einen separaten internen Offset zum Pupillenmittelpunkt. |
| 57 | `right_secondary_highlight_center` | right_secondary_highlight / ellipse_center | Mittelpunkt eines zweiten kleinen runden weißen Reflexes mit dauerhaft eigener ID. **Steuerwirkung:** Verschiebt den Zusatzreflex. opacity=0 bedeutet absent, nicht eine Umdeutung in ein anderes Detail. |
| 58 | `right_under_eye_inner` | right_under_eye / centerline_anchor | Zur Nase gerichtetes Ende der längeren durchgehenden Unteraugenfalte. **Steuerwirkung:** Steuert Position und Länge der inneren Faltenhälfte. Im Modus hatching allein ist diese Komponente abwesend. |
| 59 | `right_under_eye_center` | right_under_eye / centerline_anchor | Mittlerer Anker der durchgehenden Unteraugenfalte. **Steuerwirkung:** Verändert deren Biegung unabhängig vom Unterlid und den Schraffuren. |
| 60 | `right_under_eye_outer` | right_under_eye / centerline_anchor | Von der Nase abgewandtes Ende der durchgehenden Unteraugenfalte. **Steuerwirkung:** Steuert den äußeren Abschluss; ist kein einzelner Schraffurstrich. |
| 61 | `right_hatch_inner` | right_hatching / zone_anchor | Innerer Endanker der Schraffurzone; bei mehreren Strichen deren erster Mittelpunktsort nahe der Nase. **Steuerwirkung:** Begrenzt die gemeinsame Zone. Die acht internen Strich-Slots werden dazwischen erzeugt; dieser Punkt bezeichnet keine wechselnde Strichspitze. |
| 62 | `right_hatch_outer` | right_hatching / zone_anchor | Äußerer Endanker der Schraffurzone, von der Nase abgewandt. **Steuerwirkung:** Zusammen mit hatch_inner bestimmt er Lage, Ausdehnung und Verlauf der Zone; Anzahl und Neigung der Striche stehen im Rig. |
| 63 | `right_lid_accent_inner_start` | right_lid_accent_inner / centerline_anchor | Erster Anker des kleinen inneren Akzentbogens oberhalb des Lids. **Steuerwirkung:** Verschiebt seinen Anfang. start/mid/end sind die feste Zeichenreihenfolge dieses Details, nicht allgemeine Augenwinkel. |
| 64 | `right_lid_accent_inner_mid` | right_lid_accent_inner / centerline_anchor | Mittlerer Anker des inneren Lid-Akzentbogens. **Steuerwirkung:** Verändert seine Wölbung und erhält dabei dessen Identität als optionales Detail. |
| 65 | `right_lid_accent_inner_end` | right_lid_accent_inner / centerline_anchor | Letzter Anker des inneren Lid-Akzentbogens. **Steuerwirkung:** Verändert Abschluss, Richtung und Länge dieses Akzents. |
| 66 | `right_lid_accent_outer_start` | right_lid_accent_outer / centerline_anchor | Erster Anker des äußeren Akzentbogens oberhalb des Lids. **Steuerwirkung:** Steuert seinen Anfang getrennt von Oberlid und innerem Akzent. |
| 67 | `right_lid_accent_outer_mid` | right_lid_accent_outer / centerline_anchor | Mittlerer Anker des äußeren Lid-Akzentbogens. **Steuerwirkung:** Verändert die äußere dekorative Wölbung. |
| 68 | `right_lid_accent_outer_end` | right_lid_accent_outer / centerline_anchor | Letzter Anker des äußeren Lid-Akzentbogens. **Steuerwirkung:** Steuert die äußere dekorative Endung; opacity bestimmt die Existenz des ganzen Details. |
| 69 | `right_brow_accent_start` | right_brow_accent / centerline_anchor | Erster Anker des kleinen, optionalen Strichs am inneren Brauenende. **Steuerwirkung:** Steuert den Anfang dieses separaten Strichs, nicht die schwarze Hauptbraue. |
| 70 | `right_brow_accent_mid` | right_brow_accent / centerline_anchor | Mittlerer Anker des optionalen Brauenakzents. **Steuerwirkung:** Verändert dessen Krümmung, beispielsweise einen kleinen Klammerbogen. |
| 71 | `right_brow_accent_end` | right_brow_accent / centerline_anchor | Letzter Anker des optionalen Brauenakzents. **Steuerwirkung:** Steuert Richtung und Länge seines Endes. |
| 72 | `right_moustache_inner_tip` | right_moustache / centerline_anchor | Zur Gesichtsmitte gerichtete, zulaufende Spitze des schwarzen Wangenbands. **Steuerwirkung:** Steuert dessen inneren Ansatz neben Nase und Mund. Dies ist die Spitze des Bandes, keine Mundwinkellandmark. |
| 73 | `right_moustache_shoulder` | right_moustache / centerline_anchor | Anker der breiteren inneren Schulter unmittelbar hinter der inneren Spitze. **Steuerwirkung:** Steuert den charakteristischen inneren Schwung; lokale Breite ist widths[1]. |
| 74 | `right_moustache_sweep` | right_moustache / centerline_anchor | Anker im langen mittleren Schwung des Wangenbands. **Steuerwirkung:** Steuert dessen S-Kurve zwischen Schulter und äußerem Bauch. |
| 75 | `right_moustache_belly` | right_moustache / centerline_anchor | Anker im äußeren Bauch vor der eingerollten Endung. **Steuerwirkung:** Verändert die ausladende Wangenkurve und ihren Übergang zur Spirale. |
| 76 | `right_moustache_outer_turn` | right_moustache / centerline_anchor | Anker am äußeren Richtungswechsel, wo das Band in die eingerollte Endung übergeht. **Steuerwirkung:** Dient auch als Drehzentrum des prozeduralen Curl-Controls; ist nicht das freie Ende des Pfads. |
| 77 | `right_moustache_curl_top` | right_moustache / centerline_anchor | Scheitelanker auf der äußeren Hälfte der eingerollten Endung. **Steuerwirkung:** Steuert Größe und Lage der Spirale. Bei gedrehter Spirale ist er nicht zwingend der oberste Bildpunkt. |
| 78 | `right_moustache_curl_inner` | right_moustache / centerline_anchor | Anker auf dem nach innen zurücklaufenden Teil der Spirale. **Steuerwirkung:** Bestimmt die Einrollung und den eleganten Übergang zur freien Spitze. |
| 79 | `right_moustache_curl_tip` | right_moustache / centerline_anchor | Freie Spitze am Ende der eingerollten Wangenlinie. **Steuerwirkung:** Steuert Endrichtung und Einrolltiefe. Breite widths[7] und Tangente entscheiden über den lokalen Abschluss. |
| 80 | `nose_lower` | nose / centerline_anchor | Unterer Beginn der kleinen stilisierten Nasenlinie. **Steuerwirkung:** Steuert deren unteren Haken/Abschluss; kein anatomischer 3D-Nasenflügel. |
| 81 | `nose_center` | nose / centerline_anchor | Mittellinienanker im Bogen der Nasenzeichnung. **Steuerwirkung:** Verändert deren zentrale Krümmung und Orientierung. |
| 82 | `nose_tip` | nose / centerline_anchor | Freies oberes/rechtes Ende der stilisierten Nasenlinie. **Steuerwirkung:** Steuert deren Abschluss. Der Name bezeichnet die Spitze dieses gezeichneten Elements, nicht einen realen Nasenspitzen-Landmark. |
| 83 | `mouth_right_corner` | mouth_upper / centerline_anchor | Rechter Mundwinkel aus Sicht der Figur, also in der linken Bildhälfte. **Steuerwirkung:** Gemeinsamer Endpunkt von Ober- und Untermund; beeinflusst Mundbreite, Asymmetrie und den abgeleiteten Winkelakzent. |
| 84 | `mouth_upper_right` | mouth_upper / centerline_anchor | Anker der rechten Hälfte der oberen Mundkurve zwischen rechtem Winkel und Mitte. **Steuerwirkung:** Steuert die lokale Obermundwölbung unabhängig vom gegenüberliegenden Winkel. |
| 85 | `mouth_upper_center` | mouth_upper / centerline_anchor | Zentraler Anker der oberen Mundkurve bzw. der geschlossenen Mundlinie. **Steuerwirkung:** Steuert Lächeln, Stirnrunzel-Mund oder zentrale Obergrenze der Öffnung. Der Untermund bleibt unabhängig. |
| 86 | `mouth_upper_left` | mouth_upper / centerline_anchor | Anker der linken Hälfte der oberen Mundkurve, aus Sicht der Figur. **Steuerwirkung:** Steuert die linke Obermundwölbung und asymmetrische Formen. |
| 87 | `mouth_left_corner` | mouth_upper / centerline_anchor | Linker Mundwinkel aus Sicht der Figur, also in der rechten Bildhälfte. **Steuerwirkung:** Gemeinsamer Endpunkt von Ober- und Untermund; bleibt in allen Darstellungsmodi dieselbe ID. |
| 88 | `mouth_lower_right` | mouth_lower / centerline_anchor | Rechter Zwischenanker der unteren Mundgrenze. **Steuerwirkung:** Steuert die rechte Öffnungshälfte. Beim geschlossenen Mund ist die Untermund-Komponente absent und die Koordinate latent erhalten. |
| 89 | `mouth_lower_center` | mouth_lower / centerline_anchor | Zentraler Anker der unteren Mundgrenze. **Steuerwirkung:** Steuert vor allem Öffnungshöhe und unteren Mundbogen; ist keine Kinnposition. |
| 90 | `mouth_lower_left` | mouth_lower / centerline_anchor | Linker Zwischenanker der unteren Mundgrenze, aus Sicht der Figur. **Steuerwirkung:** Steuert deren linke Form. Die beiden Endwinkel werden aus dem Obermund übernommen und besitzen keine doppelte ID. |
| 91 | `tongue_root_right` | tongue / contour_anchor | Rechter Ansatzpunkt auf dem geschlossenen Zungenumriss, aus Sicht der Figur. **Steuerwirkung:** Verankert den Ansatz an der rechten Seite der Mundöffnung; erscheint nur bei aktivierter Zunge. |
| 92 | `tongue_side_right` | tongue / contour_anchor | Anker auf der rechten seitlichen Zungenkontur. **Steuerwirkung:** Steuert seitliche Breite, Wölbung und Asymmetrie der Zunge. |
| 93 | `tongue_tip` | tongue / contour_anchor | Anker an der freien unteren Zungenspitze. **Steuerwirkung:** Steuert Länge und tiefsten Abschnitt der Zunge; bei Innenzunge dieselbe semantische Konturposition. |
| 94 | `tongue_side_left` | tongue / contour_anchor | Anker auf der linken seitlichen Zungenkontur, aus Sicht der Figur. **Steuerwirkung:** Steuert die gegenüberliegende Breite und Wölbung unabhängig von der rechten Seite. |
| 95 | `tongue_root_left` | tongue / contour_anchor | Linker Ansatzpunkt auf dem geschlossenen Zungenumriss, aus Sicht der Figur. **Steuerwirkung:** Verankert die linke Ansatzseite an der Mundöffnung. |
| 96 | `tongue_root_center` | tongue / contour_anchor | Mittlerer Ansatzanker auf der oberen Zungenkontur; schließt die Kontur zwischen den beiden Wurzelseiten. **Steuerwirkung:** Erzeugt einen runden Ansatz statt einer geraden Schließkante und ist der Start der abgeleiteten Zungenmittellinie. |
| 97 | `tongue_crease_tip` | tongue_crease / endpoint_anchor | Freies Ende der schwarzen Mittellinie auf der Zunge. **Steuerwirkung:** Start liegt bei tongue_root_center; Verlauf entsteht aus diesem Endpunkt und rig.bend. Abwesend, wenn Zunge oder Mittellinie deaktiviert sind. |
| 98 | `chin_right` | chin / centerline_anchor | Rechter Endanker des kleinen Akzentbogens unter dem Mund. **Steuerwirkung:** Steuert dessen rechten Anfang; chin ist ein historischer Komponentenname und keine gezeichnete Gesichtssilhouette. |
| 99 | `chin_center` | chin / centerline_anchor | Mittlerer Anker des optionalen Unterlippen-/Kinnakzentstrichs. **Steuerwirkung:** Steuert dessen Wölbung und Abstand zum Mund. |
| 100 | `chin_left` | chin / centerline_anchor | Linker Endanker des optionalen Akzentbogens unter dem Mund, aus Sicht der Figur. **Steuerwirkung:** Steuert den linken Abschluss; beim ausgeschalteten Detail bleibt seine ID erhalten. |

## Nummerierte Abbildungen und Datenformat

[Übersicht aller 101 Punkte](landmarks/overview.png), [Brauen](landmarks/brows.png), [linkes Auge](landmarks/eye_left.png), [rechtes Auge](landmarks/eye_right.png), [Wangenbänder](landmarks/moustache.png), [Mund/Nase/Zunge](landmarks/mouth_nose_tongue.png).

Die vollständige Erklärung der Einheiten, Sichtbarkeitscodes, Rig-Werte und Serialisierung steht in [data_format.md](data_format.md).
