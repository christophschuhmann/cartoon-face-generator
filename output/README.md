# Generierte Ergebnisse

[Repository-Startseite](../README.md) · [Vorschauen und Downloads](../docs/previews.md)

Dieser Ordner zeigt tatsächliche Ausgaben des implementierten SVG-Generators und Messberichte. Keine generativ erzeugten Bilder ersetzen die geprüften Renderings.

| Ordner / Datei | Inhalt |
|---|---|
| [emonet/archetypes/](emonet/archetypes) | alle 40 offiziellen Kategorie-Archetypen, je SVG/PNG/JSON und Kontaktbogen |
| [social/archetypes/](social/archetypes) | alle 60 selbst entworfenen sozialen Archetypen, je SVG/PNG/JSON und Kontaktbogen |
| [emonet/variations/](emonet/variations), [social/variations/](social/variations) | je eine mitgelieferte Variation pro Kategorie und weitere Kontaktbögen |
| [emonet/manifest.json](emonet/manifest.json), [social/manifest.json](social/manifest.json) | Metadaten des vollständigen Galerie-Laufs, einschließlich Varianten außerhalb des Git-Checkouts |
| [reconstructions/](reconstructions) | Original-Crop, SVG, PNG, Pose und Metriken je Referenz |
| [comparisons/](comparisons) | Referenzvergleich, Overlays und Differenzbilder |
| [evaluation.json](evaluation.json) | globale und regionale Rekonstruktionsmetriken |
| [refinement/comparisons/](refinement/comparisons) | dokumentierter Vorher-/Nachher-Schritt für weichere Konturen |
| [under_eye/](under_eye) | kontinuierliche Kurve-/Falten-Phasen als SVG/PNG |
| [dataset_previews/](dataset_previews) | Bilder für moderate Augmentationen und extreme Landmark-Verformungen |
| [detector/](detector) | echte Lernkurven, Testmetriken und Bilder mit Ground Truth/Vorhersagen |
| [detector_v3/](detector_v3) | neue robuste und normalpräzise Modelle, Auswahlprotokoll, unverändertes Testset und OOD-Vergleiche |
| [detector_search_v3/](detector_search_v3) | vier vollständige 40-Epochen-Verläufe, Konfigurationen und Audit der zusätzlichen Daten |
| [editor/browser_test.json](editor/browser_test.json) | automatisierte Editor-Prüfung; keine menschliche Emotionsbewertung |

Die **vollen 560 Vorschauvarianten** gibt es im [Vorschau-ZIP](../docs/previews.md). Die **105.000 Trainingsposen** werden separat in `datasets/` erzeugt und sind hier nicht enthalten. Neue lokale Aufrufe können weitere Ordner wie `interpolations/`, `synthetic_samples/` und `emotions/` anlegen; diese vollständigen Prüfläufe gehören nicht automatisch zum Git-Download.

Ein Archetyp-Dateistamm enthält eine Kategorie-ID und einen Slug. Alle zugehörigen JSONs enthalten die **101 stabilen Landmark-IDs**. Kategorie-IDs und Landmark-IDs dürfen nicht verwechselt werden.
