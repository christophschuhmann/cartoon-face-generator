"""Record the agent's actual visual observations and measured artifact totals.

The observation text is a coding-agent review from this development session.
Running this report writer is not a new human evaluation or an emotion classifier.
"""
import hashlib,json,re
from pathlib import Path
from cartoon_face.emotion_library import catalog

out=Path('output/emonet');m=json.loads((out/'manifest.json').read_text())
mix=json.loads((out/'mixture_validation.json').read_text());ref=json.loads(Path('output/evaluation.json').read_text())
browser=json.loads(Path('output/editor/browser_test.json').read_text())
test_text=Path('output/test_results.txt').read_text();test_summary=re.search(r'\d+ passed[^\n]*',test_text).group()
# Observations after looking at all 40 archetypes, six family boards (four
# variations per category) and all twelve sampled transition contact sheets.
OBSERVATIONS={
 'amusement':'Offenes Lachen und enge Augen sind deutlich; die Grenze zu allgemeiner Freude bleibt fließend.',
 'elation':'Weiter Blick und breites Lachen unterscheiden sich sichtbar von amusement.',
 'pleasure_ecstasy':'Geschlossene weiche Augen und kleines Lächeln wirken entspannt; Ekstase braucht mehr Kontext.',
 'contentment':'Kleines geschlossenes Lächeln und ruhige enge Lider; Nähe zu Zuneigung und Stolz.',
 'gratitude':'Weiche innere Brauen und warmes Lächeln; Dankbarkeit ist ohne Anlass nicht eindeutig.',
 'affection':'Größere Pupillen und breiteres weiches Lächeln; Nähe zu Dankbarkeit.',
 'infatuation':'Herzreflexe erzeugen einen deutlichen stilisierten Liebeshinweis.',
 'hope':'Aufwärtsblick und freundlicher Mund; ohne Kontext auch Interesse oder Stolz möglich.',
 'triumph':'Breites weißes Siegergrinsen wirkt kräftiger als pride; Erfolg selbst braucht Kontext.',
 'pride':'Kontrolliertes schiefes Lächeln; Stolz und Verachtung können benachbart erscheinen.',
 'interest':'Wachere Augen und zurückhaltender Mund; Aufmerksamkeit ohne eindeutige Emotionsursache.',
 'awe':'Große Pupillen und kleiner O-Mund; im Vergleich weicher als surprise.',
 'surprise':'Kleine Pupillen, große Augen und großer O-Mund bilden eine klare Cartoon-Konstellation.',
 'concentration':'Leichte Kontraktion und gepresster Mund; kann als ernster neutraler Zustand gelesen werden.',
 'contemplation':'Seitlicher Aufwärtsblick, Brauenasymmetrie und gespitzter Mund; Nähe zu doubt.',
 'relief':'Entspannte enge Lider und Ausatem-Mund; kann auch erschöpft wirken.',
 'longing':'Seitlicher wehmütiger Blick; Sehnsucht bleibt ohne Gegenstand mehrdeutig.',
 'teasing':'Zwinkern, schiefes Grinsen und Zunge bleiben auch in Varianten erhalten.',
 'impatience':'Gereizter Seitenblick; Ungeduld lässt sich statisch kaum von milder Wut trennen.',
 'lust':'Schwere Lider und offener kleiner Smile; Flirt/Begehren ist ohne Kontext nicht sicher.',
 'doubt':'Asymmetrische Brauen und unterschiedliches Zusammenkneifen geben einen skeptischen Eindruck.',
 'fear':'Weite Augen und gespannter weißer Mund unterscheiden sich vom runden Überraschungsmund.',
 'distress':'Besorgte Brauen und kleine offene Abwärtsöffnung; Nähe zu Hilflosigkeit.',
 'confusion':'Suchender weiter Blick und schiefer kleiner offener Mund; Nähe zu doubt.',
 'embarrassment':'Seitlich ausweichender Blick und unsicheres Lächeln unterscheiden sich von shame.',
 'shame':'Gesenkter enger Blick und kleiner trauriger Mund; Nähe zu Enttäuschung.',
 'disappointment':'Flacherer trauriger Mund und schwere Lider; Nähe zu Traurigkeit.',
 'sadness':'Stark angehobene innere Brauen und klarer trauriger Mundbogen.',
 'bitterness':'Schiefer missmutiger Mund; Verbitterung/Neid/Ungeduld bleiben nahe.',
 'contempt':'Einseitig hochgezogener Mundwinkel sichtbar erhalten; Nähe zu Stolz.',
 'disgust':'Zusammenkneifen, Nasenanhebung und schiefer weißer Mund; noch ein schwächerer Ekelhinweis als eine anatomische Nasenfalte.',
 'anger':'Die neue innere Brauenabsenkung ergibt einen deutlich härteren Blick als der erste freundliche Basisbogen.',
 'malice':'Harter Blick plus Grinsen bildet einen stilisierten boshaften Eindruck; keine universelle Boshaftigkeitsmimik.',
 'sourness':'Ein stark geschlossenes Auge und gepresste kleine Lippen; bewusst stilisierte Geschmacksreaktion.',
 'pain':'Beidseitiger fester Lidschluss und größere offene Grimasse; Schmerz vs. Anstrengung bleibt kontextabhängig.',
 'helplessness':'Bittende innere Brauen und offener trauriger Mund; Nähe zu distress und sadness.',
 'fatigue':'Schwere Lider und kleiner Gähn-Mund bleiben sichtbar; niedrige Aktivierung erkennbar.',
 'numbness':'Flachere Brauen und waagerechter Mund; emotionale Leere kann ebenso neutral wirken.',
 'intoxication':'Ungleiche schwere Lider und lockerer schiefer Mund; Benommenheit nicht sicher von Müdigkeit/Verwirrung zu trennen.',
 'envy':'Gespannter harter Seitenblick; Neid braucht ein soziales Bezugsobjekt.'}
review={'reviewer':'coding_agent','method':'actual rendered contact sheets inspected during development',
 'recognition_accuracy':None,'human_or_expert_review':False,
 'visual_scope':{'archetypes':40,'representative_variations':160,'family_boards':6,
   'transition_contact_sheets':12,'sampled_frames_per_contact_sheet':12},
 'iterations':['neutral brow shape separated from original smile; inner raising/contraction distinguished',
   'rotated pupils clipped by stationary eye opening in common renderer',
   'pupil placement and light glints adapted to visible opening',
   'mixed under-eye wrinkle and hatching placed in separate segments',
   'variation strengths enlarged with protected target cues',
   'recipe 1.1: tangent-continuous band caps, oval O-mouths, whole glints fitted inside inked opening',
   'recipe 1.1: subtle warmth, relaxed handle extremes and a single closed-lid lash flourish'],
 'categories':[]}
for row in m['categories']:
    path=out/(row['archetype']+'.svg')
    review['categories'].append({'slug':row['slug'],'archetype_svg_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'observation_de':OBSERVATIONS[row['slug']],'human_recognition':'unmeasured'})
(out/'visual_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
foreground=[s['foreground_fraction'] for row in m['categories'] for s in row['samples']]
unique=[v['unique_svg_count'] for v in m['diversity'].values()]
std=[v['mean_coordinate_std_normalized'] for v in m['diversity'].values()]
frames=sum(v['frames'] for v in mix['rendered_sequences'].values())
lines=[f'''# Emotionsschicht: Ergebnisse und verbleibende Grenzen

## Implementierter Umfang

40 Kategorien aus der festgehaltenen offiziellen EmoNet-Face-Taxonomie, jeweils ein Archetyp und ein eigener prozeduraler Variationsraum. Alle verwenden das bestehende `cartoon_face_v1` mit 101 unveränderten IDs und denselben Python/SVG-Renderer. Eine Pose wird als vollständiges JSON mit Geometrie, Rig, Sichtbarkeit, beabsichtigtem Label, 40 Steuergewichten und Rezept gespeichert. Der Editor unterstützt Archetypen, Seeds, Mischungen und manuelle Nachbearbeitung; die Galerie unterstützt separate menschliche Bewertungen.

Aktuelle Rezeptversion: **{m['recipe_version']}**. Die subtile Überarbeitung der Strichenden, Mundrundung und Charakterwärme ist mit echten Vorher/Nachher-Renderings in [emotion_refinement.md](emotion_refinement.md) dokumentiert. Archivierte Rezept-1.0-Posen behalten ihre ursprüngliche SVG-Geometrie.

## Tatsächlich ausgeführte Prüfungen

| Prüfung | Gemessenes Ergebnis |
|---|---|
| Archetypen | {m['category_count']} SVG/PNG/JSON-Pakete |
| Neue Varianten | {m['variation_count']}, {m['variations_per_category']} pro Kategorie, Basis-Seed {m['seed']} |
| Gültige Form- und Zielhinweisprüfungen | `{m['all_valid']}` für sämtliche Archetypen und Varianten |
| Unterschiedliche Varianten-SVGs | {min(unique)}–{max(unique)} pro Kategorie |
| Mittlere Koordinaten-Streuung pro Kategorie | {min(std):.6f}–{max(std):.6f}, normalisierte Einheiten |
| Schwarzer Flächenanteil der Varianten | {min(foreground)*100:.2f}–{max(foreground)*100:.2f} % bei Grau <128 |
| Emotionspaare numerisch | {mix['pair_count']}, jeweils bei 25/50/75 %; alle geometrisch gültig: `{mix['all_geometry_valid']}` |
| Gerenderte Übergänge | {len(mix['rendered_sequences'])} Sequenzen mit zusammen {frames} SVG/PNG/JSON-Frames |
| Automatisierte Tests | {test_summary} |
| Echter Chromium-Test | `{browser['passed']}`, {len(browser['checks'])} Editor-/Galerie-Prüfungen, keine JS-Fehler |
| Menschliche 40-Klassen-Erkennungsgenauigkeit | **Nicht gemessen** |

Die Streuung bezieht sich auf alle 101 Koordinaten, inklusive bewusst stabiler Identitätsanker; sie ist kein Wahrnehmungs-Diversitätsscore. Unterschiedliche SVG-Hashes belegen unterschiedliche Geometrie, keine unterschiedliche Emotionserkennung. Flächenanteil und Formprüfungen verhindern leere/zerstörte Beispiele, sagen aber nichts über semantische Treffsicherheit.

Reproduzierbare Details: [manifest.json](../output/emonet/manifest.json), [mixture_validation.json](../output/emonet/mixture_validation.json), [Tests](../output/test_results.txt), [Browser-Test](../output/editor/browser_test.json), [visuelle Agentenbeobachtungen](../output/emonet/visual_review.json).

## Visuelle Iterationen

Der Coding-Agent hat alle 40 tatsächlichen Archetypen, sechs Familien-Kontaktbögen mit je vier Varianten pro Kategorie (160 repräsentative Varianten) und alle zwölf Übergangs-Kontaktbögen mit je zwölf zeitlich verteilten Frames betrachtet. Die übrigen Varianten und Zwischenframes wurden automatisiert geprüft; es wurden nicht alle Bilder einzeln menschlich bewertet.

Der erste Entwurf übernahm zu viel freundliche Brauenneigung aus der Lächel-Referenz. Ein gemeinsamer neutraler Ausgangsbogen und getrennte innere Hebung/Kontraktion verbessern Zorn, Angst und Traurigkeit. Rotierte Pupillen erzeugten ursprünglich eckige Fragmente, weil ihr Clip mitgedreht wurde; der gemeinsame Renderer verwendet nun eine unbewegte Lidmaske. Pupillen und Lichtreflexe folgen der tatsächlich sichtbaren Öffnung. Gemischte Unteraugenlinien verwenden getrennte Bereiche statt sich kreuzender Striche.

Die ersten Variationen unterschieden sich zu wenig. Aktivierung, Blick, Mundbreite und Asymmetrie variieren nun stärker und korreliert; einseitiger Mundwinkel, trauriger/freudiger Bogen, weite Angst-/Überraschungsaugen und notwendiger Lidschluss werden zusätzlich geschützt. Die gezeigten Kontaktbögen stammen aus dieser verbesserten Version.

![40 Archetypen](../output/emonet/archetypes/contact_sheet.png)

## Tatsächliche Übergangssequenzen

Die folgende Tabelle enthält die gemessene größte Landmark-Verschiebung zwischen zwei aufeinanderfolgenden Frames. Sie misst Koordinatenkontinuität, keine psychologische Kompatibilität. Positive Breiten und begrenzte Tangenten bleiben erhalten. Optionale Details verwenden die gemeinsamen weichen Deckkraftübergänge; graue Zwischenlinien sind beabsichtigtes Ein-/Ausblenden.

| Paar | Frames | Größter normalisierter Punktschritt | Authoring-Regel |
|---|---:|---:|---|
''']
for pair,v in mix['rendered_sequences'].items():
    lines.append(f'| [{pair}](../output/emonet/mixtures/{pair}/contact_sheet.png) | {v["frames"]} | {v["max_landmark_step_normalized"]:.6f} | {v["policy"]} |')
lines+=['''

Staunen→Überraschung, Lachen→Necken, Traurigkeit→Hilflosigkeit und Zweifel→Verwirrung zeigen nachvollziehbare kontinuierliche Formänderungen. Bei den betrachteten Kontaktbögen waren keine zerstörten Konturen oder wechselnden Landmark-Identitäten sichtbar. Dankbarkeit/Zuneigung bleiben auch gemischt eher ein warmer allgemeiner Ausdruck.

Zorn→Hochgefühl kann mittig wie ein anderer aufgeregter Zustand wirken. Schmerz→Genuss kann mittig neutralere geschlossene Augen zeigen. Solche Paare sind als `ambivalent` gekennzeichnet. Sie bleiben technische Vektormischungen und werden nicht als validierte reine Kategorie ausgegeben. Die 780-Paare-Prüfung ist numerisch; nur die zwölf gelisteten Sequenzen wurden gerendert und im Kontaktbogen angesehen.

## Beobachtungen je Kategorie

Dies sind nachvollziehbare Designbeobachtungen des Coding-Agenten, keine unabhängigen menschlichen Klassifikationen.

| Kategorie | Beobachtung / verbleibende Mehrdeutigkeit |
|---|---|
''']
for p in catalog()['profiles']:lines.append(f'| {p["id"]}. {p["label_de"]} | {OBSERVATIONS[p["slug"]]} |')
metrics=ref['mean']
lines+=[f'''

## Unveränderte Referenzfähigkeit

Nach der gemeinsamen Pupillen-Clip-Korrektur wurden alle sechs Originalreferenzen erneut ausgewertet: mittlere Foreground-IoU **{metrics['foreground_iou']:.4f}**, Dice **{metrics['dice']:.4f}**, symmetrischer Konturabstand **{metrics['contour_chamfer_px']:.3f} kanonische Pixel**, ergänzende SSIM **{metrics['ssim']:.4f}**. Die neuen Emotionsrezepte ändern keine gefitteten Referenz-Keypoints und führen keine neue Renderer-Architektur ein.

[Referenzvergleich](../output/comparisons/all_references.png), [vollständige Referenzmetriken](../output/evaluation.json), [Phase-1-Bericht](phase1_report.md). Die alten sieben Interpolationen und 100 synthetischen Rig-Posen wurden ebenfalls neu gerendert und geprüft.

## Nächster sinnvoller Qualitätsschritt

Die technische Generierung für alle 40 Klassen ist vorhanden. Für garantiert treffende **Erkennung aller 40 Kategorien** fehlt ein menschlicher Test, insbesondere bei Dankbarkeit/Zuneigung, Stolz/Triumph, Scham/Enttäuschung und Neid/Verbitterung. Die neue Galerie ermöglicht Bewertungen mit ausgeblendeten Zielnamen und JSON-Export. `face evaluate_reviews` wertet echte Urteile aus, markiert unbewertete Kategorien mit `null` und liefert eine Konfusionsmatrix.

Anschließend sollten gerade häufig verwechselte Kategorien anhand dieser Bewertungen angepasst werden. Kleine Bewegungshinweise oder situativer Kontext könnten später weitere Unterschiede vermitteln; diese Version erzeugt statische Vektorgesichter und kontinuierliche Rig-Übergänge. Es wurden keine Detektoren, kein Training und keine Videoanalyse implementiert. Ein größeres synthetisches Trainingsset sollte intended labels und tatsächlich bewertete Labels getrennt führen.
''']
Path('docs/emotion_validation.md').write_text('\n'.join(line.rstrip() for line in lines)+'\n')
print('Wrote measured emotion report and agent visual review')
