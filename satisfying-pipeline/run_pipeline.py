#!/usr/bin/env python3
"""Render, validate and publish one unique premium 3D YouTube Short."""
import datetime
import json
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

import topics

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "state.json"
HISTORY = ROOT / "state" / "used_topics.jsonl"
CONFIG = ROOT / "config.json"
IST = ZoneInfo("Asia/Kolkata")


def env_true(name):
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(STATE)


def used_topic_ids():
    used = set()
    if not HISTORY.exists():
        return used
    with HISTORY.open("r", encoding="utf-8") as history:
        for line in history:
            try:
                record = json.loads(line)
                if record.get("topic_id"):
                    used.add(record["topic_id"])
            except json.JSONDecodeError:
                print("Warning: ignored one malformed history row.", file=sys.stderr)
    return used


def probe(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(result.stdout or "{}")
    streams = info.get("streams", [])
    kinds = {stream.get("codec_type") for stream in streams}
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    duration = float(info.get("format", {}).get("duration", 0) or 0)
    fps_raw = video.get("avg_frame_rate", "0/1")
    try:
        fps = float(Fraction(fps_raw))
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return (
        kinds, duration, int(video.get("width", 0)), int(video.get("height", 0)),
        fps, video.get("codec_name", ""),
    )


def main():
    config = load_json(CONFIG, {})
    width, height, fps = (
        int(config.get("width", 1080)),
        int(config.get("height", 1920)),
        int(config.get("fps", 30)),
    )
    if (width, height, fps) != (1080, 1920, 30):
        raise RuntimeError("Shorts format lock requires exactly 1080x1920 at 30 fps.")

    dry_run = env_true("DRY_RUN")
    state = load_json(STATE, {"counter": 0, "last_upload_date": None, "uploads": 0})
    today = datetime.datetime.now(IST).date().isoformat()

    used = used_topic_ids()
    counter = int(state.get("counter", 0))
    while True:
        topic = topics.build_topic(counter, config.get("target_seconds", 28))
        if topic["topic_id"] not in used:
            break
        counter += 1
    if counter != int(state.get("counter", 0)):
        print("History guard advanced topic counter to %d." % counter)

    params = dict(topic["params"])
    params.update({
        "topic_label": topic["title"],
        "level": topic["level"],
        "topic_id": topic["topic_id"],
    })
    print("NEW 3D TOPIC #%d  %s" % (topic["counter"], topic["topic_id"]))
    print("Title:", topic["title"])
    print(
        "Scene: %s | palette: %s | shape: %s | material: %s | camera: %s | density: %d" % (
            params["scene"], params["palette"], params["shape"], params["material"],
            params["camera"], params["density"],
        )
    )

    output_dir = ROOT / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    video = output_dir / (topic["topic_id"] + ".mp4")

    from render_video import render_video
    render_video(params, video, width, height, fps, ROOT / "work")

    kinds, duration, rendered_width, rendered_height, rendered_fps, codec = probe(video)
    size_bytes = video.stat().st_size
    if not {"video", "audio"} <= kinds:
        raise RuntimeError("Quality check failed: both video and audio streams are required.")
    if (rendered_width, rendered_height) != (1080, 1920):
        raise RuntimeError(
            "Quality check failed: expected 1080x1920, got %dx%d" %
            (rendered_width, rendered_height)
        )
    if abs(rendered_fps - 30.0) > 0.15:
        raise RuntimeError("Quality check failed: expected 30 fps, got %.3f" % rendered_fps)
    if duration < 15 or duration > 60:
        raise RuntimeError("Quality check failed: Shorts duration %.2fs is outside 15-60s." % duration)
    if codec != "h264" or size_bytes < 300_000:
        raise RuntimeError(
            "Quality check failed: codec=%s, file size=%d bytes" % (codec, size_bytes)
        )
    print(
        "QUALITY OK: %dx%d | %.2f fps | %.1fs | H.264 | %.2f MB" %
        (rendered_width, rendered_height, rendered_fps, duration, size_bytes / 1e6)
    )

    if dry_run:
        print("DRY RUN: upload nahi hua aur topic consume nahi hua. Preview:", video)
        return 0

    from upload_youtube import upload_video
    video_id = upload_video(
        video, topic["title"], topic["description"], topic["tags"],
        privacy="public", made_for_kids=False,
        category_id=config.get("category_id", "24"),
    )
    print("PUBLIC SHORT UPLOADED: https://youtube.com/shorts/%s" % video_id)

    # Only a completed YouTube API upload consumes the topic and appends history.
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    history_record = {
        "counter": counter,
        "topic_id": topic["topic_id"],
        "title": topic["title"],
        "video_id": video_id,
        "date": today,
        "privacy": "public",
        "status": "uploaded",
        "width": rendered_width,
        "height": rendered_height,
        "fps": round(rendered_fps, 3),
        "duration": round(duration, 3),
    }
    with HISTORY.open("a", encoding="utf-8") as history:
        history.write(json.dumps(history_record, ensure_ascii=False) + "\n")

    state["counter"] = counter + 1
    state["last_upload_date"] = today
    state["uploads"] = int(state.get("uploads", 0)) + 1
    state["last_video_id"] = video_id
    state["last_topic_id"] = topic["topic_id"]
    state["last_title"] = topic["title"]
    save_state(state)

    video.unlink(missing_ok=True)
    print("History saved; successful topic consumed; next topic counter=%d." % state["counter"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
