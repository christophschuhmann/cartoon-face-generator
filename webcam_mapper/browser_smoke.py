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
    parser.add_argument('--empathic',action='store_true',help='Also run the real Small CPU worker')
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
    empathic_check = None
    with (out / "browser_app.log").open("w") as log:
        process = subprocess.Popen([args.python, "-m", "webcam_mapper.app", "--serve", "--port", str(args.port), '--emotion-mode', 'motion'],
                                   cwd=ROOT, stdout=log, stderr=log)
        try:
            for _ in range(450):
                if process.poll() is not None:
                    raise RuntimeError("App process stopped; inspect browser_app.log")
                try:
                    urllib.request.urlopen(url + "/healthz", timeout=.5).close()
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("App did not start within 45 seconds")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="msedge" if sys.platform == 'win32' else None, headless=True, args=[
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
                config = page.request.get(url + '/api/config').json()
                assert len(config['catalog']) == 100 and config['expressions']['cnn_available']
                assert page.locator('#archetype option').count() == 101
                # Check a real renderer transition between inference updates.
                from .mapping import controls_from_signals, controls_to_pose
                from cartoon_face.renderer import render_svg
                transition = page.evaluate("""async ({neutral, open}) => {
                    const {AvatarMotion} = await import('/static/avatar-motion.mjs');
                    const holder = document.createElement('div');
                    const animation = new AvatarMotion(holder);
                    animation.smoothing = 100;
                    animation.setSvg(neutral, true);
                    const path = () => holder.querySelector('#mouth_lower').getAttribute('d');
                    const head = () => holder.querySelector('#avatar-head').getAttribute('transform');
                    const before = path();
                    const headBefore = head();
                    animation.setSvg(open);
                    const immediate = path();
                    const deadline = performance.now() + 500;
                    while (path() === before && performance.now() < deadline)
                        await new Promise(resolve => requestAnimationFrame(resolve));
                    const between = path();
                    const headBetween = head();
                    await new Promise(resolve => setTimeout(resolve, 1400));
                    const final = path();
                    return {noJump: before === immediate, moved: between !== before, converged: final !== between,
                            headMoved: headBefore !== headBetween, headConverged: headBetween !== head(),
                            noNonfinite: !holder.innerHTML.includes('NaN') && !holder.innerHTML.includes('Infinity')};
                }""", {"neutral": render_svg(controls_to_pose(controls_from_signals({}))),
                         "open": render_svg(controls_to_pose(controls_from_signals({"jawOpen": 1,"headRoll":.35,"headYaw":.5,"tongueOut":1})))})
                assert all(transition.values()), transition
                assert page.get_by_role("button", name="Webcam starten").is_enabled()
                page.get_by_role("button", name="Webcam starten").click()
                page.wait_for_function("document.getElementById('status').textContent.includes('Gesicht erkannt')", timeout=15000)
                assert page.locator("#hint").is_hidden()
                page.wait_for_function("document.getElementById('engine-status').textContent.includes('Direkte Mimik')", timeout=15000)
                page.get_by_role('button', name='100 Ausdrücke entdecken').click()
                page.select_option('#preview-expression', 'cross_eyed_goof')
                page.wait_for_selector('#gallery-avatar svg')
                page.screenshot(path=str(out / 'browser_gallery.png'), full_page=True)
                page.get_by_role('button', name='Diesen Ausdruck einmischen').click()
                page.wait_for_function("document.getElementById('expression-meta').textContent.includes('Manuell')", timeout=10000)
                page.locator('#emotion-enabled').uncheck()
                page.wait_for_function("document.getElementById('expression-label').textContent.includes('Emotionen aus')")
                page.select_option('#archetype', '')
                page.locator('#emotion-enabled').check()
                page.wait_for_function("document.getElementById('engine-status').textContent.includes('Direkte Mimik')", timeout=15000)
                active_status = page.locator("#status").inner_text()
                page.screenshot(path=str(out / "browser_active.png"), full_page=True)
                page.get_by_role("button", name="Neutral kalibrieren", exact=True).click()
                page.wait_for_function("document.getElementById('status').textContent.includes('kalibriert')", timeout=15000)
                calibrated_status = page.locator("#status").inner_text()
                page.wait_for_function("Number(document.getElementById('status').textContent.match(/([\\d.]+) Hz/)?.[1]) > 0")
                pose = page.request.get(url + "/api/pose").json()
                assert len(pose["keypoints"]) == 101
                assert pose["webcam_controls"]["mouth_open"] < .03
                if args.empathic:
                    page.select_option('#expression-engine','empathic')
                    page.select_option('#empathic-variant','small')
                    before=len(frame_statuses)
                    page.wait_for_function("document.getElementById('engine-status').textContent.includes('40 Kategorien aktiv')",timeout=150000)
                    pose40=page.request.get(url+'/api/pose').json()
                    deep=pose40['expression_estimate']['empathic']
                    assert len(deep['scores'])==40 and len(frame_statuses)-before>3
                    page.locator('#scores40').evaluate('(node)=>node.open=true')
                    page.wait_for_function("document.getElementById('score-value-anger').value !== '–'")
                    page.screenshot(path=str(out/'browser_empathic.png'),full_page=True)
                    empathic_check={'variant':'small','categories':len(deep['scores']),
                                    'inference_ms':deep['inference_ms'],'age_seconds':deep['age_seconds'],
                                    'frames_while_waiting':len(frame_statuses)-before}
                    page.select_option('#expression-engine','motion')
                    page.wait_for_function("document.getElementById('engine-status').textContent.includes('Direkte Mimik')")
                page.select_option("#fps", "10")
                page.get_by_role("button", name="Stoppen", exact=True).click()
                assert page.get_by_role("button", name="Webcam starten").is_enabled()
                assert page.locator("#hint").is_visible()
                assert page.evaluate("document.getElementById('camera').srcObject === null")
                page.get_by_role("button", name="Kalibrierung zurücksetzen", exact=True).click()
                page.wait_for_function("document.getElementById('status').textContent.includes('Kalibrierung zurückgesetzt')")
                page.get_by_role("button", name="Nur Avatar", exact=True).click()
                assert page.locator("#preview-card").is_hidden()
                page.get_by_role("button", name="Webcam anzeigen", exact=True).click()
                assert page.locator("#preview-card").is_visible()
                browser.close()
            if errors or not frame_statuses or any(status != 200 for status in frame_statuses):
                raise AssertionError({"javascript_errors": errors, "frame_statuses": frame_statuses})
            report = {"input": "Headless Chromium fake camera using repeated public-domain astronaut photograph; not a live webcam",
                      "start_track_stop": True, "calibration_completed": True, "save_pose_has_101_landmarks": True,
                      "camera_tracks_released": True, "reset_calibration": True, "svg_interpolation": transition, "javascript_errors": errors,
                      "catalog_100": True, "direct_mimicry": True, "gallery_and_manual_blend": True, "emotion_toggle": True,
                      "empathic_worker": empathic_check,
                      "successful_frame_posts": len(frame_statuses), "active_status": active_status,
                      "calibrated_status": calibrated_status, "screenshot": str(out / "browser_active.png")}
            (out / "browser_report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
        finally:
            try:
                urllib.request.urlopen(urllib.request.Request(url+'/api/stop',method='POST'),timeout=10).close()
            except OSError: pass
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
