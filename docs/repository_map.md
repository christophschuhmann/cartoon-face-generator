# Was liegt wo?

[Dokumentationsindex](README.md) · [Architektur](architecture.md)

Die drei wichtigsten Orte sind **`src/cartoon_face/` für den Generator**, **`output/` für sichtbare Ergebnisse** und **`docs/` für Erklärungen**. Die beiden Anwendungen für Training und Webcam haben jeweils einen eigenen Ordner und eine eigene README.

## Hauptordner

| Pfad | Was liegt hier? | Wann brauche ich das? |
|---|---|---|
| [README.md](../README.md) | Überblick und Einstieg | beim ersten Besuch |
| [images/](../images) | unveränderte ursprüngliche Referenzbilder | Originale ansehen oder Rekonstruktion wiederholen |
| [poses/](../poses) | sechs gefittete vollständige Pose-JSONs | Originalausdrücke rendern und als Ausgangspose verwenden |
| [src/cartoon_face/](../src/cartoon_face) | gemeinsame Python-Implementierung | Rig, Generierung, Rendering oder Augmentation ändern |
| [viewer/](../viewer) | HTML, CSS und JavaScript für Editor/Galerien | Oberfläche ändern; Start über `face serve` |
| [output/](../output) | generierte Bilder, Vergleichsbilder und Berichte | Ergebnisse beurteilen; [Ausgabeindex](../output/README.md) |
| [docs/](.) | lesbare Dokumentation, Punktabbildungen und Manifeste | Datenformat und Modell verstehen |
| [tools/](../tools) | Hilfsskripte, Audit und Browserprüfung | Berichte erneuern oder Qualität überprüfen |
| [tests/](../tests) | automatisierte Vertrag-, Geometrie- und Pipeline-Tests | Änderungen prüfen |
| [training/](../training) | kleiner Cartoon-Landmark-Detector | trainieren oder Cartoon-Bilder vorhersagen |
| [webcam_mapper/](../webcam_mapper) | CPU-MediaPipe → Cartoon-Avatar | Human-Webcam, Foto oder Video auf das Rig abbilden |
| [video_experiments/](../video_experiments/README.md) | separate LTX-2.5-Videotests | Emotionswechsel mit Dialog und Stützframes erzeugen und messen |
| `datasets/` | lokal erzeugte große Shards und Rastercaches | Datensatzproduktion/Training; absichtlich nicht in Git |
| [pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock) | Python-Paket und aufgelöste Generator-Abhängigkeiten | Installation |
| [AGENTS.md](../AGENTS.md) | Vorgaben für Coding-Agenten | automatisierte Beiträge |

`images/` wird tatsächlich klein geschrieben. `poses/` enthält vollständige Zustände und keine gespeicherten Referenzkonturen. Unter `output/` im Git-Checkout liegen ausgewählte Ergebnisse; umfangreiche Varianten und Sequenzen können zusätzlich lokal erzeugt werden.

## Der gemeinsame Generator im Detail

| Datei | Aufgabe |
|---|---|
| [topology/face_topology.json](../src/cartoon_face/topology/face_topology.json) | verbindliche 101 IDs, Komponentenzuordnung und Ankerreihenfolge |
| [topology/landmark_semantics.json](../src/cartoon_face/topology/landmark_semantics.json) | ergänzende lesbare Punktbedeutungen und Steuerwirkung |
| [topology/pose.schema.json](../src/cartoon_face/topology/pose.schema.json) | maschinenlesbares Pose-Schema |
| [model.py](../src/cartoon_face/model.py) | Pose laden/speichern/validieren, Koordinaten und Sichtbarkeit |
| [geometry.py](../src/cartoon_face/geometry.py) | aus Ankern abgeleitete Bézier-Kurven, variable Bandbreiten und Ellipsen |
| [components/__init__.py](../src/cartoon_face/components/__init__.py) | Augen, Brauen, Wangenlinien, Nase, Mund, Zunge und Details |
| [renderer.py](../src/cartoon_face/renderer.py) | SVG zusammenstellen und mit CairoSVG rasterisieren |
| [under_eye.py](../src/cartoon_face/under_eye.py) | gemeinsame kontinuierliche Strich-Slots für Unteraugenkurve/Falten |
| [expressions.py](../src/cartoon_face/expressions.py) | elementare Steueraktionen und 14 ursprüngliche Ausdruckspresets |
| [animation.py](../src/cartoon_face/animation.py) | vollständige Posen interpolieren und Ausdrucksziele mischen |
| [emotions/catalog.json](../src/cartoon_face/emotions/catalog.json) | die 40 EmoNet-Kategorien und unsere Mimikrezepte |
| [emotion_library.py](../src/cartoon_face/emotion_library.py) | EmoNet-Archetypen, Intensität und korrelierte Variationen |
| [emotions/social_catalog.json](../src/cartoon_face/emotions/social_catalog.json) | 60 zusätzliche soziale/cartoonhafte Rezepte |
| [social_expressions.py](../src/cartoon_face/social_expressions.py) | soziale Archetypen und geschützte Blick-/Zwinker-/Zungenhinweise |
| [large_dataset.py](../src/cartoon_face/large_dataset.py) | große deterministische SVG-/JSON-Shards und extreme OOD-Varianten |
| [augmentation.py](../src/cartoon_face/augmentation.py) | gemeinsame Transformation von Rasterbild und Landmark-Labels |
| [reference.py](../src/cartoon_face/reference.py), [seeds.py](../src/cartoon_face/seeds.py), [fitting.py](../src/cartoon_face/fitting.py) | Bildanalyse, semantische Initialisierung und automatische Optimierung |
| [evaluation.py](../src/cartoon_face/evaluation.py) | IoU, Dice, Konturabstand, SSIM und regionale Vergleichsbilder |
| [cli.py](../src/cartoon_face/cli.py) | sämtliche `face …`-Befehle |
| [server.py](../src/cartoon_face/server.py) | lokale Editor-/Galerie-API; ruft denselben Renderer auf |

## Gespeicherte Ergebnisse finden

| Gesuchtes Ergebnis | Pfad |
|---|---|
| alle 40 EmoNet-Archetypen | [output/emonet/archetypes/](../output/emonet/archetypes) |
| alle 60 zusätzlichen Archetypen | [output/social/archetypes/](../output/social/archetypes) |
| Beispielvarianten je Ausdruck | [output/emonet/variations/](../output/emonet/variations), [output/social/variations/](../output/social/variations) |
| volle 560 Vorschauvarianten | [Vorschau-ZIP](previews.md); im Git liegt je eine Beispielvariante |
| nummerierte Bilder der 101 Punkte | [docs/landmarks/](landmarks) |
| sechs Referenzrekonstruktionen | [output/reconstructions/](../output/reconstructions) |
| Original/Rekonstruktion/Overlay/Differenz | [output/comparisons/](../output/comparisons) |
| weichere Konturen: Vorher/Nachher | [output/refinement/comparisons/](../output/refinement/comparisons) |
| Kurve → Falten als Kontaktbogen | [output/under_eye/transition.png](../output/under_eye/transition.png) |
| mild augmentierte und OOD-Beispiele | [output/dataset_previews/](../output/dataset_previews) |
| gemessene Detector-Vorhersagen | [output/detector/](../output/detector) |
| Human-Foto → Avatar und CPU-Protokolle | [webcam_mapper/output/verification/](../webcam_mapper/output/verification) |
| Datensatz- und Trainingsmanifeste | [docs/artifacts/](artifacts) |

Die großen SVG-Shards, virtuellen Python-Umgebungen und Trainingsweights liegen nicht im Git-Checkout. Der ausgewählte Checkpoint und das eigenständige Webcam-Paket sind [Release-Downloads](https://github.com/christophschuhmann/cartoon-face-generator/releases/tag/v1.0.0).

## Vier Namen, die leicht verwechselt werden

| Name | Bedeutung |
|---|---|
| `cartoon_face_v1` | gemeinsame Topologie mit Landmark-IDs 0–100 |
| `emonet_face_40_v1` | Emotionskatalog mit Kategorie-IDs 1–40 |
| `cartoon_social_60_v1` | zusätzlicher Ausdruckskatalog mit Kategorie-IDs 1–60 |
| `raster_landmarks_v1` | Annotation eines transformierten Rasterbilds; kein vollständiger Rig-Zustand |

Ein Emotionsname und eine Landmark-ID sind unterschiedliche Dinge. Alle Ausdrucksgruppen rendern über dieselben 101 Punkte.
