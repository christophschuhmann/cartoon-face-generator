# Sechs gefittete Referenzposen

[Repository-Startseite](../README.md) · [Datenformat](../docs/data_format.md)

Alle Dateien sind vollständige Zustände desselben parametrischen Gesichts, einschließlich der **101 Keypoints**, interner Rig-Werte und Sichtbarkeiten. Der Renderer benötigt dafür kein Originalbild.

| Datei | Ausdruck |
|---|---|
| [smile.json](smile.json) | freundliches asymmetrisches Lächeln |
| [tense.json](tense.json) | unsicher / angespannt |
| [love.json](love.json) | verliebt / begeistert, Herzreflexe und Innenzunge |
| [cheeky.json](cheeky.json) | schelmisches Grinsen |
| [tongue.json](tongue.json) | verspielt mit herausgestreckter Zunge |
| [skeptical.json](skeptical.json) | skeptisch mit asymmetrischen Brauen |

Neue Emotionsarchetypen stehen unter [output/emonet/archetypes](../output/emonet/archetypes); die 60 zusätzlichen Ausdrücke unter [output/social/archetypes](../output/social/archetypes). Sie benutzen dieselbe Topologie. Die archivierten Referenzposen behalten ihren ursprünglichen Geometriemodus; neue Rezepte verwenden die weichere Geometrie und den gemeinsamen Unteraugenübergang.

```bash
.venv/bin/face render --pose poses/smile.json --output output/example.svg --png output/example.png
```

Befehle im Repository-Hauptordner ausführen. Vor erneutem `fit_references` eigene bearbeitete Posen unter einem anderen Namen sichern.
