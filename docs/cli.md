# CLI-Kochbuch

[Dokumentationsindex](README.md) · [Installation](getting_started.md)

Alle Beispiele gelten ab Repository-Hauptordner nach Installation. Unter Windows `.venv/bin/face` durch `.venv\Scripts\face.exe` ersetzen. Mit `.venv/bin/face --help` siehst du alle Befehle; `face BEFEHL --help` zeigt dessen Optionen.

## Eine gespeicherte Pose rendern

```bash
.venv/bin/face render --pose poses/smile.json --output output/example.svg --png output/example.png
.venv/bin/face render --pose poses/tongue.json --output output/large.svg --width 1536 --height 864
```

Die Eingabepose bleibt die Quelle. `render` schreibt die SVG-Datei und nur bei `--png` auch ein PNG. Andere Seitenverhältnisse strecken das Bild entsprechend `preserveAspectRatio="none"`; proportional skalieren oder für Trainingsraster Letterboxing verwenden.

## Namen finden und Ausdrücke erzeugen

```bash
.venv/bin/face list_emotions
.venv/bin/face list_social

.venv/bin/face emotion --taxonomy emonet --name anger --output output/anger.svg
.venv/bin/face emotion --taxonomy emonet --name fear --seed 42 --variation 0.65 --intensity 0.8 --output output/fear.svg
.venv/bin/face social --name knowing_wink --seed 42 --variation 0.85 --output output/wink.svg
.venv/bin/face social --name mock_monster --output output/monster.svg
```

`emotion`, `social` und `mix` erzeugen immer drei Dateien: `.svg`, `.png`, `.json`. Ohne Seed liefern `emotion --taxonomy emonet` und `social` den jeweiligen Archetyp. Mit Seed entsteht eine reproduzierbare Variation; `--variation` steuert deren Stärke. `--intensity` bei `emotion` bewegt den Ausdruck von neutral zu voller Ausprägung.

**Wichtig:** Bei `emotion` ist die Standardtaxonomie aus Kompatibilitätsgründen `legacy`. Für die offiziellen 40 Kategorien immer `--taxonomy emonet` angeben. Legacy umfasst 14 frühere Presets wie `happy`, `sad` und `wink`.

## Gesamte Vorschaugalerien neu erzeugen

```bash
.venv/bin/face generate_emotions --variations 8 --seed 42 --output output/emonet
.venv/bin/face generate_social --variations 4 --seed 42 --output output/social
```

Das ergibt 40 + 60 Archetypen, 320 + 240 Variationen, Kontaktbögen und Manifeste. Die Manifestzählung beschreibt den vollständigen generierten Lauf. Im veröffentlichten Git-Checkout liegt je Kategorie eine Beispielvariation; [das Vorschau-ZIP](previews.md) enthält alle 560.

## Mischen und animieren

```bash
.venv/bin/face mix --a emonet:amusement --b emonet:teasing --weight 0.5 --output output/emotion_mix.svg
.venv/bin/face mix --a social:knowing_wink --b social:mock_scolding --weight 0.35 --seed 42 --output output/social_mix.svg
.venv/bin/face mix --a emonet:amusement --b social:knowing_wink --weight 0.5 --output output/cross_mix.svg

.venv/bin/face interpolate \
  --from poses/smile.json --to poses/tongue.json \
  --frames 60 --output output/interpolations/my_sequence
```

Bei `mix` gilt 0 = erstes Ziel, 1 = zweites Ziel. Der Präfix macht den Katalog eindeutig; unpräfigierte Namen werden als EmoNet-Namen behandelt. `interpolate` akzeptiert beliebige vollständige kompatible Pose-JSONs und schreibt nummerierte JSON/SVG/PNG-Frames, GIF und Kontaktbogen. Es sind mindestens 30 Frames erforderlich. Für sinnvolle Mischungen bleibt eine visuelle Prüfung notwendig, besonders bei gegensätzlichen Blickrichtungen oder optionalen Details.

## Kleine Samples oder vollständiger Trainingsdatensatz

```bash
# Kleine Phase-1-Sammlung aus den ursprünglichen Ausdruckspresets.
.venv/bin/face generate_dataset --count 100 --seed 42 --output output/my_samples

# Kleine Vorschau des großen 100-Kategorien-Formats: 1.020 Paare.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/face build_dataset \
  --per-expression 10 --ood-count 20 --seed 42 --workers 2 \
  --output datasets/my_pilot

# Vollständiger Lauf: 100.000 normale + 5.000 OOD-Paare.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/face build_dataset \
  --per-expression 1000 --ood-count 5000 --seed 42 --workers 16 \
  --output datasets/cartoon_landmarks_v2

# Alle gespeicherten Paare und Shard-Hashes prüfen.
.venv/bin/python tools/audit_dataset.py --dataset datasets/cartoon_landmarks_v2 --workers 16
```

`generate_dataset` und `build_dataset` sind verschiedene Workflows. `build_dataset` speichert SVG/JSON-Paare in komprimierten Shards und prüft vorhandene passende Shards bei Fortsetzung. Für einen anderen Seed oder eine andere Konfiguration einen eigenen Ausgabeordner verwenden. Der Vollumfang benötigt etwa 7 GB für die Archive. Details: [Datensatzanleitung](dataset.md).

## Raster mit korrekten Labels exportieren

```bash
.venv/bin/face export_rasters --dataset datasets/cartoon_landmarks_v2 \
  --split train --limit 100 --seed 42 --width 512 --height 320 \
  --format png --output output/augmented

.venv/bin/face export_rasters --dataset datasets/cartoon_landmarks_v2 \
  --split validation --limit 100 --width 512 --height 320 \
  --no-augment --format jpg --output output/clean_validation
```

Standardmäßig entstehen moderate Augmentationen und die dazu passenden transformierten Landmark-Labels. Exportiert werden Bilder, JSONL-Annotationen und COCO-kompatible Labels. Für Training/Validation die dokumentierte **Quellposen-Aufteilung** verwenden; unterschiedliche Ansichten derselben Pose sind keine unabhängigen Holdouts.

## Referenzen rekonstruieren und vergleichen

```bash
.venv/bin/face inspect_images
.venv/bin/face preprocess
.venv/bin/face fit_references --max-nfev 170 --workers 3
.venv/bin/face evaluate
```

Analyse und Vorverarbeitung verwenden `images/`. Die sechs vorhandenen Referenzen werden semantisch initialisiert und anschließend hierarchisch automatisch optimiert. Ein unbekanntes neues Bild benötigt eine passende Initialisierung; `fit_references` ist kein universeller Landmark-Detector. Fitting kann gespeicherte Referenzposen und Ergebnisse erneuern; zuvor eigene bearbeitete Dateien sichern. [Originalanalyse](reference_analysis.md), [Metriken und Grenzen](phase1_report.md).

## Qualitätsprüfungen und menschliche Bewertungen

```bash
.venv/bin/face validate --frames 32 --count 100 --seed 42
.venv/bin/face validate_emotions --variations 8 --frames 32 --seed 42
.venv/bin/face evaluate_reviews --input path/to/emotion_reviews.json --output output/review_results.json
```

Die beiden `validate`-Befehle erzeugen bzw. erneuern Prüfergebnisse. Sie prüfen Geometrie, Zwischenposen und Variation; eine menschliche Erkennungsrate entsteht erst aus echten Galerie-Bewertungen. Browser-Smoke-Testdaten sind keine solchen Bewertungen.

## Editor, Training, Webcam

```bash
.venv/bin/face serve --port 8766
```

Der Editor läuft auf Port 8766; die eigenständige Webcam-Demo standardmäßig auf 8765. Training und Webcam haben zusätzliche Abhängigkeiten und eigene Befehle: [training/README.md](../training/README.md), [webcam_mapper/README.md](../webcam_mapper/README.md). Für Tests siehe [CONTRIBUTING.md](../CONTRIBUTING.md).
