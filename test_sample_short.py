#!/usr/bin/env python3
"""Download an official Blender open-movie sample, make a polished vertical Short,
then publish the licensed Short publicly with an extracted frame thumbnail.

This test intentionally uses Big Buck Bunny, an openly licensed Blender Foundation
film, rather than extracting clips from random anime or streaming sites.
# Trigger note: source mirrors may provide only a 30-second sample, handled below.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from scene_tools import detect_scene_times, detect_silence_ranges, rank_highlight_windows

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "sample_short_test"
SOURCE = OUT / "big_buck_bunny_source.mp4"
SHORT = OUT / "big_buck_bunny_vertical_short.mp4"
THUMB = OUT / "big_buck_bunny_thumbnail.jpg"
RESULT = OUT / "test_upload_result.json"
CREDS = ROOT / "credentials"

# Primary modern Blender demo asset and historical official download fallback.
SOURCE_URLS = [
    "https://download.blender.org/demo/movies/BBB/bbb_sunflower_2160p_30fps_normal.mp4",
    "https://raw.githubusercontent.com/chintan9/Big-Buck-Bunny/master/BigBuckBunny480p30s.mp4",
]
DOWNLOADED_SOURCE_URL = SOURCE_URLS[0]
SOURCE_PAGE = "https://peach.blender.org/download/"
LICENSE_URL = "https://creativecommons.org/licenses/by/3.0/"


def run(cmd):
    print("+", " ".join(str(part) for part in cmd), flush=True)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        print(p.stdout[-12000:], file=sys.stderr)
        raise RuntimeError(f"Command failed (exit {p.returncode}): {cmd[0]}")
    return p.stdout.strip()


def write_result(data):
    OUT.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def download_source():
    global DOWNLOADED_SOURCE_URL
    OUT.mkdir(parents=True, exist_ok=True)
    if SOURCE.is_file() and SOURCE.stat().st_size > 1_000_000:
        print(f"Using already-downloaded source ({SOURCE.stat().st_size} bytes).")
        return
    errors = []
    for url in SOURCE_URLS:
        tmp = SOURCE.with_suffix(".mp4.part")
        try:
            print(f"Downloading official Blender source: {url}", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "MovieAutoPublisher/OpenMovieTest/1.0"})
            with urllib.request.urlopen(req, timeout=45) as response, tmp.open("wb") as out:
                content_type = str(response.headers.get("Content-Type") or "").lower()
                if "text/html" in content_type:
                    raise RuntimeError(f"Server returned HTML instead of a video ({content_type}).")
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if total and done % (20 * 1024 * 1024) < len(block):
                        print(f"Downloaded {done // (1024 * 1024)} / {total // (1024 * 1024)} MiB", flush=True)
            if tmp.stat().st_size < 1_000_000:
                raise RuntimeError(f"Download is unexpectedly small: {tmp.stat().st_size} bytes")
            # Verify before accepting the file; HTML/error pages must never be processed.
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(tmp)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            if probe.returncode or float(probe.stdout.strip() or 0) < 20:
                raise RuntimeError("Downloaded file did not validate as a video of at least 20 seconds.")
            tmp.replace(SOURCE)
            DOWNLOADED_SOURCE_URL = url
            print(f"Source downloaded and verified: {SOURCE} ({SOURCE.stat().st_size} bytes)")
            return
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
            tmp.unlink(missing_ok=True)
            print("Source mirror failed; trying fallback:", errors[-1], file=sys.stderr)
    raise RuntimeError("Could not download the official Blender sample. " + " | ".join(errors))


def best_scene_window(duration_seconds=35):
    probe = float(run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(SOURCE),
    ]))
    print("Analyzing source for active scene moments; this ranks scene/audio activity, not virality.")
    # Some mirrors provide a 30-second sample rather than the full 10-minute film.
    # Adapt the target clip length to the actual source duration instead of failing.
    duration_seconds = min(duration_seconds, max(8, int(probe) - 1))
    scene_times = detect_scene_times(SOURCE, threshold=0.30)
    silence_ranges = detect_silence_ranges(SOURCE, noise_db=-35.0)
    windows = rank_highlight_windows(
        probe, scene_times, count=1, clip_seconds=duration_seconds,
        silence_ranges=silence_ranges, min_gap_seconds=10,
    )
    if not windows:
        raise RuntimeError("No suitable scene window could be found in the open-movie sample.")
    start, end, score = windows[0]
    # Clamp the chosen window so the complete sample duration is available even if
    # the highest-scoring scene lies close to the end of the source.
    start = min(max(0.0, start), max(0.0, probe - duration_seconds))
    end = min(probe, start + duration_seconds)
    print(f"Selected active scene window: {start:.2f}s-{end:.2f}s, activity score={score:.3f}")
    return int(start), max(8, min(60, int(end - start))), float(score)


def render_short(start_seconds=None, duration_seconds=35):
    OUT.mkdir(parents=True, exist_ok=True)
    start_seconds, duration_seconds, scene_score = best_scene_window(duration_seconds)
    # Premium 9:16 layout: blurred, color-matched background; clean centered footage;
    # subtle top title card and a restrained grade. Original source audio is preserved.
    filters = (
        "[0:v]split=2[bgsrc][fgsrc];"
        "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=20[bg];"
        "[fgsrc]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        "eq=contrast=1.04:saturation=1.08:brightness=0.005,"
        "unsharp=5:5:0.30:5:5:0.0,"
        "drawbox=x=0:y=0:w=iw:h=210:color=black@0.30:t=fill,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        "text='BIG BUCK BUNNY':fontcolor=white:fontsize=56:borderw=3:"
        "bordercolor=black@0.85:x=(w-text_w)/2:y=56,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "text='OPEN-MOVIE SHORT TEST':fontcolor=white:fontsize=25:borderw=2:"
        "bordercolor=black@0.8:x=(w-text_w)/2:y=135,format=yuv420p[v]"
    )
    run([
        "ffmpeg", "-hide_banner", "-y", "-ss", str(start_seconds), "-i", str(SOURCE),
        "-t", str(duration_seconds), "-filter_complex", filters,
        "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
        "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", "-shortest", str(SHORT),
    ])
    run([
        "ffmpeg", "-hide_banner", "-y", "-ss", "4", "-i", str(SHORT),
        "-frames:v", "1", "-q:v", "2", str(THUMB),
    ])
    duration = float(run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(SHORT),
    ]))
    stream_types = set(run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", str(SHORT),
    ]).split())
    if not SHORT.is_file() or SHORT.stat().st_size < 100_000:
        raise RuntimeError("Output quality gate failed: rendered Short is missing or too small.")
    if not {"video", "audio"}.issubset(stream_types):
        raise RuntimeError(f"Output quality gate failed: expected video+audio; got {stream_types}.")
    if not 8 <= duration <= 60:
        raise RuntimeError(f"Output quality gate failed: Short duration {duration:.2f}s is outside 8-60s.")
    print(f"SHORT QA PASS: {duration:.2f}s, 1080x1920 vertical, audio+video, {SHORT.stat().st_size} bytes")
    print(f"Scene activity score (heuristic, not a virality prediction): {scene_score:.3f}")
    return duration


def restore_secret(name, target):
    value = os.getenv(name, "").strip()
    if not value:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        decoded = base64.b64decode(value, validate=True)
        json.loads(decoded.decode("utf-8"))
        target.write_bytes(decoded)
    except Exception as exc:
        raise RuntimeError(f"{name} is not valid base64-encoded JSON: {exc}") from exc
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return True


def upload_public_short():
    restore_secret("YOUTUBE_CLIENT_SECRET_B64", CREDS / "client_secret.json")
    restore_secret("YOUTUBE_TOKEN_B64", CREDS / "token.json")
    if not (CREDS / "client_secret.json").is_file() or not (CREDS / "token.json").is_file():
        raise RuntimeError("Missing YouTube OAuth secrets. Add existing YOUTUBE_CLIENT_SECRET_B64 and YOUTUBE_TOKEN_B64 in GitHub Actions secrets.")
    sys.path.insert(0, str(ROOT))
    from uploaders.youtube import upload_video

    title = "Big Buck Bunny 🐰 | A Tiny World of Wonder #Shorts"
    description = (
        "A short vertical moment from the open animated film Big Buck Bunny.\n\n"
        "Original film: Big Buck Bunny (2008), Blender Foundation.\n"
        "Source / project information: " + SOURCE_PAGE + "\n"
        "License: Creative Commons Attribution 3.0 (CC BY 3.0): " + LICENSE_URL + "\n"
        "This excerpt has been cropped to a vertical 9:16 layout with a restrained visual grade. "
        "Original source audio is retained. No affiliation or endorsement by Blender Foundation is implied."
    )
    video_id = upload_video(
        SHORT,
        title=title,
        description=description,
        tags=["Big Buck Bunny", "Blender Open Movie", "Creative Commons", "Shorts", "MovieAutoPublisher Test"],
        privacy="public",
        thumbnail=THUMB,
    )
    result = {
        "status": "published_public",
        "video_id": video_id,
        "url": "https://youtube.com/watch?v=" + video_id,
        "privacy": "public",
        "source_url": DOWNLOADED_SOURCE_URL,
        "source_page": SOURCE_PAGE,
        "license": LICENSE_URL,
        "short_path": str(SHORT.relative_to(ROOT)),
        "duration_seconds": float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(SHORT)])),
        "created_at": int(time.time()),
        "note": "Public upload of a CC BY 3.0 licensed Big Buck Bunny excerpt. Thumbnail is an original frame extracted from this rendered video.",
    }
    write_result(result)
    print("PUBLIC SHORT UPLOAD SUCCESS: " + result["url"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-upload", action="store_true", help="download and render only; do not upload")
    args = parser.parse_args()
    result = {
        "status": "started",
        "source_page": SOURCE_PAGE,
        "license": LICENSE_URL,
        "upload_requested": not args.no_upload,
    }
    try:
        if shutil_which("ffmpeg") is False or shutil_which("ffprobe") is False:
            raise RuntimeError("FFmpeg and ffprobe must be installed.")
        download_source()
        duration = render_short()
        result.update({
            "status": "rendered",
            "source_file": str(SOURCE.relative_to(ROOT)),
            "short_file": str(SHORT.relative_to(ROOT)),
            "thumbnail_file": str(THUMB.relative_to(ROOT)),
            "short_duration_seconds": duration,
        })
        write_result(result)
        if not args.no_upload:
            result.update(upload_public_short())
        else:
            result["status"] = "rendered_no_upload"
            write_result(result)
            print("NO-UPLOAD MODE: source downloaded and Short rendered, but YouTube was not called.")
    except Exception as exc:
        result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        write_result(result)
        raise


def shutil_which(name):
    import shutil
    return shutil.which(name) is not None


if __name__ == "__main__":
    main()
