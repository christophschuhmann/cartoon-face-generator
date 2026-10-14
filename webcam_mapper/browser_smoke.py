"""Headless browser integration with a prerecorded fake camera, not live webcam."""
import argparse
import json
from pathlib import Path
import subprocess
import socket
import sys
import time
import urllib.request
from .paths import ROOT


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="Python executable with MediaPipe installed")
    parser.add_argument("--output", type=Path, default=ROOT / "webcam_mapper/output/verification")
    parser.add_argument("--port", type=int, default=0, help="Local smoke-test port; 0 picks an available port")
    args = parser.parse_args()
    if args.port == 0:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            args.port = reservation.getsockname()[1]
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    photo = out / "astronaut.png"
    if not photo.exists():
        raise FileNotFoundError("Run python -m webcam_mapper.verify first")
    fake_camera = out / "synthetic_fake_camera.y4m"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(photo),
                    "-t", "4", "-r", "10", "-pix_fmt", "yuv420p", str(fake_camera)], check=True)
    url = f"http://127.0.0.1:{args.port}"
    errors, frame_statuses = [], []
    with (out / "browser_app.log").open("w") as log:
        process = subprocess.Popen([args.python, "-m", "webcam_mapper.app", "--serve", "--port", str(args.port)],
                                   cwd=ROOT, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("App process stopped; inspect browser_app.log")
                try:
                    urllib.request.urlopen(url + "/healthz", timeout=.5).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("App did not start within 10 seconds")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=[
                    "--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                    "--use-file-for-fake-video-capture=" + str(fake_camera),
                ])
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                context.grant_permissions(["camera"], origin=url)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda response: frame_statuses.append(response.status) if response.url.endswith("/api/frame") else None)
                page.goto(url)
                page.wait_for_selector("#avatar svg")
                assert page.get_by_role("button", name="Start camera").is_enabled()
                page.get_by_role("button", name="Start camera").click()
                page.wait_for_function("document.getElementById('status').textContent.includes('Face tracked')", timeout=15000)
                assert page.locator("#hint").is_hidden()
                active_status = page.locator("#status").inner_text()
                page.screenshot(path=str(out / "browser_active.png"), full_page=True)
                page.get_by_role("button", name="Calibrate neutral", exact=True).click()
                page.wait_for_function("document.getElementById('status').textContent.includes('calibrated')", timeout=15000)
                calibrated_status = page.locator("#status").inner_text()
                pose = page.request.get(url + "/api/pose").json()
                assert len(pose["keypoints"]) == 101
                assert pose["webcam_controls"]["mouth_open"] < .03
                page.select_option("#fps", "10")
                page.get_by_role("button", name="Stop", exact=True).click()
                assert page.get_by_role("button", name="Start camera").is_enabled()
                assert page.locator("#hint").is_visible()
                assert page.evaluate("document.getElementById('camera').srcObject === null")
                page.get_by_role("button", name="Reset calibration", exact=True).click()
                page.wait_for_function("document.getElementById('status').textContent.includes('Calibration cleared')")
                browser.close()
            if errors or not frame_statuses or any(status != 200 for status in frame_statuses):
                raise AssertionError({"javascript_errors": errors, "frame_statuses": frame_statuses})
            report = {"input": "Headless Chromium fake camera using repeated public-domain astronaut photograph; not a live webcam",
                      "start_track_stop": True, "calibration_completed": True, "save_pose_has_101_landmarks": True,
                      "camera_tracks_released": True, "reset_calibration": True, "javascript_errors": errors,
                      "successful_frame_posts": len(frame_statuses), "active_status": active_status,
                      "calibrated_status": calibrated_status, "screenshot": str(out / "browser_active.png")}
            (out / "browser_report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
