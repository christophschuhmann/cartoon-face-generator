# Manifeste und Auditnachweise

[Dokumentationsindex](../README.md) · [Datensatzanleitung](../dataset.md)

Diese kleinen Dateien dokumentieren den tatsächlich erzeugten Datensatz und Trainingscache. Die großen Archive und Caches selbst sind nicht im Repository.

| Datei | Bedeutung |
|---|---|
| [dataset_manifest.json](dataset_manifest.json) | Generator-Fingerprint, Seed, 105.000 Datensätze, 303 Shards, Splits, Größen und SHA-256 je Shard |
| [dataset_audit.json](dataset_audit.json) | alle 105.000 gespeicherten Paare validiert, alle Shard-Hashes geprüft, 909 SVG-Replays byteidentisch |
| [training_manifest.json](training_manifest.json) | 84.000 Trainingsposen, disjunkte Holdouts, fünf normale Posen je Kategorie für Validation/Test, saubere und augmentierte Ansichten |

Die Shard-Pfade im Manifest beziehen sich auf den separat erzeugten Ordner `datasets/cartoon_landmarks_v2`. Cache-Pfade beziehen sich auf `datasets/training_cache_v2`. Sie sind keine Download-URLs. Neu erzeugte Läufe schreiben ihre aktuellen Manifeste in den jeweiligen Ausgabeordner; diese hier sind Kopien des dokumentierten Prüflaufs.

Die 303 Shards sind 101 Gruppen (40 EmoNet, 60 Social, eine OOD-Gruppe) × drei Splits. In den SVG-Shards liegen 84.000 Trainings-, 10.500 Validierungs- und 10.500 Testposen. Der Trainingslauf wertet eine dokumentierte Teilmenge der Holdouts aus; Bildansichten derselben Quellpose werden dabei bewusst separat als clean/augmented berichtet.
