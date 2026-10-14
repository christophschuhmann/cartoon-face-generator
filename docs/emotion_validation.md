# Emotionsschicht: Ergebnisse und verbleibende Grenzen

[Dokumentationsindex](README.md) · [Aktuelle Unteraugen-Morphs](under_eye.md)

Dieser Bericht beschreibt den dokumentierten Emotions-/Stil-Prüflauf für Rezept 1.1. Die aktuellen EmoNet-Rezepte verwenden 1.2 und zusätzlich `stroke_bank_v1`; alle aktuellen Galerieposen wurden neu erzeugt und validiert. Die unten genannten 114 Tests sind die damalige Suite, nicht die Größe der heutigen Testsuite. Menschliche Erkennungsgenauigkeit wurde weiterhin nicht gemessen.

## Implementierter Umfang

40 Kategorien aus der festgehaltenen offiziellen EmoNet-Face-Taxonomie, jeweils ein Archetyp und ein eigener prozeduraler Variationsraum. Alle verwenden das bestehende `cartoon_face_v1` mit 101 unveränderten IDs und denselben Python/SVG-Renderer. Eine Pose wird als vollständiges JSON mit Geometrie, Rig, Sichtbarkeit, beabsichtigtem Label, 40 Steuergewichten und Rezept gespeichert. Der Editor unterstützt Archetypen, Seeds, Mischungen und manuelle Nachbearbeitung; die Galerie unterstützt separate menschliche Bewertungen.

Rezeptversion dieses Stilberichts: **1.1**. Die subtile Überarbeitung der Strichenden, Mundrundung und Charakterwärme ist mit echten Vorher/Nachher-Renderings in [emotion_refinement.md](emotion_refinement.md) dokumentiert. Archivierte Rezept-1.0-Posen behalten ihre ursprüngliche SVG-Geometrie. Die neueren Unteraugen-Übergänge sind separat in [under_eye.md](under_eye.md) beschrieben.

## Tatsächlich ausgeführte Prüfungen

| Prüfung | Gemessenes Ergebnis |
|---|---|
| Archetypen | 40 SVG/PNG/JSON-Pakete |
| Neue Varianten | 320, 8 pro Kategorie, Basis-Seed 42 |
| Gültige Form- und Zielhinweisprüfungen | `True` für sämtliche Archetypen und Varianten |
| Unterschiedliche Varianten-SVGs | 8–8 pro Kategorie |
| Mittlere Koordinaten-Streuung pro Kategorie | 0.001059–0.003557, normalisierte Einheiten |
| Schwarzer Flächenanteil der Varianten | 5.77–12.69 % bei Grau <128 |
| Emotionspaare numerisch | 780, jeweils bei 25/50/75 %; alle geometrisch gültig: `True` |
| Gerenderte Übergänge | 12 Sequenzen mit zusammen 384 SVG/PNG/JSON-Frames |
| Automatisierte Tests | 114 passed in 13.27s |
| Echter Chromium-Test | `True`, 16 Editor-/Galerie-Prüfungen, keine JS-Fehler |
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
| [amusement_teasing](../output/emonet/mixtures/amusement_teasing/contact_sheet.png) | 32 | 0.004031 | recommended |
| [awe_surprise](../output/emonet/mixtures/awe_surprise/contact_sheet.png) | 32 | 0.001128 | recommended |
| [fear_distress](../output/emonet/mixtures/fear_distress/contact_sheet.png) | 32 | 0.002279 | recommended |
| [gratitude_affection](../output/emonet/mixtures/gratitude_affection/contact_sheet.png) | 32 | 0.005611 | recommended |
| [triumph_pride](../output/emonet/mixtures/triumph_pride/contact_sheet.png) | 32 | 0.005724 | recommended |
| [embarrassment_shame](../output/emonet/mixtures/embarrassment_shame/contact_sheet.png) | 32 | 0.001736 | recommended |
| [sadness_helplessness](../output/emonet/mixtures/sadness_helplessness/contact_sheet.png) | 32 | 0.001684 | recommended |
| [doubt_confusion](../output/emonet/mixtures/doubt_confusion/contact_sheet.png) | 32 | 0.003166 | recommended |
| [disgust_sourness](../output/emonet/mixtures/disgust_sourness/contact_sheet.png) | 32 | 0.005924 | recommended |
| [contentment_relief](../output/emonet/mixtures/contentment_relief/contact_sheet.png) | 32 | 0.001250 | recommended |
| [anger_elation](../output/emonet/mixtures/anger_elation/contact_sheet.png) | 32 | 0.005655 | ambivalent |
| [pain_pleasure_ecstasy](../output/emonet/mixtures/pain_pleasure_ecstasy/contact_sheet.png) | 32 | 0.005983 | ambivalent |


Staunen→Überraschung, Lachen→Necken, Traurigkeit→Hilflosigkeit und Zweifel→Verwirrung zeigen nachvollziehbare kontinuierliche Formänderungen. Bei den betrachteten Kontaktbögen waren keine zerstörten Konturen oder wechselnden Landmark-Identitäten sichtbar. Dankbarkeit/Zuneigung bleiben auch gemischt eher ein warmer allgemeiner Ausdruck.

Zorn→Hochgefühl kann mittig wie ein anderer aufgeregter Zustand wirken. Schmerz→Genuss kann mittig neutralere geschlossene Augen zeigen. Solche Paare sind als `ambivalent` gekennzeichnet. Sie bleiben technische Vektormischungen und werden nicht als validierte reine Kategorie ausgegeben. Die 780-Paare-Prüfung ist numerisch; nur die zwölf gelisteten Sequenzen wurden gerendert und im Kontaktbogen angesehen.

## Beobachtungen je Kategorie

Dies sind nachvollziehbare Designbeobachtungen des Coding-Agenten, keine unabhängigen menschlichen Klassifikationen.

| Kategorie | Beobachtung / verbleibende Mehrdeutigkeit |
|---|---|
| 1. Heiterkeit | Offenes Lachen und enge Augen sind deutlich; die Grenze zu allgemeiner Freude bleibt fließend. |
| 2. Hochgefühl | Weiter Blick und breites Lachen unterscheiden sich sichtbar von amusement. |
| 3. Genuss / Ekstase | Geschlossene weiche Augen und kleines Lächeln wirken entspannt; Ekstase braucht mehr Kontext. |
| 4. Zufriedenheit | Kleines geschlossenes Lächeln und ruhige enge Lider; Nähe zu Zuneigung und Stolz. |
| 5. Dankbarkeit | Weiche innere Brauen und warmes Lächeln; Dankbarkeit ist ohne Anlass nicht eindeutig. |
| 6. Zuneigung | Größere Pupillen und breiteres weiches Lächeln; Nähe zu Dankbarkeit. |
| 7. Verliebtheit | Herzreflexe erzeugen einen deutlichen stilisierten Liebeshinweis. |
| 8. Hoffnung / Optimismus | Aufwärtsblick und freundlicher Mund; ohne Kontext auch Interesse oder Stolz möglich. |
| 9. Triumph | Breites weißes Siegergrinsen wirkt kräftiger als pride; Erfolg selbst braucht Kontext. |
| 10. Stolz | Kontrolliertes schiefes Lächeln; Stolz und Verachtung können benachbart erscheinen. |
| 11. Interesse | Wachere Augen und zurückhaltender Mund; Aufmerksamkeit ohne eindeutige Emotionsursache. |
| 12. Staunen / Ehrfurcht | Große Pupillen und kleiner O-Mund; im Vergleich weicher als surprise. |
| 13. Überraschung | Kleine Pupillen, große Augen und großer O-Mund bilden eine klare Cartoon-Konstellation. |
| 14. Konzentration | Leichte Kontraktion und gepresster Mund; kann als ernster neutraler Zustand gelesen werden. |
| 15. Nachdenklichkeit | Seitlicher Aufwärtsblick, Brauenasymmetrie und gespitzter Mund; Nähe zu doubt. |
| 16. Erleichterung | Entspannte enge Lider und Ausatem-Mund; kann auch erschöpft wirken. |
| 17. Sehnsucht | Seitlicher wehmütiger Blick; Sehnsucht bleibt ohne Gegenstand mehrdeutig. |
| 18. Necken | Zwinkern, schiefes Grinsen und Zunge bleiben auch in Varianten erhalten. |
| 19. Ungeduld / Gereiztheit | Gereizter Seitenblick; Ungeduld lässt sich statisch kaum von milder Wut trennen. |
| 20. Begehren | Schwere Lider und offener kleiner Smile; Flirt/Begehren ist ohne Kontext nicht sicher. |
| 21. Zweifel | Asymmetrische Brauen und unterschiedliches Zusammenkneifen geben einen skeptischen Eindruck. |
| 22. Angst | Weite Augen und gespannter weißer Mund unterscheiden sich vom runden Überraschungsmund. |
| 23. Bedrängnis / Unruhe | Besorgte Brauen und kleine offene Abwärtsöffnung; Nähe zu Hilflosigkeit. |
| 24. Verwirrung | Suchender weiter Blick und schiefer kleiner offener Mund; Nähe zu doubt. |
| 25. Verlegenheit | Seitlich ausweichender Blick und unsicheres Lächeln unterscheiden sich von shame. |
| 26. Scham | Gesenkter enger Blick und kleiner trauriger Mund; Nähe zu Enttäuschung. |
| 27. Enttäuschung | Flacherer trauriger Mund und schwere Lider; Nähe zu Traurigkeit. |
| 28. Traurigkeit | Stark angehobene innere Brauen und klarer trauriger Mundbogen. |
| 29. Verbitterung | Schiefer missmutiger Mund; Verbitterung/Neid/Ungeduld bleiben nahe. |
| 30. Verachtung | Einseitig hochgezogener Mundwinkel sichtbar erhalten; Nähe zu Stolz. |
| 31. Ekel | Zusammenkneifen, Nasenanhebung und schiefer weißer Mund; noch ein schwächerer Ekelhinweis als eine anatomische Nasenfalte. |
| 32. Zorn | Die neue innere Brauenabsenkung ergibt einen deutlich härteren Blick als der erste freundliche Basisbogen. |
| 33. Boshaftigkeit | Harter Blick plus Grinsen bildet einen stilisierten boshaften Eindruck; keine universelle Boshaftigkeitsmimik. |
| 34. Säure-Reaktion | Ein stark geschlossenes Auge und gepresste kleine Lippen; bewusst stilisierte Geschmacksreaktion. |
| 35. Schmerz | Beidseitiger fester Lidschluss und größere offene Grimasse; Schmerz vs. Anstrengung bleibt kontextabhängig. |
| 36. Hilflosigkeit | Bittende innere Brauen und offener trauriger Mund; Nähe zu distress und sadness. |
| 37. Müdigkeit / Erschöpfung | Schwere Lider und kleiner Gähn-Mund bleiben sichtbar; niedrige Aktivierung erkennbar. |
| 38. Emotionale Leere | Flachere Brauen und waagerechter Mund; emotionale Leere kann ebenso neutral wirken. |
| 39. Benommenheit | Ungleiche schwere Lider und lockerer schiefer Mund; Benommenheit nicht sicher von Müdigkeit/Verwirrung zu trennen. |
| 40. Eifersucht / Neid | Gespannter harter Seitenblick; Neid braucht ein soziales Bezugsobjekt. |


## Unveränderte Referenzfähigkeit

Nach der gemeinsamen Pupillen-Clip-Korrektur wurden alle sechs Originalreferenzen erneut ausgewertet: mittlere Foreground-IoU **0.9096**, Dice **0.9526**, symmetrischer Konturabstand **0.925 kanonische Pixel**, ergänzende SSIM **0.9079**. Die neuen Emotionsrezepte ändern keine gefitteten Referenz-Keypoints und führen keine neue Renderer-Architektur ein.

[Referenzvergleich](../output/comparisons/all_references.png), [vollständige Referenzmetriken](../output/evaluation.json), [Phase-1-Bericht](phase1_report.md). Die alten sieben Interpolationen und 100 synthetischen Rig-Posen wurden ebenfalls neu gerendert und geprüft.

## Nächster sinnvoller Qualitätsschritt

Die technische Generierung für alle 40 Klassen ist vorhanden. Für garantiert treffende **Erkennung aller 40 Kategorien** fehlt ein menschlicher Test, insbesondere bei Dankbarkeit/Zuneigung, Stolz/Triumph, Scham/Enttäuschung und Neid/Verbitterung. Die neue Galerie ermöglicht Bewertungen mit ausgeblendeten Zielnamen und JSON-Export. `face evaluate_reviews` wertet echte Urteile aus, markiert unbewertete Kategorien mit `null` und liefert eine Konfusionsmatrix.

Anschließend sollten gerade häufig verwechselte Kategorien anhand dieser Bewertungen angepasst werden. Kleine Bewegungshinweise oder situativer Kontext könnten später weitere Unterschiede vermitteln; diese Version erzeugt statische Vektorgesichter und kontinuierliche Rig-Übergänge. Es wurden keine Detektoren, kein Training und keine Videoanalyse implementiert. Ein größeres synthetisches Trainingsset sollte intended labels und tatsächlich bewertete Labels getrennt führen.
