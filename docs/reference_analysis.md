# Bestandsaufnahme der sechs Referenzen

Alle sechs Bilder sind isolierte Gesichtsillustrationen. Keine Roboterfotos vorhanden. Originaldateien bleiben unverändert.

| Pose | Datei | Auflösung | Ausdruck / Details |
|---|---|---|---|
| smile | ChatGPT-Bild 13. Okt. 2026, 19_43_48.png | [1536, 864] | Freundliches asymmetrisches Lächeln; breite aufwärts geschwungene Brauen; runde Pupillen; je ein Lichtreflex; durchgehende kurze Unteraugenkurven. |
| tense | ChatGPT-Bild 13. Okt. 2026, 19_45_19.png | [1536, 864] | Unsicher/angespannt; links hochgezogene, rechts abgesenkte Braue; enger welliger offener Mund mit weißem Innenraum; Schraffuren und doppelte Lichtreflexe. |
| love | ChatGPT-Bild 13. Okt. 2026, 19_45_42.png | [1536, 864] | Verliebt/begeistert; weiße Herzreflexe in schwarzen Pupillen, zusätzlicher runder Reflex; schwarzer offener Mund mit weißer Innenzunge; Schraffuren. |
| cheeky | ChatGPT-Bild 13. Okt. 2026, 19_46_02.png | [1536, 864] | Schelmisches Lächeln; ähnlich tense/love in Augen und Brauen, geschlossenes aufwärts gerichtetes Lächeln; Schraffuren. |
| tongue | ChatGPT-Bild 13. Okt. 2026, 19_46_23.png | [1536, 864] | Verspielt mit herausgestreckter Zunge; stark geöffnete Augen mit entgegengesetzter Blickrichtung; dünnere Brauen; lange weiße Zunge mit schwarzem Rand und Mittellinie; zusätzliche Augenwinkelstriche. |
| skeptical | ChatGPT-Bild 13. Okt. 2026, 19_46_42.png | [1536, 864] | Skeptisch/selbstbewusst; gegensinnig gekrümmte Brauen; schräge obere Lider; nach innen gerichteter Blick; breites flaches Lächeln und kleiner Unterlippenstrich; Schraffuren. |

## Gemeinsame Formensprache

Zwei unabhängig geformte breite Brauen; jeweils ein stark betontes oberes Lid mit äußerer Wimper, feine seitliche und untere Lidkurven; leicht elliptische schwarze Pupillen und weiße Reflexe. Eine kleine bogenförmige Nase. Zwei gefüllte Wangenbänder mit dünner werdender äußerer Spirale. Kein Gesichtsumriss.

Die Wangenbänder, Brauen und Lidformen sind kontinuierlich deformierbar. Die diskreten Modi sind Unteraugendekoration (none/continuous/hatching/mixed), Reflex (round/heart) und Mundinnenraum (dark/white). Zunge und Akzentstriche sind optionale feste Komponenten. Sichtbarkeit wird weich als Deckkraft interpoliert; Landmark-IDs werden niemals umgeordnet.

## Vorverarbeitung

Gemeinsamer Ausschnitt [42, 56, 1492, 806] (x0,y0,x1,y1, rechte/untere Grenze exklusiv), 1450 × 750 Pixel. Dieser Ausschnitt liegt in allen sechs weißen Bildschirmen. Keine Rotation, kein Resize, kein Thresholding oder Glätten der gespeicherten Referenzen. Affine Transformation: x′=x−42, y′=y−56. Normalisierung: u=x′/1450, v=y′/750. Die Rastermasken für Metriken verwenden Grau<128; Details bleiben im RGB-Original erhalten.

## Modellentscheidung vor Implementierung

Semantische Anker auf den Mittellinien und an den Mund-/Augengrenzen. Interne Hermite-Tangenten und positive Breitenprofile erzeugen glatte gefüllte Bézier-Bänder. Die Spirale erhält eigene Anker für Bauch, Außenbogen, Scheitel und Spitze. Keine Referenzkonturen werden im Renderer gespeichert. Zusatzstriche werden aus festen Akzentankern und einer parametrierten Schraffurzone erzeugt. Alle sechs Posen teilen identische Komponenten und Landmark-Reihenfolge.