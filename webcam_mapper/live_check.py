"""Brief real-webcam CPU diagnostic. Keeps images in memory; saves no recordings."""
import argparse
import json
import statistics
import time
import cv2
from .app import Pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--seconds', type=float, default=5)
    args = parser.parse_args()
    pipeline = Pipeline()
    capture = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not capture.isOpened():
        capture.release()
        capture = cv2.VideoCapture(args.camera, cv2.CAP_MSMF)
    inference, rendering, total, tracked = [], [], [], 0
    try:
        if not capture.isOpened():
            raise RuntimeError('Webcam could not be opened. Check camera privacy settings or other camera apps.')
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        started = time.perf_counter()
        while time.perf_counter() - started < args.seconds:
            ok, frame = capture.read()
            if not ok: raise RuntimeError('Webcam opened but did not deliver a frame.')
            pose, _, status = pipeline.frame(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            assert len(pose['keypoints']) == 101
            tracked += int(status['tracking'])
            inference.append(status['inference_ms'])
            rendering.append(status['mapping_render_ms'])
            total.append(status['total_ms'])
        elapsed = time.perf_counter() - started
        print(json.dumps({'source': 'real webcam, in-memory only', 'cpu': True,
                          'frames': len(total), 'tracked_frames': tracked,
                          'capture_pipeline_hz': round(len(total) / elapsed, 2),
                          'median_inference_ms': round(statistics.median(inference), 2),
                          'median_mapping_render_ms': round(statistics.median(rendering), 2),
                          'median_total_ms': round(statistics.median(total), 2),
                          'cartoon_keypoints': 101}, indent=2))
    finally:
        capture.release()
        pipeline.expressions.worker.close()
        pipeline.expressions.empathic.close()
        pipeline.detector.close()


if __name__ == '__main__':
    main()
