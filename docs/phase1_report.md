# Phase-1-Ergebnisbericht

[Dokumentationsindex](README.md) · [Aktueller Projektumfang](../README.md)

Dieser Bericht dokumentiert den ursprünglichen Phase-1-Prüflauf. Die Rekonstruktionswerte bleiben gültig; die weiter unten genannten Testzahlen und damaligen nächsten Schritte sind historische Angaben. Inzwischen sind die [105.000-Pose-Daten](dataset.md), das [trainierte Landmark-Modell](detector_results.md) und der [separate MediaPipe-Mapper](../webcam_mapper/README.md) hinzugekommen.

Implementiert und ausgeführt: gemeinsames parametrisches SVG-Rig, 101 feste semantische Landmarks, sechs automatisch optimierte Parametersätze, lokaler Editor, Interpolation und 100 zusätzliche synthetische Zustände. Die Ergebnisse wurden als tatsächliche SVGs gerendert und mehrfach visuell mit den Originalen verglichen. Alle Werte unten stammen aus `output/evaluation.json`.

## Rekonstruktion aller sechs Originale

Arbeitsauflösung: 1450 × 750 Pixel nach identischem rahmenfreien Ausschnitt. Keine Glättung der RGB-Referenzen. Maskenschwelle Grau<128. IoU/Dice: höher ist besser; symmetrischer mittlerer Konturabstand: niedriger ist besser. Mittelwerte sind arithmetische Mittel der sechs Posen.

| Pose | Foreground-IoU | Dice | Konturabstand [px] | Kontur-p95 [px] | SSIM |
|---|---:|---:|---:|---:|---:|
| smile | 0.9353 | 0.9666 | 0.666 | 2.236 | 0.9050 |
| tense | 0.9112 | 0.9535 | 0.972 | 2.828 | 0.9068 |
| love | 0.9192 | 0.9579 | 0.846 | 2.828 | 0.8950 |
| cheeky | 0.9228 | 0.9599 | 0.998 | 2.828 | 0.9033 |
| tongue | 0.8784 | 0.9352 | 0.989 | 3.606 | 0.9240 |
| skeptical | 0.8911 | 0.9424 | 1.078 | 4.000 | 0.9131 |
| **Mittel** | **0.9096** | **0.9526** | **0.925** | — | **0.9079** |

SSIM ist durch die Referenztextur und die großen weißen Flächen beeinflusst. Die SVGs reproduzieren die Vektorformen, nicht das leichte Korn oder sehr schwache Kratzspuren der Rastervorlagen.

[Vergleichsbogen](../output/comparisons/all_references.png). Für jede Pose existieren Original, SVG, PNG, JSON und Metriken in `output/reconstructions/` sowie separate Overlay-/Differenzbilder in `output/comparisons/`. Rot bedeutet nur in der Referenz, Blau nur im Rendering, Schwarz Überdeckung.

## Gezielte Iterationen

Die ersten gemeinsamen Renderings wurden vor dem Fitting untersucht; eckige Brauenenden, zu gleichförmige Wangenbreiten, nicht deckungsgleiche Pupillen und steife Mundformen waren sichtbar. Die anfängliche Kontur-Fitting-Runde erreichte ca. 0,721 mittlere IoU. Regionale Augen-/Mundoptimierung, korrekte optionale Akzente und die separate Zungenwurzel verbesserten das auf ca. 0,878. Die visuelle Prüfung der Interpolationen deckte eine fehlerhafte beidseitige Zuordnung der Schraffurzonen auf; die Initialisierung und ein Anatomie-Test wurden korrigiert. Anschließend verbesserte die finale lokale Rasterverfeinerung die Konturen nochmals. Die gesamte dokumentierte CLI-Pipeline wurde abschließend erneut ausgeführt.

Die gespeicherten Optimierungsprotokolle enthalten tatsächliche Start-/Endverluste, Auswertungszahlen und Annahmeentscheidungen. Weniger als 50 geordnete Parameter werden je lokalem Optimierungsschritt bearbeitet. Der Renderer speichert keine extrahierten Referenzkonturen.

## Regionale Restfehler

Die folgenden Angaben lokalisieren Abweichungen. Regionen sind feste, teilweise überlappende Debug-Ausschnitte; ihre Scores werden nicht als unabhängige Gesamtverluste aufsummiert. Schwerpunktsverschiebungen beziehen sich auf alle schwarzen Pixel der Region, nicht auf eine diagnostizierte Pupillenverschiebung.

| Pose | Region mit niedrigster IoU | IoU | Schwerpunkt Δx / Δy [px] |
|---|---|---:|---:|
| smile | left_eye | 0.908 | -0.05 / -0.77 |
| tense | left_eye | 0.879 | +0.59 / +1.62 |
| love | left_eye | 0.875 | +1.06 / +0.87 |
| cheeky | left_eye | 0.889 | -0.94 / +1.03 |
| tongue | nose | 0.808 | -0.65 / -1.45 |
| skeptical | left_eye | 0.842 | +0.18 / +0.41 |

Konkrete verbleibende visuelle Unterschiede:

- `smile`: einzelne Wimpernansätze und die dünnen Enden am unteren Lid bleiben leicht anders gewölbt.
- `tense`: der gegabelte obere Lid-Akzent und die kleinräumige Dicke des welligen weißen Mundrandes werden vereinfacht.
- `love`: die Herzreflexe sind ein gemeinsames skaliertes/gedrehtes Herz; die individuelle Asymmetrie und kleine weiße Pupillenkratzreflexe fehlen teilweise.
- `cheeky`: einzelne Schraffuren teilen eine gemeinsame Neigung und ein symmetrisches Dickenprofil; die ursprünglichen Striche sind etwas ungleichmäßiger.
- `tongue`: Nasenhaken, seitliche Lidenden und die Übergänge vom schwarzen Mundraum zur weißen Zunge unterscheiden sich am stärksten. Die Zungenmittellinie und der lange Umriss sind vorhanden.
- `skeptical`: die feinen unteren Augenwinkel-Fächer und die lokale Breite der Mundwinkel bleiben vereinfacht.

## Interpolation und neue Emotionen

Sieben tatsächlich gerenderte Sequenzen mit jeweils 32 Frames (224 SVGs, PNGs und vollständige JSON-Zustände). Alle Landmark-IDs bleiben identisch; normierte Anker bewegen sich linear und ohne Sprünge. Positive Breiten und begrenzte Tangenten werden interpoliert. Optionale Zunge/Unterlippe erscheint bzw. verschwindet mit einem definierten weichen Fenster; Schwarz/Weiß-Innenräume wechseln bei Null-Deckkraft. Bewusste Transparenz kann Zwischenframes grau erscheinen lassen.

| Sequenz | Frames | Größter Landmark-Schritt (normiert) |
|---|---:|---:|
| smile_cheeky | 32 | 0.00469 |
| cheeky_love | 32 | 0.00482 |
| smile_tongue | 32 | 0.00711 |
| cheeky_skeptical | 32 | 0.00803 |
| tense_love | 32 | 0.00482 |
| neutral_surprised | 32 | 0.00711 |
| neutral_sleepy | 32 | 0.00626 |

[Emotionen-Kontaktbogen](../output/emotions/contact_sheet.png): neutral, glücklich, Freude, verliebt, stolz, traurig, wütend, überrascht, ängstlich, besorgt, angewidert, müde, zwinkernd, verspielt. Der wütende Mund wurde nach der Sichtprüfung vom selbstbewussten Grinsen getrennt; der überraschte Mund wurde gerundet.

## Synthetische Prüfung

100 zusätzliche Posen, Seed 42, 14 geschichtet gewählte Emotionen. Alle besitzen gültige endliche SVG-Pfade, 101 konsistente Labels, sichtbare Oberlider und Wangenbänder, positive Pupillenradien und plausible Gesamt-Vordergrundflächen. Der Kontaktbogen wurde visuell geprüft. Die Stichprobe ist ein Nachweis für diese eingeschränkten Sampling-Bereiche, kein mathematischer Beweis für jede mögliche freie Ankerverformung.

[100 Samples](../output/synthetic_samples/contact_sheet.png). `manifest.json` enthält Dateizuordnung, Seed, Emotion, Prüfwerte und SVG-SHA256 je Beispiel. Gleicher Seed und gleicher Code erzeugen dieselben Zustände; ein Roundtrip gespeicherter JSON-Posen erzeugt exakt dieselbe SVG-Geometrie.

## Tests und Editor

114 automatisierte Tests bestanden. Sie prüfen Serialisierung, Anatomie einschließlich Schraffurzonen, echte Referenzqualität, endliche Geometrie, geordnete Konturanschlüsse, Interpolation, Varianten, Seed, Auflösung und gemeinsame Server-/CLI-Ausgabe. Zusätzlich bestand ein realer Chromium-Test für Laden, Sliders, Keypoint-Dragging, Overlay, Varianten, JSON-/SVG-/PNG-Downloads, Emotionen und Reset. Der abschließende Audit validierte 351 gespeicherte vollständige Posen gegen das finale Register.

[Editor-Screenshot](../output/editor/editor.png), [Browser-Prüfprotokoll](../output/editor/browser_test.json), [Testausgabe](../output/test_results.txt).

## Voraussetzungen für Phase 2

Die Daten sind sofort für eine spätere Datensatzaufbereitung verwendbar: normalisierte Koordinaten, verbindliche ID-Reihenfolge, explizite sichtbare/verdeckte/abwesende Punkte, vollständige Rig-Zustände, reproduzierbare Seeds und SVG-/PNG-Paare. Pupillen-/Reflexzentren werden geometrisch gegen die tatsächlichen Clips geprüft; die übrige Komponentensichtbarkeit ist keine pixelgenaue Occlusion-Annotation. Vor einem großen Trainingsdatensatz sollten die Verteilung der Emotionen, stärkere Stilvariation, weitere Referenzen und eine präzisere Sichtbarkeit der beschnittenen Pupillen evaluiert werden. Ein Detector, Videotracking oder Motion-Modell wurde nicht vorzeitig implementiert.
