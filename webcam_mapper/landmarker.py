"""MediaPipe Tasks CPU inference with a single tracked face and strict timestamps."""
from pathlib import Path
import numpy as np
from .mapping import Observation
from .tongue import tongue_protrusion
from .paths import DEFAULT_MODEL


class CpuFaceLandmarker:
    def __init__(self, model_path=DEFAULT_MODEL, video=True):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError("Model missing. Run: python -m webcam_mapper.download_model")
        self.mp = mp
        self.video = video
        self.last_timestamp_ms = -1
        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(path), delegate=python.BaseOptions.Delegate.CPU),
            running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
            num_faces=1, min_face_detection_confidence=.5,
            min_face_presence_confidence=.5, min_tracking_confidence=.5,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)

    def detect(self, rgb, timestamp_ms=0):
        rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("Expected H x W x 3 RGB image")
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        if self.video:
            timestamp_ms = max(int(timestamp_ms), self.last_timestamp_ms + 1)
            self.last_timestamp_ms = timestamp_ms
            result = self.detector.detect_for_video(image, timestamp_ms)
        else:
            result = self.detector.detect(image)
        if not result.face_landmarks:
            return None
        landmarks = [(float(q.x), float(q.y), float(q.z)) for q in result.face_landmarks[0]]
        blendshapes = {q.category_name: float(q.score) for q in result.face_blendshapes[0]} if result.face_blendshapes else {}
        matrix = result.facial_transformation_matrixes[0].tolist() if result.facial_transformation_matrixes else None
        tongue = tongue_protrusion(rgb, landmarks, blendshapes.get('jawOpen', 0), blendshapes)
        return Observation(blendshapes, landmarks, rgb.shape[1], rgb.shape[0], matrix, tongue)

    def close(self):
        self.detector.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
