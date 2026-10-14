# Cartoon Face Rig

Preserve the Phase-1 shared SVG rig, reference fitting, evaluation and debugger.
The user also authorized full landmark documentation and procedural authoring,
variation and mixing of all 40 EmoNet-Face categories. Keep this above the existing renderer.
The user additionally authorized a separate social-expression catalog, a large
synthetic SVG/pose dataset, extreme OOD landmark jitter and label-aware raster
augmentation utilities. The latest user request explicitly also authorizes a
trained 101-keypoint detector with mild augmentations, five held-out poses per
expression (clean and augmented), and a separate CPU MediaPipe webcam mapper.
The user explicitly authorizes a separate agent for the webcam mapping pipeline.
Do not implement the later generative motion model. Keep social labels separate from the
published forty-category taxonomy. Never store user-provided access tokens in
source, artifacts or logs. Conditional private Hub upload is only needed if the
actual dataset exceeds the user's size threshold.
Keep published taxonomy labels distinct from authored cartoon cues and human
recognition evidence. Never claim 40-class recognition accuracy without measured reviews.
Preserve original files in images/. Use the Python renderer for both CLI and browser.
Keep stable landmark IDs; never put traced reference paths or raster textures in poses.
Changing geometry requires rendering and visually checking comparisons and novel expressions.
Run `.venv/bin/python -m pytest` after changes to pose or geometry contracts.
Do not report SSIM alone as reconstruction quality. Keep the real masks, Dice/IoU,
contour distances, regional metrics and limitations in output/evaluation.json.
