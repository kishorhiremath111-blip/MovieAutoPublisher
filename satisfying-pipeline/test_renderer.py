#!/usr/bin/env python3
"""Smoke-test every procedural scene in Chromium, including 4K canvas creation."""
import sys
from pathlib import Path

import topics

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "renderer" / "scene.html").as_uri()
CHROME_ARGS = [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    "--enable-webgl",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--force-color-profile=srgb",
]


def scene_params(scene_name, index):
    topic = topics.build_topic(index % topics.TOTAL, 28)
    params = dict(topic["params"])
    params.update({
        "scene": scene_name,
        "density": index % 4,
        "shape": topics.SHAPES[(index * 3) % len(topics.SHAPES)],
        "material": topics.MATERIALS[(index * 5) % len(topics.MATERIALS)],
        "duration": 28.0,
        "beat": 0.5,
        "level": (index % 4) + 1,
        "multiplier": (1, 2, 4, 8)[index % 4],
        "topic_id": "SCENE-SMOKE-%s" % scene_name.upper(),
    })
    return params


def main():
    from playwright.sync_api import sync_playwright

    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=CHROME_ARGS)
        context = browser.new_context(viewport={"width": 360, "height": 640}, device_scale_factor=1)
        try:
            for index, scene_name in enumerate(topics.SCENES):
                page = context.new_page()
                page_errors = []
                console_errors = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                params = scene_params(scene_name, index)
                try:
                    page.goto(HTML, wait_until="load")
                    page.wait_for_function(
                        "window.__ready === true || !!window.__error", timeout=60000
                    )
                    load_error = page.evaluate("window.__error || null")
                    if load_error:
                        raise RuntimeError(load_error)
                    page.evaluate("p => window.initScene(p)", params)
                    for t in (0.0, 0.5, 8.0, 14.0, 25.7, 27.9):
                        page.evaluate("t => window.renderAt(t)", t)
                    hud = page.locator("#hud").inner_text()
                    if "LEVEL" not in hud or "MULTIPLIER" not in hud:
                        raise RuntimeError("Level/multiplier HUD missing: " + hud)
                    if page_errors:
                        raise RuntimeError("; ".join(page_errors))
                    if console_errors:
                        raise RuntimeError("; ".join(console_errors))
                    if scene_name == "gaprun":
                        hud = page.locator("#hud").inner_text()
                        if "MULTIPLIER" not in hud:
                            raise RuntimeError("Gap-run HUD was not rendered.")
                        page.evaluate("t => window.renderAt(t)", 19.0)
                        hud = page.locator("#hud").inner_text()
                        if "8× MULTIPLIER" not in hud:
                            raise RuntimeError("Gap-run did not reach the 8x stage: " + hud)
                    print("PASS:", scene_name, flush=True)
                except Exception as exc:
                    failures.append((scene_name, str(exc)))
                    print("FAIL:", scene_name, str(exc), file=sys.stderr, flush=True)
                finally:
                    page.close()
        finally:
            context.close()

        # Exercise the actual 2160x3840 WebGL drawing buffer at least once.
        page = browser.new_page(viewport={"width": 2160, "height": 3840}, device_scale_factor=1)
        try:
            page.goto(HTML, wait_until="load")
            page.wait_for_function("window.__ready === true || !!window.__error", timeout=60000)
            params = scene_params("gaprun", 3)
            page.evaluate("p => window.initScene(p)", params)
            page.evaluate("t => window.renderAt(t)", 19.0)
            result = page.evaluate("""() => ({
                width: document.getElementById('c').width,
                height: document.getElementById('c').height,
                glError: window.__renderer.getContext().getError()
            })""")
            if result["width"] != 2160 or result["height"] != 3840 or result["glError"] != 0:
                raise RuntimeError("4K canvas check failed: %s" % result)
            print("PASS: 4K canvas 2160x3840 / WebGL", flush=True)
        except Exception as exc:
            failures.append(("4K-canvas", str(exc)))
            print("FAIL: 4K canvas", str(exc), file=sys.stderr, flush=True)
        finally:
            page.close()
            browser.close()

    if failures:
        print("%d renderer test(s) failed." % len(failures), file=sys.stderr)
        return 1
    print("All %d scene families rendered; 4K drawing buffer passed." % len(topics.SCENES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
