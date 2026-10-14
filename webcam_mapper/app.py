"""Run the laptop browser webcam app, or map a local image/video to SVG poses."""
import argparse
import io
import json
from pathlib import Path
import threading
import time
import numpy as np
from PIL import Image, ImageOps
from flask import Flask, Response, jsonify, request
from .paths import DEFAULT_MODEL
from .landmarker import CpuFaceLandmarker
from .mapping import TemporalMapper, controls_to_pose
from cartoon_face.model import save_pose
from cartoon_face.renderer import render_svg, rasterize


def resize_rgb(image, maximum=640):
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((maximum, maximum), Image.Resampling.BILINEAR)
    return np.asarray(image)


class Pipeline:
    def __init__(self, model=DEFAULT_MODEL, fps=5.0, smoothing=.12):
        self.detector = CpuFaceLandmarker(model, video=True)
        self.mapper = TemporalMapper(smoothing_seconds=smoothing)
        self.fps = fps
        self.lock = threading.Lock()
        self.start = time.monotonic()

    def frame(self, rgb):
        with self.lock:
            started = time.perf_counter()
            now = time.monotonic() - self.start
            observation = self.detector.detect(rgb, round(now * 1000))
            inferred = time.perf_counter()
            controls = self.mapper.update(observation, now)
            pose = controls_to_pose(controls)
            svg = render_svg(pose, 870, 450)
            ended = time.perf_counter()
            total_ms = (ended - started) * 1000
            status = {
                "tracking": observation is not None,
                "landmark_count": len(observation.landmarks) if observation else 0,
                "blendshape_count": len(observation.blendshapes) if observation else 0,
                "inference_ms": round((inferred - started) * 1000, 2),
                "mapping_render_ms": round((ended - inferred) * 1000, 2),
                "total_ms": round(total_ms, 2),
                "suggested_fps": round(min(30, 1000 / max(total_ms * 1.5, 1)), 2),
                "calibration_remaining": self.mapper.calibration_remaining,
                "calibrated": bool(self.mapper.calibration),
                "controls": controls,
            }
            return pose, svg, status


def create_app(pipeline):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

    @app.before_request
    def same_origin():
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            return jsonify(error="Use the local app's own browser tab."), 403

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/healthz")
    def health():
        return jsonify(ok=True, cpu=True, target_fps=pipeline.fps)

    @app.get("/api/config")
    def config():
        with pipeline.lock:
            return jsonify(target_fps=pipeline.fps, svg=render_svg(controls_to_pose(pipeline.mapper.controls), 870, 450))

    @app.post("/api/frame")
    def frame():
        if request.mimetype not in ("image/jpeg", "image/png"):
            return jsonify(error="Send a JPEG or PNG frame."), 415
        try:
            with Image.open(io.BytesIO(request.get_data())) as image:
                if image.width * image.height > 4096 * 4096:
                    return jsonify(error="Frame too large; use 640px webcam capture."), 413
                rgb = resize_rgb(image)
        except (OSError, ValueError, Image.DecompressionBombError):
            return jsonify(error="Could not decode the image frame."), 400
        _, svg, status = pipeline.frame(rgb)
        return jsonify(svg=svg, **status)

    @app.post("/api/calibrate")
    def calibrate():
        with pipeline.lock:
            pipeline.mapper.begin_calibration(8)
        return jsonify(ok=True, frames=8)

    @app.post("/api/reset")
    def reset():
        with pipeline.lock:
            pipeline.mapper.reset()
            svg = render_svg(controls_to_pose(pipeline.mapper.controls), 870, 450)
        return jsonify(ok=True, svg=svg)

    @app.get("/api/pose")
    def pose():
        with pipeline.lock:
            pose = controls_to_pose(pipeline.mapper.controls)
        return Response(json.dumps(pose, indent=2) + "\n", mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=webcam_pose.json"})

    @app.get("/api/avatar.svg")
    def avatar():
        with pipeline.lock:
            svg = render_svg(controls_to_pose(pipeline.mapper.controls))
        return Response(svg, mimetype="image/svg+xml",
                        headers={"Content-Disposition": "attachment; filename=webcam_avatar.svg"})

    return app


def image_to_avatar(path, model, output):
    with Image.open(path) as image:
        rgb = resize_rgb(image)
    with CpuFaceLandmarker(model, video=False) as detector:
        started = time.perf_counter()
        observation = detector.detect(rgb)
        inference_ms = (time.perf_counter() - started) * 1000
    mapper = TemporalMapper(smoothing_seconds=0)
    pose = controls_to_pose(mapper.update(observation, 0))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    save_pose(pose, output / "avatar.json")
    svg = render_svg(pose)
    (output / "avatar.svg").write_text(svg)
    rasterize(svg).save(output / "avatar.png")
    status = {"tracking": observation is not None, "inference_ms": round(inference_ms, 2),
              "human_landmarks": len(observation.landmarks) if observation else 0,
              "cartoon_landmarks": len(pose["keypoints"]), "output": str(output)}
    (output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(json.dumps(status, indent=2))
    return observation is not None


def video_to_avatars(path, model, output, fps, smoothing):
    import cv2
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {path}")
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if source_fps <= 0 or not np.isfinite(source_fps):
        raise ValueError("Video frame rate unavailable; provide a standard constant-rate video")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    mapper = TemporalMapper(smoothing_seconds=smoothing)
    rows, frame_index, next_time = [], 0, 0.0
    try:
        with CpuFaceLandmarker(model, video=True) as detector:
            while True:
                ok, bgr = capture.read()
                if not ok:
                    break
                timestamp = frame_index / source_fps
                frame_index += 1
                if timestamp + 1e-9 < next_time:
                    continue
                next_time += 1 / fps
                rgb = resize_rgb(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
                started = time.perf_counter()
                observation = detector.detect(rgb, round(timestamp * 1000))
                pose = controls_to_pose(mapper.update(observation, timestamp))
                name = f"frame_{len(rows):06d}"
                save_pose(pose, output / f"{name}.json")
                (output / f"{name}.svg").write_text(render_svg(pose))
                rows.append({"frame": name, "timestamp_seconds": timestamp, "tracking": observation is not None,
                             "inference_mapping_render_ms": (time.perf_counter() - started) * 1000})
    finally:
        capture.release()
    (output / "video_report.json").write_text(json.dumps({"source_fps": source_fps, "target_fps": fps, "frames": rows}, indent=2) + "\n")
    print(f"Wrote {len(rows)} SVG/pose samples to {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--serve", action="store_true", help="Local browser webcam app (default)")
    mode.add_argument("--image", type=Path, help="Map one local human photo to SVG/PNG/pose")
    mode.add_argument("--video", type=Path, help="Sample a local video into avatar SVG/pose files")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=Path("webcam_mapper/output/run"))
    parser.add_argument("--fps", type=float, default=5.0, help="Target updates per second, .5..30 (default 5)")
    parser.add_argument("--smoothing", type=float, default=.12, help="Expression smoothing seconds, 0..2")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not np.isfinite(args.fps) or not .5 <= args.fps <= 30:
        parser.error("--fps must be .5..30")
    if not np.isfinite(args.smoothing) or not 0 <= args.smoothing <= 2:
        parser.error("--smoothing must be 0..2")
    if args.image:
        raise SystemExit(0 if image_to_avatar(args.image, args.model, args.output) else 2)
    if args.video:
        video_to_avatars(args.video, args.model, args.output, args.fps, args.smoothing)
        return
    pipeline = Pipeline(args.model, args.fps, args.smoothing)
    try:
        print(f"Open http://127.0.0.1:{args.port} on this laptop. Webcam frames stay local; no recordings are stored.")
        create_app(pipeline).run(host="127.0.0.1", port=args.port, debug=False, threaded=True)
    finally:
        pipeline.detector.close()


if __name__ == "__main__":
    main()
