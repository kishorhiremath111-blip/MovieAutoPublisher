#!/usr/bin/env python3
"""Smoke-test every 3D scene in headless Chromium before any Shorts render/upload."""
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


def main():
    from playwright.sync_api import sync_playwright

    sample = topics.build_topic(0, 28)["params"]
    failures = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=CHROME_ARGS)
        context = browser.new_context(viewport={"width": 360, "height": 640}, device_scale_factor=1)
        try:
            for scene_name in topics.SCENES:
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                params = dict(sample)
                params.update({
                    "scene": scene_name,
                    "duration": 28.0,
                    "beat": 0.5,
                    "level": 1,
                    "topic_id": "SCENE-SMOKE-TEST",
                })
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
                    if page_errors:
                        raise RuntimeError("; ".join(page_errors))
                    print("PASS:", scene_name, flush=True)
                except Exception as exc:
                    failures.append((scene_name, str(exc)))
                    print("FAIL:", scene_name, str(exc), file=sys.stderr, flush=True)
                finally:
                    page.close()
        finally:
            context.close()
            browser.close()

    if failures:
        print("%d scene(s) failed smoke test." % len(failures), file=sys.stderr)
        return 1
    print("All %d scene families initialized and rendered test frames." % len(topics.SCENES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
