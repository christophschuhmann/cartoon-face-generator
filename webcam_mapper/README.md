# Mimikstudio – lokale Webcam auf 101-Punkt-Cartoon

## Start unter Windows

Diese Version wurde auf Windows mit Python 3.12 und CPU getestet. Alle Befehle im Repository-Hauptordner ausführen. Für einen neuen Checkout zuerst die Umgebung und das MediaPipe-Modell einrichten:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r webcam_mapper/requirements-windows.txt
.\.venv\Scripts\python.exe -m webcam_mapper.download_model
.\Start-Avatar.ps1
```

`Start-Avatar.cmd` startet den lokalen Python-Server und öffnet ein eigenes Edge-Fenster. Die Oberfläche ist unter http://127.0.0.1:8765 erreichbar. Webcam erlauben und bei entspanntem Gesicht **Neutral kalibrieren** wählen. Nach einem Software-Update das Fenster mit F5 neu laden. Die Audio-Bühne benötigt zusätzlich die unten beschriebenen lokalen Audiomodelle und die separate Umgebung; sie ist nach einer reinen Webcam-Installation noch nicht analysebereit.

```powershell
.\Start-Avatar.ps1 -Restart -NoWindow
.\.venv\Scripts\python.exe -m webcam_mapper.app --serve --emotion-mode motion
```

Die Startskripte ermitteln ihren Projektpfad selbst. Virtuelle Umgebungen, große Modellgewichte, Laufzeit-Binaries und persönliche Audio-/Webcam-Dateien sind nicht Teil des Git-Checkouts. Die kleinen Normalisierungstabellen mit ihren Lizenzhinweisen sind enthalten. Die ältere Version im GitHub-Release `v1.0.0` enthält diese neuen Audiofunktionen noch nicht; der aktuelle Quellcode liegt auf `main`.

## Mimik und Darstellung

- MediaPipe verfolgt Kopfhaltung, beide Augen und Mund unabhängig von der langsameren Emotionsanalyse. Augenbrauen werden pro Seite aus Blendshapes und nach Neutral-Kalibrierung zusätzlich aus Mesh-Abständen gesteuert.
- Empfindlichkeit für Brauen, gesenkte Mundwinkel, Sprechen, Blick und Zunge ist einstellbar. Kleine Mundbewegungen reagieren schneller; negative Mundwinkel und zusammengezogene Brauen werden gegen widersprüchliche Lächelschätzungen geschützt.
- Jede Pupille kann unabhängig wandern, rollen oder schielen. Augenöffnung und Pupille begrenzen die Glanzlichter; die Lider verdecken nach oben wandernde Pupillen kontinuierlich.
- Kopfbewegungen verwenden eine gekrümmte räumliche Projektion mit Nasentiefe und Perspektive. Das ist eine stilisierte 2,5D-Darstellung des bestehenden SVG-Rigs. Die Richtung des Nickens ist korrigiert, die Kopfbewegung zeitlich geglättet.
- Alle 101 Keypoint-IDs bleiben stabil. Der Browser interpoliert SVG-Kurven und Transformationen; Messrate und Anzeige-Zwischenbilder sind unterschiedliche Größen. Tatsächliche Hz und CPU-Zeiten stehen im Fenster.
- MediaPipe liefert kein Zungensignal. Eine zusätzliche lokale Farb-/Formheuristik prüft den Mundbereich, die Verbindung zur Unterlippe und die Form. Sie berücksichtigt auch eine nach vorne gerichtete Zunge. Licht, Lippenfarbe, Bart und Verdeckung können weiterhin Fehlalarme oder Aussetzer verursachen. Das ist kein trainierter Zungendetektor.

## Emotionen und Archetypen

Die Emotionserkennung ist abschaltbar. **Archetyp/Mimik** regelt den Einfluss auf den Gesichtsstil. Kopf, Blick, Zwinkern, Zunge und Mundöffnung bleiben direkt gesteuert; gesprochene Mundbewegungen werden nicht durch einen statischen Archetyp ersetzt.

**Direkte Mimik + Ausdrucksstile** verwendet gemessene Gesten und Ähnlichkeit zu den vorhandenen Cartoon-Rezepten. Das frühere Sieben-Klassen-CNN ist aus dem normalen Ablauf entfernt. **Empathic Small** und **Empathic Large** verwenden alle 40 LAION-Regressoren mit einem gemeinsamen SigLIP2-Bildencoder. Small hat 1152→128→32→1, Large 1152→1024→512→256→1 Neuronen pro Kategorie. Die zusätzlichen vier Small-Ausgaben gehören nicht zur 40er-Cartoon-Taxonomie.

Die 40er-Analyse läuft in einem separaten CPU-Prozess mit einem Rechenthread und maximal einem wartenden Bild. Das Fenster zeigt Berechnungszeit und Alter des analysierten Bildes. Auf diesem i5-7200U ist auch Small wegen des gemeinsamen großen Encoders keine Echtzeit-Emotionserkennung. Mit dem gewählten Q4-Encoder benötigte Small bei den sieben veröffentlichten Beispielen etwa 14–19 Sekunden pro Bild, im Browser-Test mit aktiver Vorschau rund 36 Sekunden. Die 40 Small-Regressoren allein benötigten etwa 7–10 ms, Large etwa 47–48 ms. Der schnelle Modus bleibt für die unmittelbare Mimik verfügbar. Die numerischen Werte sind relative Modellintensitäten, keine kalibrierten Wahrscheinlichkeiten und kein sicherer Nachweis einer inneren Emotion.

Die Galerie enthält die 40 originalen EmoNet-Archetypen und 60 separat gekennzeichnete soziale Cartoon-Ausdrücke aus dem [Cartoon-Face-Generator](https://github.com/christophschuhmann/cartoon-face-generator). Alle sind manuell darstellbar. Ähnlichkeit zu einem Cartoon-Rezept ist ausdrücklich keine validierte 100-Klassen-Erkennung menschlicher Emotionen. Zwinkern, Schielen, Blick nach oben und Zunge liefern direkt beobachtbare Stilhinweise. Eigene Mimikmuster lassen sich pro Archetyp anlernen; diese Merkmale bleiben nur im Arbeitsspeicher der Sitzung.

## Audio-Bühne

**Audio-Bühne · MP3 / WAV** beendet das Übertragen deiner Webcam-Mimik. Datei wählen, **Audio analysieren**, danach den Audio-Player starten. Spulen, Pause und Wiedergabe verwenden dieselbe Audio-Uhr; die Animation läuft im Browser mit bis zu 30 Bildern/s. Die lokale Voranalyse verwendet **Moondream Parakeet Redux** auf CPU mit Silero-VAD und Wortzeitstempeln, danach **LAION Humaneness Ears Medium** aus `laion/humaneness-ears-base-medium` für Gruppen von bis zu drei Wörtern. **Base** bleibt als schnellere Option verfügbar. Gruppen überschreiten keine längeren Sprechpausen; der akustische Kontext für Emotion und Sprechstil umfasst mindestens 1,4 Sekunden, soweit die Aufnahme reicht.

Alle 40 Original-Archetypen besitzen eigene Parameter für Sprechtempo, Mundöffnung, Lippenrundung, Nicken und Kopfneigung. Referenzabweichungen oberhalb z = +0,5 liefern die Ausdrucksbeiträge. Vor der Auswahl von drei Rezepten werden widersprüchliche Beiträge anhand von Ärger/Ungeduld und Sprechspannung gewichtet: Sind diese zusammen erhöht, verdrängen gleichzeitig hohe Triumph-/Elation-Werte die negative Mimik nicht mehr. Das ist eine Regel für die Darstellung; die gemessenen Emotionswerte bleiben unverändert. Medium verwendet die Speech-Referenz aus 80.265 Clips von [LAION Procedural Voice Captions](https://github.com/LAION-AI/procedural-voice-captions): `(Rohwert − Mittelwert) / Populationsstandardabweichung`. Base verwendet ausdrücklich seine ursprüngliche Median/Std-Referenz, nicht die Medium-Statistik. Die Trainingsnormalisierung zum Dekodieren der Gewichte bleibt davon getrennt. Rohwerte, z-Werte, höchster Modellwert und dargestellte Mimik stehen pro Abschnitt zur Verfügung.

Ranting, Whispering, dramatischer, verspielter und monotoner Sprechstil sowie Betonung und Spannung kommen aus denselben VoiceNet-Ausgaben und benötigen keinen zweiten Encoder. Ranting verstärkt die Artikulation, Flüstern reduziert die Bewegungen. Erst zusätzliche Ärger-/Ungeduld-Signale verstärken die aggressive Mimik: gesenkte innere Brauen, engere Augen und deutlichere negative Mundwinkel. Lautstärke oder Ranting allein erzeugen keinen Ärger. Traurigkeit und Angst behalten ihre hochgezogenen inneren Brauen; ein absichtliches Grinsen bei Malice bleibt ohne Ärgersignale erhalten. Aktivierung verstärkt Bewegung und Mimik; Valenz gibt einen begrenzten Einfluss, ohne negative Mundwinkel wieder in ein Lächeln umzuwandeln. Mundbewegungen folgen Wortfenstern und dem 20-ms-Lautstärkeverlauf. Wangen, Lider, Brauen und Kopf reagieren gemeinsam auf diese Mundimpulse; bei Ärger senkt der Sprechimpuls die Brauen, bei negativer Mimik hebt er die Wangen weniger. Blinzeln liegt bevorzugt an Wortenden. Die Bewegungsstärke ist einstellbar.

Überlappende Ausdruckskurven überblenden standardmäßig in 450 ms, einstellbar von 250 bis 900 ms. Nach Sprachabschnitten klingt der Ausdruck in 850 ms aus; kurze aufeinanderfolgende Abschnitte springen nicht auf eine neue Ausgangspose. Das ist stilisierte Artikulation, keine Phonem-/Visem-Erkennung. Sehr kurze Segmente und synthetische Stimmen können die Emotionsschätzung erschweren.

**Blickkontakt per Webcam** ist voreingestellt. Beim Abspielen startet eine sparsame Positionsverfolgung (384 Pixel, höchstens etwa vier Bilder/s), bei Pause, Ende oder Moduswechsel werden die Kameraspuren freigegeben. Der zusätzliche Haken **Kopf folgt mir · drehen & neigen** aktiviert räumliche Kopfdrehungen nach links/rechts, oben/unten und in alle diagonalen Richtungen. Er ist zunächst aus; die Auswahl wird gespeichert und lässt sich ohne erneute Audioanalyse weich umschalten. Die Augen reagieren zuerst, der Kopf folgt langsamer. Der Blick zielt auf eine virtuelle Person vor dem Bildschirm: Kopfrotation und Neigung werden räumlich herausgerechnet, sodass die Pupillen bei gedrehtem Kopf leicht entgegensteuern und Augenkontakt vermitteln. Das ist eine stilisierte Blickillusion, keine Messung des räumlichen Augenabstands. Eine kleine Totzone unterdrückt Messzittern. Die browserseitige Projektion verwendet dieselbe gekrümmte Gesichtsfläche und Nasentiefe wie der bestehende Python-Renderer; sie erhält die 101-Punkt-Struktur und die Lidbegrenzung der Pupillen. Deine Mimik ersetzt dabei nicht den Audioausdruck. Tracking-Lücken unter 850 ms unterbrechen den Blickkontakt nicht; danach kehren Augen und Kopf sanft zur Mitte zurück. Ohne Kamerafreigabe läuft die Audioanimation weiter.

Audiodateien bleiben lokal. Für die Analyse entsteht eine temporäre Kopie unter `webcam_mapper/output/audio_sessions`, die nach Abschluss oder Abbruch gelöscht wird. Maximal 100 MB und 10 Minuten pro Datei. Das Original wird nicht verändert. Die separate `.venv-audio` schützt MediaPipe vor inkompatiblen Bibliotheksversionen; ASR und Ears laufen nacheinander mit zwei CPU-Threads.

Unter Windows verwendet die Spracherkennung `parakeet.cpp 0.6.1` mit den Redux-Q8-Gewichten und separatem Silero-VAD aus dem Redux-Bundle. Die kleinere gepackte Ternärfassung lief auf diesem Rechner nur über einen langsamen skalaren Rechenpfad und verursachte Zeitüberschreitungen. Ears verwendet einen lokal geprüften TorchScript-Export; dadurch entfällt der langsame Import der Trainingsbibliotheken bei jeder Analyse. Der Analyseknopf wird erst nach einem erfolgreich abgeschlossenen lokalen Lauf freigegeben; die Dateiauswahl bleibt während der Einrichtung zugänglich.

Die optionale Webcam-Checkbox **Sprechbewegung kurz überbrücken** aktiviert nach wiederholtem Öffnen/Schließen eine kurze Mundanimation. Nach 300/400/500 ms ohne neue Bewegung endet sie. Zunge, Schmollmund und verlorenes Tracking beenden sie ebenfalls. Mundwinkel, zusammengekniffene Augen und einzelne Brauen reagieren empfindlicher; nach dem Update neutral kalibrieren.

Unter **Feinabstimmung → Zungenerkennung** stehen Babble, SigLIP, die bisherige Farb-/Formheuristik und Aus zur Auswahl. Die zusätzlichen Modelle arbeiten im Hintergrund; Ergebnisse einer inzwischen geänderten Mundpose werden verworfen. Babble ist ein Mundmodell, SigLIP vergleicht fünf Gruppen von Textbeschreibungen. Beide Verfahren bleiben experimentell.

Im kleinen lokalen Fototest erkannte SigLIP alle fünf sichtbaren Zungen und unterschied die beiden Kontrollbilder (vorgeschobene/geschlossene Lippen, Lächeln); Laufzeit 1,0–1,6 s/Bild. Babble benötigte überwiegend 55–65 ms, übersah jedoch mehrere Zungen. Daher ist SigLIP voreingestellt. Die Stichprobe belegt keine allgemeine Trefferquote; schnelle Zungengesten können wegen der Analyseverzögerung weiterhin ausfallen. Berichte: `output/verification/mouth_research/*_report.json`.

## Einrichtung der Modelle

Die folgenden Schritte erweitern die oben eingerichtete Webcam-Umgebung um die optionale 40er-Bildanalyse. Für die einmalige Konvertierung zusätzlich `requirements-empathic-setup.txt` installieren.

```powershell
.\.venv\Scripts\python.exe -m pip install -r webcam_mapper/requirements-windows.txt
.\.venv\Scripts\python.exe -m webcam_mapper.download_model
.\.venv\Scripts\python.exe -m pip install -r webcam_mapper/requirements-empathic-setup.txt
.\.venv\Scripts\python.exe -m webcam_mapper.download_empathic --variant small
.\.venv\Scripts\python.exe -m webcam_mapper.empathic --convert --variant small
```

Die einmalige Konvertierung der LAION-Gewichte benötigt PyTorch und lädt nur Gewichte (`weights_only=True`). Die Laufzeit verwendet NumPy und ONNX Runtime auf CPU. Downloads sind auf Revision und SHA-256 festgelegt. Standard ist der Q4-Export, weil seine Rangfolgen näher an den veröffentlichten Small-Beispielen lagen. Der ebenfalls getestete CPU-INT8-Encoder ist aus dem ONNX-Community-Export abgeleitet; ausschließlich der vorzeichenbehaftete ConvInteger-Gewichtstyp wird durch eine äquivalente unsigned-Darstellung ersetzt. Details stehen in den Modell-Provenienzdateien. Die optionale Modellinstallation benötigt zusätzlichen freien Speicher.

### Audio-Laufzeit auf einem neuen Rechner

Die Audio-Laufzeit ist auf Windows ausgerichtet und benötigt eine eigene `.venv-audio` mit CPU-PyTorch, NumPy, SoundFile, FFmpeg und Transformers. `setup_audio_environment.py` installiert nur zusätzliche gepinnte Wheels in eine bereits vorhandene Umgebung. `download_audio_models.py` lädt die ursprünglichen Base-/Redux-Dateien; dieses Hilfsskript allein installiert die aktuelle Q8-/Medium-Laufzeit noch nicht vollständig.

Für die vollständige Einrichtung werden diese zusätzlichen Assets benötigt:

- `webcam_mapper/models/parakeet-redux/cpp/parakeet-v0.6.1-bin-win-cpu-x64/parakeet-cli.exe` aus der Windows-CPU-Ausgabe von parakeet.cpp 0.6.1.
- `redux-q8.gguf` und `redux-bundle.gguf` im darüberliegenden `parakeet-redux`-Ordner. Quellen, Revisionen, Originaldateinamen und Prüfsummen stehen in [THIRD_PARTY.md](THIRD_PARTY.md).
- Ears Base und Medium unter `webcam_mapper/models/ears/base` beziehungsweise `medium`, einschließlich `config.json`, `preprocessor_config.json` und `model.safetensors`, plus dem veröffentlichten `model.py` und `classes.json` im `ears`-Ordner. Die gepinnte LAION-Quelle steht ebenfalls in [THIRD_PARTY.md](THIRD_PARTY.md).

Anschließend beide CPU-Graphen exportieren und mit einem eigenen kurzen Sprachclip prüfen. Erst die erfolgreiche Prüfung erzeugt die lokalen Freigabemarker für den Analyseknopf:

```powershell
.\.venv-audio\Scripts\python.exe -m webcam_mapper.prepare_audio_runtime --variant base
.\.venv-audio\Scripts\python.exe -m webcam_mapper.prepare_audio_runtime --variant medium
.\.venv\Scripts\python.exe -m webcam_mapper.verify_audio_runtime C:\Pfad\sprachprobe.wav --variant base
.\.venv\Scripts\python.exe -m webcam_mapper.verify_audio_runtime C:\Pfad\sprachprobe.wav --variant medium
```

Die Modelle und funktionierenden Marker einer anderen Installation werden nicht durch einen Git-Pull übertragen. Eine automatisierte vollständige Erstinstallation der Audio-Laufzeit ist noch nicht enthalten.

## Prüfen und Grenzen

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_webcam_mapper.py tests/test_expression_upgrade.py tests/test_extended_tracking.py tests/test_empathic.py tests/test_audio_performance.py -q
node --test tests/test_avatar_motion.mjs tests/test_speech_assist.mjs tests/test_head_follow.mjs
.\.venv\Scripts\python.exe -m webcam_mapper.visual_check
.\.venv\Scripts\python.exe -m webcam_mapper.browser_smoke --empathic
.\.venv\Scripts\python.exe -m webcam_mapper.audio_browser_smoke
```

Die Tests prüfen Mapping, Clip-Grenzen, Links/Rechts-Steuerung, Kopfprojektion, negative Ausdrücke, Übergänge, API und die Darstellung aller 100 Rezepte. Der Browser-Test nutzt eine künstliche Kamera mit einem öffentlichen NASA-Testbild. Modellbenchmarks und synthetische Gestentests belegen Funktion und Laufzeit, keine zuverlässige Erkennung aller 40 Kategorien bei realen Menschen.

Der Audio-Browser-Test prüft zusätzlich alle 40 Sprechposen, ruhenden Mund in Pausen, deterministisches Spulen, Blickrichtungen und Kamerafreigabe. Tatsächliche CPU-Inferenz und Modellparität stehen separat in `output/verification/audio_*_report.json` beziehungsweise `models/ears/medium/runtime_verification.json`.

Im lokalen Medium-Test benötigte eine 8,54 Sekunden lange WAV-Datei insgesamt 162,5 Sekunden Voranalyse: ASR 80,7 s, Laden von Ears 36,1 s, Ears-Inferenz für sechs Abschnitte 6,8 s, zusätzlich Prozessstart und SVG-Vorbereitung. Der Test lief mit dem bestehenden Webcam-Fenster und Modellen auf E:. CPU- und Datenträgerlast beeinflussen diese Zeiten deutlich. Der exportierte Medium-Graph stimmte bei drei unterschiedlichen Testlängen exakt mit den Originalausgaben überein. Das belegt die Laufzeitfunktion, nicht die Emotionsgenauigkeit der synthetischen Teststimme.

Webcam-Bilder, Gesichtsausschnitte und Embeddings werden im Live-Betrieb weder gespeichert noch hochgeladen. SVG-/Pose-Export erfolgt nur über die entsprechenden Schaltflächen. **Stoppen** gibt die Kamera frei und beendet die zusätzliche 40er-Analyse. Weitere Quellen und Lizenzen: [THIRD_PARTY.md](THIRD_PARTY.md).
