# Dokumentation: hier anfangen

[Zur Repository-Startseite](../README.md)

Wenn du das Projekt zum ersten Mal öffnest, lies zunächst den [Einstieg](getting_started.md). Für die Frage „Wo liegt die Datei, die ich brauche?“ gibt es den [Repository-Wegweiser](repository_map.md).

## Benutzen

| Anleitung | Inhalt |
|---|---|
| [Einstieg](getting_started.md) | Installation, erstes Bild, lokaler Editor, Webcam und Checkpoint-Download |
| [Vorschauen und Downloads](previews.md) | alle 100 Archetypen, Kontaktbögen, Vorschau-ZIP und andere Downloads |
| [CLI-Kochbuch](cli.md) | ausführbare Beispiele für Erzeugen, Mischen, Interpolation, Fitting und Datenexport |
| [Webcam-Demo](../webcam_mapper/README.md) | CPU-MediaPipe, Laptop-Setup, Kalibrierung, Bilder und Videos |
| [Training und Inferenz](../training/README.md) | Cartoon-Detector benutzen, Daten vorbereiten, Training reproduzieren |
| [LTX-2.5-Videos](../video_experiments/README.md) | Emotionswechsel, deutsche Sprache, Start-/End-/Zwischenbilder und gemessene Geschwindigkeit |

## Verstehen und erweitern

| Anleitung | Inhalt |
|---|---|
| [Repository-Wegweiser](repository_map.md) | Ordner und zentrale Dateien mit ihrem jeweiligen Zweck |
| [Architektur](architecture.md) | gemeinsamer Renderer, Keypoints versus Bézier-Geometrie, Datenfluss |
| [101-Punkte-Katalog](topology.md) | jede ID, Bedeutung, Region und Wirkung beim Verschieben |
| [Datenformat](data_format.md) | vollständiger Pose-Zustand, Einheiten, Sichtbarkeit und Python-Beispiele |
| [40 EmoNet-Kategorien](emotions.md) | Herkunft der Taxonomie, Rezepte, Intensität und Variation |
| [60 soziale Ausdrücke](social_expressions.md) | alle Slugs, deutsche Namen und charakteristische Hinweise |
| [Unteraugen-Morphs](under_eye.md) | kontinuierlicher Übergang zwischen Kurven und Falten |
| [Datensatz und Augmentationen](dataset.md) | 105.000 Posen, Shards, Splits, Labeltransformationen, OOD |
| [Entwicklung](../CONTRIBUTING.md) | Tests, Änderungspunkte und Regeln für kompatible Daten |
| [English overview](overview_en.md) | shorter introduction for English-speaking readers |

## Ergebnisse nachvollziehen

| Bericht | Einordnung |
|---|---|
| [Referenzanalyse](reference_analysis.md) | Auswahl und ursprüngliche Bildanalyse |
| [Rekonstruktionsbericht](phase1_report.md) | sechs Originale und Grenzen des Basis-Rigs |
| [Emotionsvalidierung](emotion_validation.md) | geometrische und visuelle Prüfungen; keine behauptete menschliche Erkennungsrate |
| [Stilverfeinerung](emotion_refinement.md) | historischer Schritt von Rezept 1.0 zu 1.1 |
| [Detector-Ergebnisse](detector_results.md) | tatsächliche Testmessungen, Originalreferenzen und OOD-Schwächen |
| [Erweiterte Detector-Suche](detector_search.md) | zusätzliche Varianten, stärkere Augmentationen und Auswahl auf unverändertem Holdout |
| [Maschinenlesbare Manifeste](artifacts/README.md) | Datensatz-Fingerprint, vollständiger Audit und Trainingsaufteilung |

Die aktuellen Rezepte sind **EmoNet 1.2** und **Social 1.1**, bei unveränderter Topologie `cartoon_face_v1`. Historische Berichte beschreiben ihre damaligen Prüfläufe. Vollständig gespeicherte Posen behalten ihren eigenen Geometriemodus und sind die verbindliche Grundlage für erneutes Rendern.
