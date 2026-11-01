#!/usr/bin/env python3
"""Render premium 9:16 3D scenes in headless Chromium and encode a high-quality MP4."""
import subprocess
import sys
from pathlib import Path

import audio

ROOT = Path(__file__).resolve().parent

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


def render_video(params, out_path, width=1080, height=1920, fps=60, workdir=None):
    from playwright.sync_api import sync_playwright

    out_path = Path(out_path)
    workdir = Path(workdir or ROOT / "work")
    workdir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wav = workdir / "audio.wav"
    html = (ROOT / "renderer" / "scene.html").as_uri()

    if width != 1080 or height != 1920:
        raise ValueError("Shorts render is locked to 1080x1920; received %dx%d" % (width, height))
    if fps != 30:
        raise ValueError("Shorts frame rate is locked to 60 fps; received %d" % fps)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=CHROME_ARGS)
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        page.on("pageerror", lambda e: print("[browser error]", e, file=sys.stderr))
        page.on("console", lambda m: print("[browser]", m.text) if m.type == "error" else None)
        try:
            page.goto(html, wait_until="load")
            page.wait_for_function("window.__ready === true || !!window.__error", timeout=90000)
            err = page.evaluate("window.__error || null")
            if err:
                raise RuntimeError(err)
            viewport = page.evaluate("({w: innerWidth, h: innerHeight, dpr: devicePixelRatio})")
            if viewport["w"] != width or viewport["h"] != height:
                raise RuntimeError("Unexpected browser viewport: %s" % viewport)
            try:
                res = page.evaluate("p => window.initScene(p)", params)
            except Exception as exc:
                raise RuntimeError("3D scene initialize failed: %s" % exc) from exc
            events = res["events"]
            print("3D scene ready: %d original sound events" % len(events))
            audio.make_audio(events, params, wav)

            frame_count = int(round(params["duration"] * fps))
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "image2pipe", "-framerate", str(fps),
                "-c:v", "mjpeg", "-i", "-",
                "-i", str(wav),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2",
                "-r", str(fps), "-vsync", "cfr",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-c:a", "aac", "-b:a", "192k", "-shortest",
                "-movflags", "+faststart", str(out_path),
            ]
            log_path = workdir / "ffmpeg.log"
            with open(log_path, "wb") as log:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)
                try:
                    for frame in range(frame_count):
                        page.evaluate("t => window.renderAt(t)", frame / float(fps))
                        proc.stdin.write(page.screenshot(type="jpeg", quality=96))
                        if frame % 60 == 0:
                            print("frame %d/%d" % (frame, frame_count), flush=True)
                    proc.stdin.close()
                    code = proc.wait()
                except Exception:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
                    proc.wait()
                    raise
            if code != 0:
                raise RuntimeError("ffmpeg failed; inspect work/ffmpeg.log")
        finally:
            browser.close()
    return out_path


if __name__ == "__main__":
    raise SystemExit("Call render_video() through run_pipeline.py")
