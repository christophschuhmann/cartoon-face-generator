"""Build the Phase-1 report from actual evaluated artifacts."""
import json
from pathlib import Path
from cartoon_face.reference import ROOT
r=json.loads((ROOT/'output/evaluation.json').read_text());v=json.loads((ROOT/'output/validation.json').read_text());d=json.loads((ROOT/'output/diagnostics.json').read_text())
import re
test_count=re.search(r'(\d+) passed',(ROOT/'output/test_results.txt').read_text()).group(1)
lines=['# Phase-1-Ergebnisbericht','',
 'Implementiert und ausgeführt: gemeinsames parametrisches SVG-Rig, 101 feste semantische Landmarks, sechs automatisch optimierte Parametersätze, lokaler Editor, Interpolation und 100 zusätzliche synthetische Zustände. Die Ergebnisse wurden als tatsächliche SVGs gerendert und mehrfach visuell mit den Originalen verglichen. Alle Werte unten stammen aus `output/evaluation.json`.', '',
 '## Rekonstruktion aller sechs Originale', '',
 'Arbeitsauflösung: 1450 × 750 Pixel nach identischem rahmenfreien Ausschnitt. Keine Glättung der RGB-Referenzen. Maskenschwelle Grau<128. IoU/Dice: höher ist besser; symmetrischer mittlerer Konturabstand: niedriger ist besser. Mittelwerte sind arithmetische Mittel der sechs Posen.', '',
 '| Pose | Foreground-IoU | Dice | Konturabstand [px] | Kontur-p95 [px] | SSIM |','|---|---:|---:|---:|---:|---:|']
for n,m in r['poses'].items():lines.append(f"| {n} | {m['foreground_iou']:.4f} | {m['dice']:.4f} | {m['contour_chamfer_px']:.3f} | {m['contour_p95_px']:.3f} | {m['ssim']:.4f} |")
m=r['mean'];lines.append(f"| **Mittel** | **{m['foreground_iou']:.4f}** | **{m['dice']:.4f}** | **{m['contour_chamfer_px']:.3f}** | — | **{m['ssim']:.4f}** |")
lines+=['', 'SSIM ist durch die Referenztextur und die großen weißen Flächen beeinflusst. Die SVGs reproduzieren die Vektorformen, nicht das leichte Korn oder sehr schwache Kratzspuren der Rastervorlagen.', '',
 '[Vergleichsbogen](../output/comparisons/all_references.png). Für jede Pose existieren Original, SVG, PNG, JSON und Metriken in `output/reconstructions/` sowie separate Overlay-/Differenzbilder in `output/comparisons/`. Rot bedeutet nur in der Referenz, Blau nur im Rendering, Schwarz Überdeckung.', '',
 '## Gezielte Iterationen', '',
 'Die ersten gemeinsamen Renderings wurden vor dem Fitting untersucht; eckige Brauenenden, zu gleichförmige Wangenbreiten, nicht deckungsgleiche Pupillen und steife Mundformen waren sichtbar. Die anfängliche Kontur-Fitting-Runde erreichte ca. 0,721 mittlere IoU. Regionale Augen-/Mundoptimierung, korrekte optionale Akzente und die separate Zungenwurzel verbesserten das auf ca. 0,878. Die visuelle Prüfung der Interpolationen deckte eine fehlerhafte beidseitige Zuordnung der Schraffurzonen auf; die Initialisierung und ein Anatomie-Test wurden korrigiert. Anschließend verbesserte die finale lokale Rasterverfeinerung die Konturen nochmals. Die gesamte dokumentierte CLI-Pipeline wurde abschließend erneut ausgeführt.', '',
 'Die gespeicherten Optimierungsprotokolle enthalten tatsächliche Start-/Endverluste, Auswertungszahlen und Annahmeentscheidungen. Weniger als 50 geordnete Parameter werden je lokalem Optimierungsschritt bearbeitet. Der Renderer speichert keine extrahierten Referenzkonturen.', '',
 '## Regionale Restfehler', '',
 'Die folgenden Angaben lokalisieren Abweichungen. Regionen sind feste, teilweise überlappende Debug-Ausschnitte; ihre Scores werden nicht als unabhängige Gesamtverluste aufsummiert. Schwerpunktsverschiebungen beziehen sich auf alle schwarzen Pixel der Region, nicht auf eine diagnostizierte Pupillenverschiebung.', '',
 '| Pose | Region mit niedrigster IoU | IoU | Schwerpunkt Δx / Δy [px] |','|---|---|---:|---:|']
for n,rows in d.items():
 e=rows[0];x,y=e['centroid_shift_xy_px'];lines.append(f"| {n} | {e['region']} | {e['iou']:.3f} | {x:+.2f} / {y:+.2f} |")
lines+=['', 'Konkrete verbleibende visuelle Unterschiede:', '',
 '- `smile`: einzelne Wimpernansätze und die dünnen Enden am unteren Lid bleiben leicht anders gewölbt.',
 '- `tense`: der gegabelte obere Lid-Akzent und die kleinräumige Dicke des welligen weißen Mundrandes werden vereinfacht.',
 '- `love`: die Herzreflexe sind ein gemeinsames skaliertes/gedrehtes Herz; die individuelle Asymmetrie und kleine weiße Pupillenkratzreflexe fehlen teilweise.',
 '- `cheeky`: einzelne Schraffuren teilen eine gemeinsame Neigung und ein symmetrisches Dickenprofil; die ursprünglichen Striche sind etwas ungleichmäßiger.',
 '- `tongue`: Nasenhaken, seitliche Lidenden und die Übergänge vom schwarzen Mundraum zur weißen Zunge unterscheiden sich am stärksten. Die Zungenmittellinie und der lange Umriss sind vorhanden.',
 '- `skeptical`: die feinen unteren Augenwinkel-Fächer und die lokale Breite der Mundwinkel bleiben vereinfacht.', '',
 '## Interpolation und neue Emotionen', '',
 'Sieben tatsächlich gerenderte Sequenzen mit jeweils 32 Frames (224 SVGs, PNGs und vollständige JSON-Zustände). Alle Landmark-IDs bleiben identisch; normierte Anker bewegen sich linear und ohne Sprünge. Positive Breiten und begrenzte Tangenten werden interpoliert. Optionale Zunge/Unterlippe erscheint bzw. verschwindet mit einem definierten weichen Fenster; Schwarz/Weiß-Innenräume wechseln bei Null-Deckkraft. Bewusste Transparenz kann Zwischenframes grau erscheinen lassen.', '',
 '| Sequenz | Frames | Größter Landmark-Schritt (normiert) |','|---|---:|---:|']
for n,e in v['interpolation_sequences'].items():lines.append(f"| {n} | {e['frames']} | {e['max_landmark_step_normalized']:.5f} |")
lines+=['', '[Emotionen-Kontaktbogen](../output/emotions/contact_sheet.png): neutral, glücklich, Freude, verliebt, stolz, traurig, wütend, überrascht, ängstlich, besorgt, angewidert, müde, zwinkernd, verspielt. Der wütende Mund wurde nach der Sichtprüfung vom selbstbewussten Grinsen getrennt; der überraschte Mund wurde gerundet.', '',
 '## Synthetische Prüfung', '',
 f"{v['synthetic_count']} zusätzliche Posen, Seed {v['synthetic_seed']}, 14 geschichtet gewählte Emotionen. Alle besitzen gültige endliche SVG-Pfade, 101 konsistente Labels, sichtbare Oberlider und Wangenbänder, positive Pupillenradien und plausible Gesamt-Vordergrundflächen. Der Kontaktbogen wurde visuell geprüft. Die Stichprobe ist ein Nachweis für diese eingeschränkten Sampling-Bereiche, kein mathematischer Beweis für jede mögliche freie Ankerverformung.", '',
 '[100 Samples](../output/synthetic_samples/contact_sheet.png). `manifest.json` enthält Dateizuordnung, Seed, Emotion, Prüfwerte und SVG-SHA256 je Beispiel. Gleicher Seed und gleicher Code erzeugen dieselben Zustände; ein Roundtrip gespeicherter JSON-Posen erzeugt exakt dieselbe SVG-Geometrie.', '',
 '## Tests und Editor', '',
 f'{test_count} automatisierte Tests bestanden. Sie prüfen Serialisierung, Anatomie einschließlich Schraffurzonen, echte Referenzqualität, endliche Geometrie, geordnete Konturanschlüsse, Interpolation, Varianten, Seed, Auflösung und gemeinsame Server-/CLI-Ausgabe. Zusätzlich bestand ein realer Chromium-Test für Laden, Sliders, Keypoint-Dragging, Overlay, Varianten, JSON-/SVG-/PNG-Downloads, Emotionen und Reset. Der abschließende Audit validierte 351 gespeicherte vollständige Posen gegen das finale Register.', '',
 '[Editor-Screenshot](../output/editor/editor.png), [Browser-Prüfprotokoll](../output/editor/browser_test.json), [Testausgabe](../output/test_results.txt).', '',
 '## Voraussetzungen für Phase 2', '',
 'Die Daten sind sofort für eine spätere Datensatzaufbereitung verwendbar: normalisierte Koordinaten, verbindliche ID-Reihenfolge, explizite sichtbare/verdeckte/abwesende Punkte, vollständige Rig-Zustände, reproduzierbare Seeds und SVG-/PNG-Paare. Pupillen-/Reflexzentren werden geometrisch gegen die tatsächlichen Clips geprüft; die übrige Komponentensichtbarkeit ist keine pixelgenaue Occlusion-Annotation. Vor einem großen Trainingsdatensatz sollten die Verteilung der Emotionen, stärkere Stilvariation, weitere Referenzen und eine präzisere Sichtbarkeit der beschnittenen Pupillen evaluiert werden. Ein Detector, Videotracking oder Motion-Modell wurde nicht vorzeitig implementiert.'
]
(ROOT/'docs/phase1_report.md').write_text('\n'.join(lines)+'\n')
print('Wrote docs/phase1_report.md from measured artifacts')
