"""Check whole-body tricks using the live page's Perform control, even while the conversation slot is busy."""
import asyncio
import json
import os

from playwright.async_api import async_playwright

TRICKS = (
    ("Body · 360° clockwise (from above)", "bodySpin", -1),
    ("Body · 360° counterclockwise (from above)", "bodySpin", 1),
    ("Forward somersault · whole robot", "bodyFlip", 1),
    ("Backflip · whole robot", "bodyFlip", -1),
)


async def check(browser, options, url, *, deny_microphone=False):
    page = await browser.new_page(**options)
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    try:
        # This suite only uses the public animation controls. Leave the microphone available.
        setup = """
            localStorage.setItem('robby.browserBuddyVersion','1');
            localStorage.setItem('robby.autoStartDefaultVersion','1');
            localStorage.setItem('robby.autoStart','false');
            localStorage.setItem('robby.avatar-idle-enabled','false');
        """
        if deny_microphone:
            # Make the permission response arrive while the first preview is moving.
            setup += """
                localStorage.setItem('robby.autoStart','true');
                navigator.mediaDevices.getUserMedia = constraints => new Promise((resolve, reject) => {
                    const deny = () => reject(new DOMException('Microphone permission denied','NotAllowedError'));
                    if (constraints.audio) window.denyTestMicrophone = deny;
                    else deny();
                });
            """
        await page.add_init_script(setup)
        response = await page.goto(url)
        assert response and response.ok
        await page.wait_for_function("window.robotFace?.rig && window.robo && !document.querySelector('#call').disabled")
        panel = page.locator("#avatar-action-controls")
        await panel.locator("summary").click()
        await page.evaluate("""() => {
            window.trickSamples = [];
            setInterval(() => {
                if (robotFace.actions.active?.source !== 'preview') return;
                const canvas = document.querySelector('#avatar canvas');
                const r = canvas.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                const s = robotFace.rig.snapshot();
                trickSamples.push({bodySpin:s.bodySpin, bodyFlip:s.bodyFlip, visible:hit === canvas});
            }, 40);
        }""")
        result = {}
        for label, axis, direction in (TRICKS[:1] if deny_microphone else TRICKS):
            await page.select_option("#avatar-trick", label=label)
            await page.evaluate("trickSamples.length = 0")
            await page.click("#avatar-perform")
            await page.wait_for_function("trickSamples.length > 0", timeout=8000)
            if deny_microphone:
                await page.wait_for_function("typeof window.denyTestMicrophone === 'function'")
                await page.evaluate("window.denyTestMicrophone()")
            await page.wait_for_function("!robotFace.actions.active && !robotFace.actions.queue.length", timeout=20000)
            samples = await page.evaluate("trickSamples")
            degrees = max(direction * s[axis] for s in samples)
            visible = sum(s["visible"] for s in samples)
            assert degrees > 345 and visible == len(samples), (label, degrees, visible, len(samples))
            # A last rendered angle of 359.99° is already facing forward.
            await page.wait_for_function("""() => {
                const s = robotFace.rig.snapshot();
                const front = angle => Math.abs(angle - 360 * Math.round(angle / 360)) < 1;
                return front(s.bodySpin) && front(s.bodyFlip) && Math.abs(s.bodyLift) < 1;
            }""", timeout=2000)
            result[label] = {"degrees": round(degrees, 2), "visible_samples": visible}
        assert not errors, errors
        return result
    finally:
        await page.close()


async def main():
    url = os.environ.get("ROBBY_DEMO_URL", "http://127.0.0.1:8793/desk-robot/")
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get("CHROME", "/usr/bin/google-chrome"),
                                          args=["--no-sandbox"])
        try:
            for name, options in (("desktop", {"viewport": {"width": 1400, "height": 1024}}),
                                  ("Pixel 5 emulation", p.devices["Pixel 5"])):
                print(name, json.dumps(await check(browser, options, url), ensure_ascii=False), flush=True)
            print("Microphone permission denied during preview",
                  await check(browser, {"viewport":{"width":1400,"height":1024}}, url, deny_microphone=True),
                  flush=True)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
