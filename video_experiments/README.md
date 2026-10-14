# LTX 2.5: sprechende Cartoon-Gesichter mit Emotionswechsel

[Projektübersicht](../README.md) · [Dokumentation](../docs/README.md)

Hier liegen **echte LTX-2.5-MP4s mit dem direkt generierten Ton**, die passenden SVG-Rig-Eingaben, reproduzierbare Skripte und Zeitmessungen. Das SVG-Rig bleibt das bestehende gemeinsame 101-Punkte-Modell. LTX erzeugt daraus Rastervideos; die Zwischenframes besitzen **keine exakten Ground-Truth-Landmarks**.

Die [Videogalerie](https://owner-curves-cosmetics-taught.trycloudflare.com/refinement-assets/ltx25/index.html) enthält abspielbare Beispiele, Kontaktbögen und Downloads. Die Cloudflare-Adresse ist ein temporärer Tunnel. Die lokale Galerie steht nach dem Lauf unter `video_experiments/index.html`; `python3 -m http.server 8000 --directory video_experiments` macht sie unter `http://localhost:8000` erreichbar.

## Was getestet wurde

- Fröhlich → sanft wütend: „Das ist ja wunderbar! Moment, das ist unfair!“
- Traurig → hoffnungsvoll: „Heute ist alles schwer. Aber ich gebe nicht auf.“
- Skeptisch → amüsiert: „Meinst du das ernst? Na gut, ich muss lachen.“
- Ängstlich → erleichtert: „Oh, was war das? Puh, alles wieder gut.“

Jedes Video enthält 129 Frames bei 24 fps, also **5,375 Sekunden**. Das Hauptformat ist 1024 × 512; zusätzlich wurde 768 × 384 getestet. Der Prompt verlangt einen festen Bildausschnitt, weißen Hintergrund, schwarze Linien, denselben Charakter und ausschließlich bewegte Gesichtselemente.

Die Vergleiche verwenden denselben Seed und dasselbe Skript je Paar. Getestet wurden nur Startbild, Start/Ende, Start/Mitte/Ende und fünf Stützframes. Bei drei Stützen liegen sie auf Frames 0/64/128 mit Stärken 1,0/0,85/1,0. Die zusätzlichen Stützen liegen auf Frames 32 und 96 mit Stärke 0,8. Diese Bilder sind echte interpolierte SVG-Posen.

Die letzten drei Fälle erproben mehr Randabstand. Eine zusätzliche Video-Regiepose senkt die inneren Brauen stärker, damit die Wut deutlicher wird. **Die veröffentlichten Emotionsrezepte und Detector-Trainingsdaten werden dadurch nicht geändert.** `conditioning_transform.json` beschreibt die affine SVG-Komposition: `conditioning_xy = pose_xy * scale + translate`. Der gespeicherte vollständige Pose-Zustand bleibt im ursprünglichen Rig-Koordinatensystem.

## Schnelle Checkpoints und Fast-LoRA

Die [offizielle Modellkarte](https://huggingface.co/Lightricks/LTX-2.5) veröffentlicht einen direkt destillierten 22B-Transformer, den vollständigen Dev-Transformer und eine Distillation-LoRA. Alle drei wurden tatsächlich verwendet: der destillierte Transformer für die meisten Vergleiche, Dev + `ltx-2.5-22b-distilled-lora-450-bf16.safetensors` mit Stärke 1 für zwei weitere Videos.

Der schnelle Conv-Video-VAE, Audio-VAE, Gemma4-12B-Textencoder und x2-Spatial-Upscaler sind gemeinsame Komponenten. In der getesteten [offiziellen Implementierung](https://github.com/Lightricks/LTX-2) besteht der Standard aus **8 primären und 3 sekundären Denoising-Updates**. Vier Sigma-Werte in Stufe 2 ergeben drei Übergänge. Die reduzierte 6+2- und 4+2-Auswahl ist ein **hier getestetes experimentelles Subsampling** dieser Sigma-Liste; sie ist keine behauptete offizielle Qualitätsgarantie.

`results.json` enthält alle Einzelmessungen und die Wiederholungen. Der Vergleich verwendet vier wiederholte Generierungen je Einstellung; der erste, noch kalte Lauf wird vom Warm-Median ausgeschlossen. Derselbe Prompt wird im Cache gehalten. Dieser Vergleich isoliert Durchsatz bei gleichem Prompt, keine wechselnden Produktionsaufträge.

| Einstellung | Warme Messungen | Median | Bereich |
|---|---:|---:|---:|
| 1024 × 512, 8+3 Updates | 3 | 14,22 s | 14,21–14,50 s |
| 1024 × 512, 6+2 Updates | 4 | 11,20 s | 11,14–11,29 s |
| 1024 × 512, 4+2 Updates | 4 | 10,12 s | 10,01–10,27 s |
| 768 × 384, 8+3 Updates | 4 | 9,09 s | 8,85–13,94 s |

Alle Wiederholungen einer Einstellung erzeugten byteidentische MP4s auf dieser Maschine. Die ersten destillierten Generierungen benötigten 52–64 s einschließlich Modellladen. Der reale Dev+LoRA-Vergleich benötigte 136,82 s beim ersten und 39,31 s beim warmen Aufruf. Der korrigierte LoRA-Pfad nutzt CPU-RAM für Basisgewichte; seine Geschwindigkeit ist daher kein isolierter Vergleich der Transformer-Qualität.

Für schnelle Vorschauen ist hier **6+2 bei drei Stützframes** ein brauchbarer Ausgangspunkt. 4+2 funktioniert im getesteten Skript ebenfalls und spart noch etwa eine Sekunde, zeigt aber teilweise doppelte Mundkonturen. Für weitere Qualitätsvergleiche bleibt das offizielle 8+3-Schema die Referenz. Die kleine Auflösung spart mehr Zeit, verliert feine Linien und hatte die größte Laufzeitstreuung.

## Dateien und Bedeutung

| Pfad | Inhalt |
|---|---|
| `prepare_inputs.py` | echte Rig-Posen, SVGs und PNGs einschließlich Zwischenbildern |
| `inputs/<paar>/` | Start, Viertel, Mitte, Dreiviertel, Ende; vollständiges Pose-JSON und Prompt |
| `run_experiments.py` | offizieller DistilledPipeline-Aufruf, LoRA und phasenweise CUDA-Zeitmessung |
| `output/<fall>/video.mp4` | unverändertes Originalvideo mit originalem Modellton |
| `output/<fall>/settings.json` | Seed, Sigma-Werte, Stützframes, Stärken und Modellrevision |
| `output/<fall>/timing.json` | Gesamtzeit, Phasen, Update-Anzahl, GPU und Speichermaximum |
| `output/<fall>/contact_sheet.png` | drei SVG-Referenzen und neun tatsächlich decodierte Videoframes |
| `output/<fall>/video_metrics.json` | Endpunkt-IoU, Randhelligkeit, Farbstreuung und einfache Bewegungskriterien |
| `output/<fall>/speech_check.json` | unabhängiger Whisper-Textvergleich mit dem gewünschten Dialog |
| `results.json`, `index.html` | konsolidierter Bericht und abspielbare Galerie |
| `ltx25_examples.zip` | Videos, Eingaben, Auswertung und Skripte, ohne Modellgewichte oder Umgebungen |

MP4s und große Vorschauen werden als Download-Artefakte bereitgestellt. Die Skripte, Eingaben und kleinen Berichte können im Git-Repository stehen. `models/`, `vendor/` und `.venv/` gehören ausdrücklich nicht in Git.

Das Beispiel-ZIP nach `video_experiments/` innerhalb eines geklonten Projekt-Repositorys entpacken. Die vorhandenen Videos lassen sich sofort abspielen; eine erneute Eingabegenerierung setzt den SVG-Generator aus diesem Repository voraus.

## Reproduzieren

Voraussetzungen: Linux, Python 3.12, `uv`, Git, FFmpeg, Cairo und eine geeignete NVIDIA-GPU mit funktionierendem CUDA. Die getestete Umgebung nutzt **A100-SXM4-80GB, Torch 2.9.1+cu128, Transformers 5.14.1 und ltx-pipelines/ltx-core 1.4.2**. Upstream-Quellstand und Gewichte sind festgehalten:

```text
LTX-2 Git: be6d6d0a69d11a0a399c462ed92606692e5f8697
LTX-2.5 Hub: 49b093a39c19169a8a81721dcc541e07e945232f
```

Vom Repository-Hauptordner:

```bash
bash video_experiments/setup.sh

# Voraussetzung: bereits freigeschalteter Zugriff auf das offizielle Modell.
# Token wird verdeckt abgefragt und nicht gespeichert.
HF_HUB_DISABLE_TELEMETRY=1 video_experiments/.venv/bin/python \
  -m video_experiments.download_models --with-lora

video_experiments/.venv/bin/python -m video_experiments.prepare_inputs

# Zwei Endpunkte plus ein Zwischenbild; zusätzliche Fälle: --cases 1 2 4 5 ...
CUDA_VISIBLE_DEVICES=0 video_experiments/.venv/bin/python \
  -m video_experiments.run_experiments --cases 11 --device cuda:0

# Realer Dev-Checkpoint mit Fast-LoRA
CUDA_VISIBLE_DEVICES=0 video_experiments/.venv/bin/python \
  -m video_experiments.run_experiments --model-kind dev_lora --cases 12 13

# Wiederholbarer Geschwindigkeitsvergleich
CUDA_VISIBLE_DEVICES=0 video_experiments/.venv/bin/python \
  -m video_experiments.run_experiments --cases 11 4 5 6 --repeat 4

video_experiments/.venv/bin/python -m video_experiments.analyze_videos
video_experiments/.venv/bin/python -m video_experiments.transcribe --skip-completed
python3 -m video_experiments.build_report --package
```

Ein Fall mit vorhandener `timing.json` wird übersprungen. Für erneute Versuche einen neuen Fallnamen/Seed ergänzen oder einen einzelnen Ausgabeordner bewusst archivieren. Die Zeitmessung beginnt unmittelbar vor der Pipeline und endet nach MP4-Encoding und CUDA-Synchronisierung. Sie enthält die beim ersten Aufruf fälligen Modell-Ladevorgänge, aber nicht Download, Python-Imports, CUDA-Initialisierung oder ASR-Prüfung.

Der Server verwendet wegen seines älteren Treibers zusätzlich eine bereits vorhandene, **prozesslokale** CUDA-Compatibility-Bibliothek. Das verändert den Treiber oder die Detector-Umgebung nicht. Auf einem passend aktuellen Treiber ist dieser serverspezifische `LD_LIBRARY_PATH` nicht notwendig.

## Qualität und Grenzen

Die Kontaktbögen wurden tatsächlich visuell geprüft. Endpunkt-Stützen erhalten die vorgegebenen Flächen in den meisten Beispielen eng. Ein Startbild allein lässt mehr Ausdrucksfreiheit zu, verändert aber Größe und Position. Einzelne Zwischenframes verschieben Brauen bis über den oberen Bildrand. Mehr Randabstand und zusätzliche Stützen werden deshalb separat verglichen. Bei Sprechmundformen erscheinen gelegentlich weichgraue Flächen oder doppelte dünne Konturen.

In den nachgebesserten Fällen 14–16 bleiben die untersuchten Frames innerhalb des vergrößerten Rands. Der Mittelwert der hellen Randpixel liegt dort bei 100 %. Das ist eine Verbesserung für diese Beispiele; sämtliche Bewegungen anderer Seeds sind dadurch nicht garantiert. Fünf Stützen führen im Angst→Erleichterung-Beispiel zu weniger freier Mimik als drei Stützen.

Ein milder Wut-Endpunkt erzeugt einen milden Wut-Endpunkt: gutes Bildfitting ist noch kein Beweis für eine überzeugende emotionale Darbietung. Die schärfer geneigte Regiepose ist deshalb ein eigener Vergleich. Die Ausdrucksstärke, Natürlichkeit der Stimme und audiovisuelle Synchronität wurden nicht durch unabhängige menschliche Bewertungen gemessen.

Whisper prüft die gesprochenen Wörter und kann selbst Fehler machen. Eine Wortfehlerrate von null beweist keine perfekte Aussprache, keine passende Emotion und keine genaue Phonem-Lippen-Zuordnung. Foreground-IoU und helle Ränder messen Bildähnlichkeit bzw. Hintergrundhelligkeit, keine Emotionsgenauigkeit oder garantierte Kamerastabilität.

GPU-Caching benötigt hier bis etwa **78 GB tatsächlich allokierten GPU-Speicher**. Eine naive GPU-Aufbewahrung von Dev-Basisgewichten plus verschmolzenen LoRA-Gewichten führte zunächst zu einem OOM. Der korrigierte Dev-LoRA-Pfad speichert unveränderte Basisgewichte im CPU-RAM; dadurch funktioniert er bei etwa 40–42 GB GPU-Allokation, zahlt aber zusätzliche Transfers und Fusion pro Generierung. Eine Laptop- oder CPU-Videogenerierung wurde nicht getestet.

Die Modellgewichte benötigen separat etwa **122 GB dezimal** für beide Transformer und LoRA zusammen; das schnelle Set allein rund 71 GB. Das ist zusätzlicher Modelldownload, kein Wachstum des SVG-Trainingsdatensatzes. Die Beispielvideos selbst sind nur wenige MB groß. Gewichte sind nicht Bestandteil von Git oder Beispiel-ZIP.

LTX-Code und -Gewichte stehen unter der eigenen [LTX-2.x Community License](https://github.com/Lightricks/LTX-2/blob/be6d6d0a69d11a0a399c462ed92606692e5f8697/LICENSE), nicht unter der MIT-Lizenz dieses SVG-Projekts. Der Download setzt bereits autorisierten Modellzugriff voraus; unser Skript akzeptiert keine Lizenzbedingungen im Namen eines Nutzers.
