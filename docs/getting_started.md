# Erste Schritte

[Dokumentationsindex](README.md) · [Alle CLI-Beispiele](cli.md)

## 1. Projekt herunterladen

```bash
git clone https://github.com/christophschuhmann/cartoon-face-generator.git
cd cartoon-face-generator
```

Alternativ auf GitHub **Code → Download ZIP** wählen und entpacken. Die folgenden Befehle im Ordner ausführen, der `pyproject.toml`, `poses/`, `src/` und `viewer/` enthält. Die mitgelieferten Bilder kann man bereits ohne Installation ansehen: [40 Emotionen](../output/emonet/archetypes/contact_sheet.png), [60 soziale Ausdrücke](../output/social/archetypes/contact_sheet.png).

## 2. Generator installieren

Getesteter Standard ist Python 3.12. Unter Linux/macOS:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
```

Falls `python3.12` bei dir `python3` heißt, dessen Version mit `python3 --version` prüfen. Die Projektmetadaten erlauben Python ab 3.11; die dokumentierten Prüfläufe verwenden 3.12.

CairoSVG braucht die native Cairo-Bibliothek. Unter Debian/Ubuntu bei Bedarf `sudo apt install libcairo2`, unter macOS `brew install cairo` ausführen. Für Windows beschreibt die [CairoSVG-Dokumentation](https://cairosvg.org/documentation/) die native Installation.

Unter Windows sind die entsprechenden Generator-Befehle:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\face.exe render --pose poses/smile.json --output output/my_face.svg --png output/my_face.png
.venv\Scripts\face.exe serve --port 8766
```

Linux mit Python 3.12 wurde tatsächlich geprüft. macOS-/Windows-Webcam-Sitzungen wurden hier nicht getestet.

Falls du `uv` bereits benutzt, kannst du stattdessen die versionierte Umgebung anlegen:

```bash
uv sync --locked --extra test
```

PyTorch und MediaPipe sind für den normalen Generator und Editor **nicht erforderlich**. Ihre zusätzlichen Umgebungen werden weiter unten beschrieben.

## 3. Erstes Bild erzeugen

```bash
.venv/bin/face render --pose poses/smile.json --output output/my_face.svg --png output/my_face.png
```

Das liest die vollständige gespeicherte Pose und erzeugt zwei Bilder. `render` schreibt kein neues Pose-JSON, da die Eingabepose bereits vorhanden ist.

Für einen neuen prozeduralen Ausdruck:

```bash
.venv/bin/face emotion --taxonomy emonet --name amusement --output output/my_amusement.svg
.venv/bin/face social --name knowing_wink --seed 42 --output output/my_wink.svg
```

Jetzt entstehen pro Aufruf **SVG + PNG + JSON**. Das JSON ist der vollständige Zustand zum Wiederherstellen. Derselbe Seed mit denselben Argumenten und derselben Rezeptversion ergibt dieselbe Variation. Ohne Seed erzeugt der Aufruf den festen Archetyp.

## 4. Editor öffnen

```bash
.venv/bin/face serve --port 8766
```

Das Terminal bleibt geöffnet, solange der Server läuft. Im Browser:

| Adresse | Funktion |
|---|---|
| `http://127.0.0.1:8766/` | Editor mit Referenzen und allen Ausdruckskatalogen |
| `http://127.0.0.1:8766/emotions` | 40-Emotionsgalerie und Bewertungsmöglichkeit |
| `http://127.0.0.1:8766/social` | Galerie der 60 zusätzlichen Ausdrücke |

Wähle eine Pose, blende Punkte/IDs ein und ziehe einen Anker. Die Slider steuern unter anderem Augenöffnung, Brauen, Mund, Wangenlinien und den Übergang **Kurve → Falten**. JSON/SVG/PNG lassen sich herunterladen. Eine selbst exportierte JSON-Datei kann anschließend direkt über `face render` erneut gerendert werden.

Der HTML-Editor benötigt diesen Python-Server. Ein direktes Öffnen von `viewer/index.html` stellt die Render-API nicht bereit. Zum Beenden des Servers im Terminal **Ctrl+C** drücken.

Die [bereitgestellte HTTPS-Demo](https://owner-curves-cosmetics-taught.trycloudflare.com/) ist ein temporärer Tunnel zu diesem Editor. Für längerfristige Nutzung ist der lokale Server der reproduzierbare Einstieg.

## 5. Webcam-Demo auf dem Laptop

Die Webcam-Demo ist eine separate Anwendung auf **Port 8765**. Sie erkennt menschliche Gesichtssignale mit MediaPipe auf CPU und steuert damit dasselbe Cartoon-Rig.

Du kannst das Repository verwenden oder [das eigenständige Webcam-ZIP](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.0.0/cartoon_webcam_mapper.zip) entpacken. Im jeweiligen Hauptordner eine separate Umgebung anlegen:

```bash
python3.12 -m venv .venv-webcam
.venv-webcam/bin/python -m pip install -r webcam_mapper/requirements.txt
.venv-webcam/bin/python -m webcam_mapper.download_model
.venv-webcam/bin/python -m webcam_mapper.app --serve
```

Im Laptop-Browser `http://127.0.0.1:8765` öffnen, **Start camera** anklicken und Kamera erlauben. Mit entspanntem Gesicht **Calibrate neutral** wählen und acht Updates ruhig halten. Standard ist 5 Hz; die Frequenz kann geändert werden. Das ZIP enthält bereits das geprüfte Modell; `download_model` prüft in diesem Fall seine Prüfsumme.

Das ist unabhängig vom Cartoon-Keypoint-Detector. Details zu Mapping, CPU-Prüfung, Kameraablauf und Plattformen stehen in der [Webcam-Anleitung](../webcam_mapper/README.md).

## 6. Trainierten Cartoon-Detector ausprobieren

Der Detector erkennt die 101 Punkte in einem **Cartoon-Rasterbild**. Lade den neuen [robusten Checkpoint](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.1.0/cartoon_landmarks_robust.pt) herunter und lege ihn unter `output/detector_v3/best.pt` ab. Für höchste Präzision auf normalen Generatorbildern gibt es zusätzlich die [normalpräzise Variante](https://github.com/christophschuhmann/cartoon-face-generator/releases/download/v1.1.0/cartoon_landmarks_precise.pt). [Der Ergebnisvergleich](detector_results.md) erklärt den Unterschied.

Für CPU-Inferenz eine eigene PyTorch-Umgebung im Repository-Hauptordner anlegen:

```bash
python3.12 -m venv .venv-training
.venv-training/bin/python -m pip install -e .
.venv-training/bin/python -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu

.venv-training/bin/python -m training.predict \
  --image output/my_face.png --checkpoint output/detector_v3/best.pt \
  --device cpu --output output/prediction.json
```

Die JSON-Ausgabe enthält vorhergesagte Positionen und Sichtbarkeitswahrscheinlichkeiten. Sie ist **keine vollständige renderbare Pose**, da Breiten und interne Kurvenparameter aus Landmark-Positionen allein nicht bestimmt sind. [Trainingsanleitung](../training/README.md) und [gemessene Grenzen](detector_results.md).

## Häufige Stolperstellen

| Beobachtung | Lösung |
|---|---|
| `face` nicht gefunden | den vollständigen Umgebungspfad `.venv/bin/face` verwenden; zuerst `pip install -e .` ausführen |
| `cairo`/`libcairo` fehlt | native Cairo-Bibliothek installieren, siehe Schritt 2 |
| Editor hat keine API-Verbindung | `face serve` starten und die lokale HTTP-Adresse öffnen |
| `Address already in use` | Editor etwa mit `--port 8767` starten und die passende Adresse öffnen |
| `best.pt` fehlt | den Checkpoint separat aus dem Release herunterladen |
| `datasets/cartoon_landmarks_v2` fehlt | das ist normal im frischen Checkout; nach [Datensatzanleitung](dataset.md) erzeugen |
| Webcam startet nicht | die Anwendung auf dem eigenen Laptop öffnen, Kamera erlauben und andere Kamera-Anwendungen schließen |
| Cloudflare-Link nicht erreichbar | lokalen Editor starten; der Tunnel ist temporär |

Für Änderungen am Code siehe [CONTRIBUTING.md](../CONTRIBUTING.md).
