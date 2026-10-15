"""Run the laptop browser webcam app, or map a local image/video to SVG poses."""
import argparse
import io
import json
from pathlib import Path
import threading
import time
import numpy as np
import cv2
from PIL import Image, ImageOps
from flask import Flask, Response, jsonify, request
from .paths import DEFAULT_MODEL
from .landmarker import CpuFaceLandmarker
from .mapping import TemporalMapper, controls_to_pose
from .expressions import ExpressionMixer, library, archetype_pose
from .empathic import model_ready
from .speech import mouth_basis
from .audio_jobs import AudioJobs
from .mouth_models import MouthTracker
from .viewer import eye_position
from cartoon_face.model import save_pose
from cartoon_face.renderer import render_svg, rasterize


def resize_rgb(image, maximum=640):
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((maximum, maximum), Image.Resampling.BILINEAR)
    return np.asarray(image)


class Pipeline:
    def __init__(self, model=DEFAULT_MODEL, fps=24.0, smoothing=.06, emotion_mode='auto'):
        cv2.setNumThreads(2)
        self.detector = CpuFaceLandmarker(model, video=True)
        self.mapper = TemporalMapper(smoothing_seconds=smoothing)
        self.mouth = MouthTracker()
        self.expressions = ExpressionMixer(backend='motion' if emotion_mode=='auto' else emotion_mode)
        self.last_pose = None
        self.fps = fps
        self.lock = threading.Lock()
        self.start = time.monotonic()
        self.processed_frames = 0
        self.last_status = None
        self.animation = {'speech':False, 'release_ms':400}

    def frame(self, rgb):
        with self.lock:
            started = time.perf_counter()
            now = time.monotonic() - self.start
            observation = self.detector.detect(rgb, round(now * 1000))
            mouth_status = self.mouth.update(rgb, observation) if hasattr(self,'mouth') else {}
            inferred = time.perf_counter()
            controls = self.mapper.update(observation, now)
            mixer = getattr(self, 'expressions', None)
            rendered_controls = mixer.update(rgb, observation, controls, now) if mixer else controls
            pose = controls_to_pose(rendered_controls)
            if mixer:
                pose['expression_estimate'] = copy_status = dict(mixer.status)
                copy_status['interpretation'] = 'Model estimates of visible expression; archetypes and similarities are authored style, not verified inner emotion.'
                pose['tracked_controls'] = controls
            self.last_pose = pose
            svg = render_svg(pose, 870, 450, live=True)
            speech = mouth_basis(pose, rendered_controls) if getattr(self,'animation',{}).get('speech') and observation else None
            ended = time.perf_counter()
            total_ms = (ended - started) * 1000
            status = {
                "tracking": observation is not None,
                "landmark_count": len(observation.landmarks) if observation else 0,
                "blendshape_count": len(observation.blendshapes) if observation else 0,
                "inference_ms": round((inferred - started) * 1000, 2),
                "mapping_render_ms": round((ended - inferred) * 1000, 2),
                "total_ms": round(total_ms, 2),
                "suggested_fps": round(min(30, 1000 / max(total_ms * 1.15, 1)), 2),
                "calibration_remaining": self.mapper.calibration_remaining,
                "calibrated": bool(self.mapper.calibration),
                "controls": controls,
                "expression": dict(mixer.status) if mixer else {'enabled': False},
                "speech_basis": speech,
                "mouth_detector": mouth_status,
            }
            self.processed_frames = getattr(self, 'processed_frames', 0) + 1
            self.last_status = status
            return pose, svg, status


def create_app(pipeline):
    if not hasattr(pipeline,'mouth'):pipeline.mouth=MouthTracker()
    audio_jobs = AudioJobs()
    pipeline.mode = 'webcam'
    if not hasattr(pipeline, 'animation'): pipeline.animation = {'speech':False,'release_ms':400}
    if not hasattr(pipeline, 'expressions'): pipeline.expressions = ExpressionMixer()
    if not hasattr(pipeline, 'last_pose'): pipeline.last_pose = None
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

    @app.after_request
    def fresh_version(response):
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.before_request
    def same_origin():
        if request.path in ('/api/frame','/api/audio/viewer') and (request.content_length or 0) > 2*1024*1024:
            return jsonify(error='Webcam frame too large'), 413
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            return jsonify(error="Use the local app's own browser tab."), 403

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/healthz")
    def health():
        status = getattr(pipeline, 'last_status', None) or {}
        return jsonify(ok=True, cpu=True, target_fps=pipeline.fps,
                       version='2.3.2', capabilities=['wink', 'independent_gaze', 'curved_head_pose', 'mouth_detectors', 'speech_assist', 'independent_brows', 'lip_pout', 'empathic_small_large_40', '100_archetypes', 'audio_performance', 'audio_viewer_tracking', 'normalized_voice_styles', 'coherent_negative_audio'],
                       expression_backend=pipeline.expressions.backend, expression_variant=pipeline.expressions.empathic.variant,
                       empathic_state=pipeline.expressions.empathic.state,
                       processed_frames=getattr(pipeline, 'processed_frames', 0),
                       tracking=status.get('tracking'), total_ms=status.get('total_ms'))

    @app.get("/api/config")
    def config():
        with pipeline.lock:
            return jsonify(target_fps=pipeline.fps, expressions=pipeline.expressions.settings(),
                           audio=audio_jobs.readiness(),mode=pipeline.mode,
                           mouth=pipeline.mouth.settings(),
                           animation=pipeline.animation,
                           sensitivity=pipeline.mapper.sensitivity,
                           catalog=[{k: v for k, v in item.items() if k != 'actions'} for item in library().values()],
                           svg=render_svg(pipeline.last_pose or controls_to_pose(pipeline.mapper.controls), 870, 450, live=True))

    @app.post('/api/settings')
    def settings():
        data = request.get_json(silent=True)
        if not isinstance(data, dict): return jsonify(error='Expected settings object'), 400
        try:
            with pipeline.lock:
                gains = data.get('sensitivity', {})
                if not isinstance(gains, dict): raise ValueError('Invalid sensitivity')
                validated = {}
                for key, value in gains.items():
                    if key not in pipeline.mapper.sensitivity: raise ValueError('Unknown sensitivity')
                    value = float(value)
                    if not np.isfinite(value) or not .5 <= value <= 3: raise ValueError('Sensitivity must be .5..3')
                    validated[key] = value
                expressions = data.get('expressions', {})
                if not isinstance(expressions, dict): raise ValueError('Invalid expression settings')
                mouth = data.get('mouth', {})
                if not isinstance(mouth,dict):raise ValueError('Invalid mouth settings')
                animation = data.get('animation', {})
                if not isinstance(animation, dict) or set(animation)-{'speech','release_ms'}: raise ValueError('Invalid animation settings')
                if 'speech' in animation and not isinstance(animation['speech'],bool): raise ValueError('speech must be boolean')
                if 'release_ms' in animation and animation['release_ms'] not in (300,400,500): raise ValueError('release_ms must be 300, 400 or 500')
                pipeline.expressions.configure(expressions)
                pipeline.mouth.configure(mouth)
                pipeline.mapper.sensitivity.update(validated)
                pipeline.animation.update(animation)
                if not pipeline.expressions.enabled:
                    pipeline.last_pose = controls_to_pose(pipeline.mapper.controls)
                return jsonify(ok=True, expressions=pipeline.expressions.settings(), sensitivity=pipeline.mapper.sensitivity, animation=pipeline.animation, mouth=pipeline.mouth.settings())
        except (ValueError, TypeError, KeyError) as error:
            return jsonify(error=str(error)), 400

    @app.get('/api/archetype/<slug>')
    def archetype(slug):
        if slug not in library(): return jsonify(error='Unknown archetype'), 404
        return jsonify(svg=render_svg(archetype_pose(slug), 580, 300, live=True, id_prefix='gallery-'))

    @app.post('/api/reference')
    def reference():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict): return jsonify(error='Expected reference object'), 400
        with pipeline.lock:
            if data.get('clear') is True:
                pipeline.expressions.references.clear()
                pipeline.expressions.learning = None
            else:
                status = pipeline.last_status or {}
                if not status.get('tracking'): return jsonify(error='Starte die Webcam und zeige dein Gesicht.'), 409
                try: pipeline.expressions.learn(data.get('slug', ''))
                except ValueError as error: return jsonify(error=str(error)), 400
        return jsonify(ok=True)

    @app.post('/api/stop')
    def stop():
        with pipeline.lock:
            pipeline.mouth.close()
            pipeline.expressions.reset()
            pipeline.expressions.empathic.close()
        return jsonify(ok=True)

    @app.post("/api/frame")
    def frame():
        if pipeline.mode != 'webcam':return jsonify(error='Audio mode is active'),409
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
            pipeline.expressions.reset()
            if pipeline.expressions.backend=='empathic':pipeline.expressions.empathic.calibrate()
        return jsonify(ok=True, frames=8)

    @app.post("/api/reset")
    def reset():
        with pipeline.lock:
            pipeline.mapper.reset()
            pipeline.expressions.reset()
            pipeline.expressions.empathic.neutral=None
            pipeline.last_pose = None
            svg = render_svg(controls_to_pose(pipeline.mapper.controls), 870, 450, live=True)
        return jsonify(ok=True, svg=svg)

    @app.get("/api/pose")
    def pose():
        with pipeline.lock:
            pose = pipeline.last_pose or controls_to_pose(pipeline.mapper.controls)
        return Response(json.dumps(pose, indent=2) + "\n", mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=webcam_pose.json"})

    @app.post('/api/mode')
    def mode():
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict) or data.get('mode') not in ('webcam','audio'):return jsonify(error='Invalid mode'),400
        with pipeline.lock:
            pipeline.mode=data['mode']
            pipeline.mouth.close()
            pipeline.expressions.reset();pipeline.expressions.empathic.close()
        if pipeline.mode=='webcam':audio_jobs.cancel()
        return jsonify(ok=True,mode=pipeline.mode)

    @app.get('/api/audio/ready')
    def audio_ready():
        return jsonify(audio_jobs.readiness())

    @app.post('/api/audio/viewer')
    def audio_viewer():
        if pipeline.mode!='audio':return jsonify(error='Audio mode required'),409
        if audio_jobs.snapshot()['state']=='running':return jsonify(tracking=False,reason='analysis')
        if request.mimetype not in ('image/jpeg','image/png'):return jsonify(error='Expected image'),415
        try:
            with Image.open(io.BytesIO(request.get_data())) as image:
                if image.width*image.height>4096*4096:return jsonify(error='Image too large'),413
                rgb=resize_rgb(image,384)
        except (OSError,ValueError,Image.DecompressionBombError):return jsonify(error='Invalid image'),400
        with pipeline.lock:
            if pipeline.mode!='audio':return jsonify(error='Audio mode required'),409
            started=time.perf_counter()
            observation=pipeline.detector.detect(rgb,round((time.monotonic()-pipeline.start)*1000))
            position=eye_position(observation)
        return jsonify(tracking=position is not None,position=position,inference_ms=round((time.perf_counter()-started)*1000,1))

    @app.post('/api/audio/analyze')
    def analyze_audio():
        ready=audio_jobs.readiness()
        if not ready['ready']:return jsonify(error='Audiomodelle werden noch eingerichtet.',**ready),503
        variant=request.args.get('variant','base')
        if variant not in ('base','medium'):return jsonify(error='Unknown Ears variant'),400
        if not ready['variants'][variant]:return jsonify(error='Dieses Audiomodell wird noch eingerichtet.'),503
        data=request.get_data()
        if not data:return jsonify(error='Keine Audiodatei empfangen.'),400
        with pipeline.lock:
            pipeline.mode='audio';pipeline.mouth.close();pipeline.expressions.reset();pipeline.expressions.empathic.close()
        return jsonify(audio_jobs.start(data,variant)),202

    @app.get('/api/audio/status/<identifier>')
    def audio_status(identifier):
        try:return jsonify(audio_jobs.snapshot(identifier))
        except KeyError:return jsonify(error='Unknown audio job'),404

    @app.get('/api/audio/result/<identifier>')
    def audio_result(identifier):
        try:
            with audio_jobs.lock:
                state=audio_jobs.snapshot(identifier)
                if state['state']!='ready':return jsonify(error='Analyse noch nicht fertig.'),409
                return Response(audio_jobs.result,mimetype='application/json',headers={'Content-Encoding':'gzip'})
        except KeyError:return jsonify(error='Unknown audio job'),404

    @app.post('/api/audio/cancel')
    def audio_cancel():
        audio_jobs.cancel();return jsonify(ok=True)

    @app.get("/api/avatar.svg")
    def avatar():
        with pipeline.lock:
            svg = render_svg(pipeline.last_pose or controls_to_pose(pipeline.mapper.controls))
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
    parser.add_argument("--fps", type=float, default=24.0, help="Target updates per second, .5..30 (default 24)")
    parser.add_argument("--smoothing", type=float, default=.06, help="Expression smoothing seconds, 0..2")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument('--emotion-mode',choices=('auto','motion','fast','empathic'),default='auto')
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
    pipeline = Pipeline(args.model, args.fps, args.smoothing,args.emotion_mode)
    try:
        print(f"Open http://127.0.0.1:{args.port} on this laptop. Webcam frames stay local; no recordings are stored.")
        create_app(pipeline).run(host="127.0.0.1", port=args.port, debug=False, threaded=True)
    finally:
        pipeline.expressions.worker.close()
        pipeline.expressions.empathic.close()
        pipeline.detector.close()


if __name__ == "__main__":
    main()
