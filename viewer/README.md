# Browser-Editor und Galerien

[Repository-Startseite](../README.md) · [Installationsanleitung](../docs/getting_started.md)

```bash
.venv/bin/face serve --port 8766
```

Im Repository-Hauptordner ausführen und `http://127.0.0.1:8766` öffnen. Die Oberfläche braucht die Python-API; `index.html` direkt aus dem Dateisystem zu öffnen genügt nicht.

| Datei | Aufgabe |
|---|---|
| [index.html](index.html), [app.js](app.js) | Haupteditor: Posen, Anker, Slider, Überlagerung und Export |
| [emotions.html](emotions.html), [gallery.js](gallery.js) | 40-Emotionsgalerie und exportierbare Bewertungen |
| [social.html](social.html), [social.js](social.js) | 60 zusätzliche soziale Ausdrücke |
| [style.css](style.css) | gemeinsame Gestaltung |

Die lokale API steht in [server.py](../src/cartoon_face/server.py). Sie verwendet dieselbe Python-Geometrie wie die CLI. Die Oberfläche speichert keine unabhängigen SVG-Pfade. Die Webcam hat eine eigene Browserseite unter [webcam_mapper/static/index.html](../webcam_mapper/static/index.html) und läuft standardmäßig auf Port 8765.
