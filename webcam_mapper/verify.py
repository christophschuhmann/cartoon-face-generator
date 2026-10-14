"""Reproducible CPU smoke/latency checks using one public-domain NASA photograph.

Repeated still frames test the processing pipeline; they are not a live webcam
benchmark, independent subjects, emotion accuracy, or measured user latency.
"""
import argparse
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import statistics
import time
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from .app import Pipeline, create_app, resize_rgb, video_to_avatars
from .landmarker import CpuFaceLandmarker
from .mapping import controls_from_signals, controls_to_pose, TemporalMapper
from .paths import DEFAULT_MODEL, ROOT
from cartoon_face.model import landmark_arrays, save_pose
from cartoon_face.renderer import render_svg, rasterize

ASTRONAUT_SOURCE = "https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut"


def summary(values):
    return {"samples": len(values), "median_ms": round(statistics.median(values), 3),
            "p95_ms": round(float(np.percentile(values, 95)), 3), "min_ms": round(min(values), 3),
            "max_ms": round(max(values), 3)}


def main():
    from skimage import data
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "webcam_mapper/output/verification")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args()
    if not 5 <= args.repeats <= 1000:
        parser.error("--repeats must be 5..1000")
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    photo = Image.fromarray(data.astronaut())
    photo.save(out / "astronaut.png")
    rgb = resize_rgb(photo)
    timings, observations = {}, {}
    for mode in ("image", "video"):
        load_start = time.perf_counter()
        with CpuFaceLandmarker(args.model, video=mode == "video") as detector:
            model_load_ms = (time.perf_counter() - load_start) * 1000
            values = []
            for i in range(args.repeats + 3):
                started = time.perf_counter()
                observation = detector.detect(rgb, i * 200)
                duration = (time.perf_counter() - started) * 1000
                if observation is None:
                    raise AssertionError("Public-domain astronaut face was not detected")
                if i >= 3:
                    values.append(duration)
            observations[mode] = observation
            blank_result = detector.detect(np.full_like(rgb, 255), (args.repeats + 4) * 200)
            if blank_result is not None:
                raise AssertionError("Blank-image no-face check failed")
            timings[mode] = {"model_load_ms": round(model_load_ms, 3), **summary(values)}
    observation = observations["image"]
    mapper = TemporalMapper(smoothing_seconds=0)
    controls = mapper.update(observation, 0)
    pose = controls_to_pose(controls)
    save_pose(pose, out / "astronaut_avatar.json")
    svg = render_svg(pose)
    (out / "astronaut_avatar.svg").write_text(svg)
    avatar = rasterize(svg)
    avatar.save(out / "astronaut_avatar.png")
    coords, visibility = landmark_arrays(pose)
    np.savez_compressed(out / "astronaut_landmarks.npz", human=np.asarray(observation.landmarks),
                        cartoon=coords, cartoon_visibility=visibility)
    (out / "astronaut_blendshapes.json").write_text(json.dumps(observation.blendshapes, indent=2) + "\n")
    render_timings = []
    for _ in range(args.repeats):
        started = time.perf_counter()
        render_svg(controls_to_pose(controls), 870, 450)
        render_timings.append((time.perf_counter() - started) * 1000)
    cases = [
        ("neutral", {}),
        ("smile", {"mouthSmileLeft": .95, "mouthSmileRight": .95, "eyeSquintLeft": .25, "eyeSquintRight": .25}),
        ("left wink", {"eyeBlinkLeft": 1, "mouthSmileLeft": .6, "mouthSmileRight": .6}),
        ("closed eyes", {"eyeBlinkLeft": 1, "eyeBlinkRight": 1}),
        ("jaw open", {"jawOpen": .85, "eyeWideLeft": .7, "eyeWideRight": .7, "browInnerUp": .7}),
        ("brow contraction", {"browDownLeft": .8, "browDownRight": .8, "mouthFrownLeft": .7, "mouthFrownRight": .7}),
        ("asymmetric brow", {"browOuterUpLeft": .9, "eyeSquintRight": .7}),
        ("pucker", {"mouthPucker": .9, "jawOpen": .2}),
        ("screen-right gaze", {"eyeLookOutLeft": .7, "eyeLookInRight": .7}),
    ]
    board = Image.new("RGB", (1350, 9 * 255 // 3), "#edf1ec")
    draw = ImageDraw.Draw(board)
    for index, (name, signals) in enumerate(cases):
        p = controls_to_pose(controls_from_signals(signals))
        save_pose(p, out / f"cue_{index:02d}.json")
        s = render_svg(p, 430, 222)
        (out / f"cue_{index:02d}.svg").write_text(s)
        tile = rasterize(s)
        x, y = index % 3 * 450, index // 3 * 255
        draw.text((x + 14, y + 8), name, fill="#253c30")
        board.paste(tile, (x + 10, y + 28))
    board.save(out / "authored_cue_contact_sheet.png")
    comparison = Image.new("RGB", (1350, 520), "#edf1ec")
    comparison.paste(ImageOps.contain(photo, (500, 480)), (10, 30))
    comparison.paste(ImageOps.contain(avatar, (820, 460)), (520, 45))
    ImageDraw.Draw(comparison).text((14, 10), "NASA astronaut photograph (one subject)", fill="#253c30")
    ImageDraw.Draw(comparison).text((525, 10), "CPU MediaPipe cues -> shared 101-point cartoon SVG", fill="#253c30")
    comparison.save(out / "human_to_cartoon_comparison.png")
    pipeline = Pipeline(args.model)
    try:
        client = create_app(pipeline).test_client()
        jpeg = io.BytesIO()
        photo.save(jpeg, "JPEG", quality=82)
        response = client.post("/api/frame", data=jpeg.getvalue(), content_type="image/jpeg")
        if response.status_code != 200 or not response.json["tracking"]:
            raise AssertionError("Actual CPU browser API smoke check failed")
        api_status = {k: v for k, v in response.json.items() if k != "svg"}
        if client.post("/api/calibrate").status_code != 200:
            raise AssertionError("Calibration API failed")
        for _ in range(8):
            client.post("/api/frame", data=jpeg.getvalue(), content_type="image/jpeg")
        if not pipeline.mapper.calibration:
            raise AssertionError("Actual CPU calibration did not complete")
        calibration_neutral = client.get("/api/pose").json["webcam_controls"]
        if calibration_neutral["mouth_open"] > .03 or abs(calibration_neutral["smile"] - .08) > .03:
            raise AssertionError("Calibration failed to neutralize the repeated resting cue")
    finally:
        pipeline.detector.close()
    import cv2
    video_path = out / "synthetic_repeated_photo_input.avi"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 12, (512, 512))
    if not writer.isOpened():
        raise AssertionError("Could not construct the synthetic video smoke input")
    try:
        for _ in range(36):
            writer.write(cv2.cvtColor(np.asarray(photo), cv2.COLOR_RGB2BGR))
    finally:
        writer.release()
    video_to_avatars(video_path, args.model, out / "video_smoke", 5, .12)
    video_report = json.loads((out / "video_smoke/video_report.json").read_text())
    if len(video_report["frames"]) != 15 or not all(row["tracking"] for row in video_report["frames"]):
        raise AssertionError("Synthetic 3-second video sampling check failed")
    cpu_model = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), "unknown") if Path("/proc/cpuinfo").exists() else platform.processor()
    report = {
        "test_input": {"source": ASTRONAUT_SOURCE, "name": "NASA Eileen Collins astronaut via skimage.data.astronaut",
                       "license": "Public domain; no known copyright restrictions according to scikit-image documentation",
                       "independent_human_subjects": 1, "image_size": [512, 512],
                       "synthetic_video": "36 repeated still-image frames, 12 fps, 3 seconds; this is not a live webcam"},
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "cpu_model": cpu_model, "logical_cpus": os.cpu_count(), "delegate": "MediaPipe BaseOptions.Delegate.CPU / TFLite XNNPACK",
                        "versions": {name: importlib.metadata.version(name) for name in ("mediapipe", "numpy", "CairoSVG", "Flask", "Pillow")}},
        "human_landmarks": len(observation.landmarks), "human_blendshapes": len(observation.blendshapes),
        "cartoon_landmarks": len(pose["keypoints"]), "timings": timings,
        "mapping_and_python_svg": summary(render_timings), "actual_cpu_browser_api_smoke": api_status,
        "checks": {"blank_frame_no_face": True, "actual_cpu_api": True, "neutral_calibration": True,
                   "synthetic_video_samples": len(video_report["frames"]), "all_video_samples_tracked": True},
        "limits": ["Server CPU repeated-photo timing only; no laptop/live webcam benchmark was possible here.",
                   "Inference timings exclude image decode, model load, browser capture, local transfer and display latency.",
                   "Only one public-domain human subject was used; no broad demographic or expression validation.",
                   "The nine extra contact-sheet cases are authored coefficient tests, not independently inferred emotions.",
                   "No human emotion recognition accuracy or 40-category classification was measured."],
    }
    (out / "verification_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(out / "verification_report.json"), "timings": timings,
                      "mapping_and_svg": report["mapping_and_python_svg"], "checks": report["checks"]}, indent=2))


if __name__ == "__main__":
    main()
