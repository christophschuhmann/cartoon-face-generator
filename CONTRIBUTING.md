# Entwicklung und Beiträge

[Repository-Startseite](README.md) · [Architektur](docs/architecture.md) · [Dateiübersicht](docs/repository_map.md)

## Entwicklungsumgebung

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

Alternativ `uv sync --locked --extra test`. Die normalen Tests benötigen kein MediaPipe-Modell und kein PyTorch. Ohne PyTorch wird die optionale Detector-Testdatei übersprungen. Für sie die in [training/README.md](training/README.md) beschriebene Umgebung verwenden:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-training/bin/python -m pytest tests/test_detector.py -q
```

Eine echte Browserprüfung benötigt Chromium:

```bash
.venv/bin/python -m playwright install chromium
.venv/bin/python tools/test_editor.py
```

Das Script prüft den Editor mit seinem Python-Server, einschließlich Keypoint-Dragging und Downloads. Für echte MediaPipe-/Kamera-Simulationstests gelten die gesonderten Schritte in [webcam_mapper/README.md](webcam_mapper/README.md).

## Wo ändere ich was?

| Änderung | Einstieg |
|---|---|
| Keypoint lesen, verschieben, speichern | `src/cartoon_face/model.py`, [Datenformat](docs/data_format.md) |
| Kontur glätten, Strichbreite oder Kappe ändern | `geometry.py`, `components/__init__.py` |
| Emotionsrezept ändern | `emotions/catalog.json`, `emotion_library.py` |
| sozialen Ausdruck ändern | `emotions/social_catalog.json`, `social_expressions.py` |
| Unteraugenübergang ändern | `under_eye.py`; [Konventionen](docs/under_eye.md) beachten |
| Oberfläche ändern | `viewer/`, gegebenenfalls `server.py` |
| Augmentation ändern | `augmentation.py`; Bild und Labels gemeinsam transformieren |
| Detector ändern | `training/` |
| Human-Signale auf Cartoon-Steuerwerte abbilden | `webcam_mapper/mapping.py` |

## Verträge erhalten

Die **101 Landmark-IDs, Bedeutungen und Seitenkonventionen** sind feste Datenverträge. Neue Bézier-Handles oder Strich-Slots sind interne Geometrie und keine automatisch neuen Landmark-IDs. Bei einer absichtlichen inkompatiblen Topologieänderung braucht es einen neuen Topologie-Identifier, eine Migration und neue Labels/Modelle.

Vollständige Posen sind die verbindliche Renderquelle. Rezepte dürfen bei späteren Änderungen andere neue Posen erzeugen; alte vollständige JSONs müssen unter ihrem gespeicherten Geometriemodus reproduzierbar bleiben. Beim Ändern von Punkten Sichtbarkeiten mit `refresh_states` erneuern und über `validate_pose` prüfen.

Geometrieänderungen immer tatsächlich rendern: Referenzvergleiche, neue Ausdrücke und Zwischenposen visuell ansehen. IoU/Dice und Konturabstand zusammen beurteilen. Eine bessere Pixelmetrik allein rechtfertigt keine unruhige Kurve oder verlorene Identität.

Bei Augmentationen gelten identische Bild-/Labeltransformationen, anatomische Spiegelungspermutation und disjunkte Quellposen-Splits. Abwesende oder außerhalb liegende Labels nicht stillschweigend auf `[0,0]` setzen. Die unabhängigen extremen OOD-Verformungen bleiben eine getrennte Gruppe ohne verlässliches Emotionsziel.

## Daten, Releases und Dokumentation

Große Datensätze, virtuelle Umgebungen, persönliche Medien und Zugangsdaten gehören nicht in Git. Beispielbilder und kleine Nachweise sind erwünscht. Umfangreiche Vorschauen, Modellweights und eigenständige Pakete werden als Release-Assets bereitgestellt.

Änderst du geteilte Renderermodule, das Mapping oder das Standalone-Paket, das Webcam-ZIP neu bauen und prüfen:

```bash
webcam_mapper/.venv/bin/python -m webcam_mapper.bundle --include-model
```

Für den großen Datensatz sind Generator-Fingerprint und Shard-Hashes maßgeblich. Nach einer relevanten Generatoränderung einen neuen Datensatzlauf erzeugen und auditieren; ein vorhandenes Manifest nicht einfach als neu validiert ausgeben.

Die Dokumentation mit [tools/check_docs.py](tools/check_docs.py) prüfen. Für einen GitHub-Checkout prüft `--tracked-only` ausschließlich versionierte Dateien und erkennt Links auf versehentlich nur lokal vorhandene Ergebnisse:

```bash
python tools/check_docs.py --root . --tracked-only
```

Ein optionaler GitHub-Actions-Workflow liegt unter [tools/github_ci_template.yml](tools/github_ci_template.yml). Um Actions einzuschalten, das Template als `.github/workflows/ci.yml` übernehmen und mit einem Konto bzw. Token veröffentlichen, das Workflow-Änderungen erlaubt. Bis dahin sind automatische Actions nicht aktiv.

## Was wir als Ergebnis behaupten

Gemessene Landmark-Qualität, prozedurale Ziel-Labels und menschliche Erkennung sind verschiedene Nachweise. Neue Resultate müssen mit Split, Auflösung, Metrik und Grenzen angegeben werden. Automatische Browserbewertungen zählen nicht als menschliche Emotionsstudie. CPU-Zeiten auf dem Entwicklungsserver sind keine gemessene Laptop-Webcam-Performance.
