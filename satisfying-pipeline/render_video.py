#!/usr/bin/env python3
"""Headless Chromium (software WebGL, GPU ki zaroorat nahi) se frame-by-frame
render karta hai aur ffmpeg se audio ke saath MP4 banata hai."""
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
]


def render_video(params, out_path, width=720, height=1280, fps=30, workdir=None):
    from playwright.sync_api import sync_playwright

    out_path = Path(out_path)
    workdir = Path(workdir or ROOT / "work")
    workdir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wav = workdir / "audio.wav"
    html = (ROOT / "renderer" / "scene.html").as_uri()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=CHROME_ARGS)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        page.on("pageerror", lambda e: print("[browser error]", e, file=sys.stderr))
        page.on("console", lambda m: print("[browser]", m.text) if m.type == "error" else None)
        page.goto(html)
        page.wait_for_function("window.__ready === true || !!window.__error", timeout=90000)
        err = page.evaluate("window.__error || null")
        if err:
            raise RuntimeError(err)
        try:
            res = page.evaluate("p => window.initScene(p)", params)
        except Exception as exc:
            raise RuntimeError("Scene start nahi hua (WebGL available hai?): %s" % exc)
        events = res["events"]
        print("Scene ready: %d sound events" % len(events))

        audio.make_audio(events, params, wav)

        n_frames = int(params["duration"] * fps)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
            "-i", str(wav),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
            str(out_path),
        ]
        log = open(workdir / "ffmpeg.log", "wb")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)
        try:
            for f in range(n_frames):
                page.evaluate("t => window.renderAt(t)", f / float(fps))
                proc.stdin.write(page.screenshot(type="jpeg", quality=93))
                if f % 60 == 0:
                    print("frame %d/%d" % (f, n_frames), flush=True)
            proc.stdin.close()
            code = proc.wait()
        except BrokenPipeError:
            code = proc.wait()
        finally:
            log.close()
            browser.close()
        if code != 0:
            raise RuntimeError("ffmpeg fail hua, dekho work/ffmpeg.log")
    return out_path
