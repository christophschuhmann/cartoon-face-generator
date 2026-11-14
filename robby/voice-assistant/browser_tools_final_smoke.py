"""Final deployed HTTPS smoke: literal speech must not be removed as a tool preamble."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
from browser_stunts_emotions_check import INIT, URL, HOOK

ROOT = Path(__file__).parent

async def main():
    report = {"passed": False, "request": "Sag genau: Ich warte auf die Freigabe.", "page_errors": []}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True,
            args=["--no-sandbox", "--disable-gpu", "--autoplay-policy=no-user-gesture-required"])
        page = await browser.new_page()
        page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
        await page.add_init_script(INIT)
        try:
            response = await page.goto(URL + "/desk-robot/")
            assert response.status == 200
            await page.wait_for_function('window.robo&&window.robotFace&&!document.querySelector("#call").disabled&&document.querySelector("#system-guide")', timeout=120000)
            await page.evaluate(HOOK)
            # Fail promptly if the pilot's single conversation slot is occupied.
            # Never stop a different visitor's conversation to obtain that slot.
            await page.evaluate("robo.start(false)")
            await page.fill("#message", report["request"])
            await page.locator("#form").evaluate("f=>f.requestSubmit()")
            await page.wait_for_function('actEvents.some(e=>["turn_done","error","busy"].includes(e.type))', timeout=100000)
            report.update(await page.evaluate('({events:actEvents,pcm_chunks:actAudio})'))
            assert not any(e["type"] in ("error", "busy", "barge", "avatar_action") for e in report["events"])
            spoken = " ".join(e.get("text", "") for e in report["events"] if e["type"] == "reply")
            assert "Ich warte auf die Freigabe" in spoken, spoken
            assert report["pcm_chunks"] > 0
            assert not report["page_errors"]
            report["passed"] = True
        except Exception as e:
            report["error"] = repr(e)
            try:
                report.update(await page.evaluate('({events:window.actEvents||[],pcm_chunks:window.actAudio||0,subtitle:document.querySelector("#subtitle")?.textContent})'))
            except Exception:
                pass
        finally:
            try:
                await page.evaluate("robo.stop()")
            except Exception:
                pass
            await browser.close()
    (ROOT / "logs/tools-final-smoke-20261114.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print({k: report.get(k) for k in ("passed", "pcm_chunks", "error")}, flush=True)
    if not report["passed"]:
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())
