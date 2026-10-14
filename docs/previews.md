# Bilder ansehen und Dateien herunterladen

[Dokumentationsindex](README.md) · [Ausgabeordner](../output/README.md)

## Direkt im Repository

| Sammlung | Übersicht | Einzeldateien |
|---|---|---|
| 40 EmoNet-Face-Archetypen | [Kontaktbogen](../output/emonet/archetypes/contact_sheet.png) | [SVG/PNG/JSON](../output/emonet/archetypes) |
| 60 soziale/cartoonhafte Archetypen | [Kontaktbogen](../output/social/archetypes/contact_sheet.png) | [SVG/PNG/JSON](../output/social/archetypes) |
| Beispiele mit Zufallsvariation | [EmoNet](../output/emonet/variations) | [Social](../output/social/variations) |
| Rekonstruktion der sechs Originale | [Vergleich aller Referenzen](../output/comparisons/all_references.png) | [Rekonstruktionen](../output/reconstructions) |
| 101 feste Landmark-IDs | [nummerierte Übersicht](landmarks/overview.png) | [regionale Abbildungen](landmarks) |
| weicher Unteraugenübergang | [Kurve → Falten](../output/under_eye/transition.png) | [technische Erklärung](under_eye.md) |
| mild augmentierte Bilder | [sauber / verändert / Labels](../output/dataset_previews/augmentation_examples.png) | [Augmentationskonventionen](dataset.md) |
| extreme OOD-Verformungen | [Ausgang / OOD / Labels](../output/dataset_previews/ood_examples.png) | [gemessene Detector-Grenzen](detector_results.md) |
| Human-Foto → Avatar | [Vergleich](../webcam_mapper/output/verification/human_to_cartoon_comparison.png) | [Mapper-Prüfbericht](../webcam_mapper/output/verification/verification_report.json) |

Dateinamen wie `32_anger.svg`, `32_anger.png` und `32_anger.json` gehören zusammen. Die Zahl ist die **Kategorie-ID im betreffenden Katalog**, keine Landmark-ID. Die JSON-Datei enthält alle 101 Punkte samt Rig. Variationen liegen in nach Ausdruck benannten Unterordnern; ihr Dateiname enthält Index und Seed.

## Ein ZIP mit sämtlichen Ausdrucksvorschauen

[expression_previews.zip herunterladen](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.0.0/expression_previews.zip)

Enthalten sind:

- alle **40 EmoNet-Archetypen und 60 sozialen Archetypen**;
- **320 EmoNet-Variationen und 240 soziale Variationen** mit Seed 42;
- je Zustand SVG, PNG und vollständiges Pose-JSON;
- die Kontaktbögen, Katalog-Manifeste und eine kurze Erläuterung.

Das ZIP enthält insgesamt **660 Gesichtszustände** und ist 90.231.804 Bytes groß, also etwa 90 MB (86 MiB). Die inneren Pfade beginnen mit `output/emonet/` und `output/social/`. Der Git-Checkout enthält alle Archetypen, aber zur Begrenzung der Repository-Größe nur je eine Beispielvariation pro Kategorie.

SHA-256 des ZIP:

```text
1d5dbcc918ddbcaeb129ec3e837014f2955dbc27205879620b165bd46b9ae4f9
```

Das Vorschau-ZIP ist **nicht der 105.000-Pose-Trainingsdatensatz**. Den großen Datensatz erzeugt [build_dataset](cli.md) reproduzierbar; seine Manifeste stehen unter [docs/artifacts](artifacts/README.md).

## Webcam und Detector separat herunterladen

| Datei | Zweck | Größe |
|---|---|---:|
| [cartoon_webcam_mapper.zip](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.0.0/cartoon_webcam_mapper.zip) | eigenständige Laptop-Demo mit gemeinsamem Renderer und geprüftem MediaPipe-Modell | 3.426.627 Bytes |
| [cartoon_landmarks_best.pt](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.0.0/cartoon_landmarks_best.pt) | gewählter PyTorch-Checkpoint des Cartoon-Detectors | 4.092.674 Bytes |

Das Webcam-ZIP entpacken und seine [Installationsschritte](../webcam_mapper/README.md) ausführen; Python-Abhängigkeiten müssen einmal installiert werden. Den Detector-Checkpoint beispielsweise unter `output/detector/best.pt` speichern und nach [Trainings-/Inferenzanleitung](../training/README.md) laden.

Alle Downloads liegen im [Release v1.0.0](https://github.com/christophschuhmann/cartoon-face-generator/releases/tag/v1.0.0). Der Source-Code-Download von GitHub enthält diese Release-Assets nicht automatisch.
