#!/usr/bin/env python3
"""Render one new satisfying topic; publish Public or keep as a dry-run artifact."""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import topics

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "state.json"
HISTORY = ROOT / "state" / "used_topics.jsonl"
CONFIG = ROOT / "config.json"


def env_true(name):
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_state(state):
    STATE.parent.mkdir(exist_ok=True)
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
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    info = json.loads(result.stdout or "{}")
    streams = info.get("streams", [])
    kinds = {stream.get("codec_type") for stream in streams}
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    duration = float(info.get("format", {}).get("duration", 0) or 0)
    return kinds, duration, int(video_stream.get("width", 0)), int(video_stream.get("height", 0))


def main():
    config = load_json(CONFIG, {})
    dry_run = env_true("DRY_RUN")
    state = load_json(STATE, {"counter": 0, "last_upload_date": None, "uploads": 0})
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    used = used_topic_ids()
    counter = int(state.get("counter", 0))
    while True:
        topic = topics.build_topic(counter, config.get("target_seconds", 28))
        if topic["topic_id"] not in used:
            break
        counter += 1
    if counter != int(state.get("counter", 0)):
        print("Used-topic history ke kaaran counter %d se %d par advance hua." %
              (state.get("counter", 0), counter))

    params = dict(topic["params"])
    params.update({
        "topic_label": topic["title"],
        "level": topic["level"],
        "topic_id": topic["topic_id"],
    })
    print("NEW TOPIC #%d  %s" % (topic["counter"], topic["topic_id"]))
    print("Title:", topic["title"])
    print("Recipe: %s | %s | %s | %s | camera=%s | density=%s | %d BPM" % (
        params["scene"], params["palette"], params["shape"], params["material"],
        params["camera"], params["density"], params["bpm"]))

    width = int(config.get("width", 720))
    height = int(config.get("height", 1280))
    if os.getenv("RES") == "1080":
        width, height = 1080, 1920
    fps = int(config.get("fps", 30))
    output_dir = ROOT / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    video = output_dir / (topic["topic_id"] + ".mp4")

    from render_video import render_video
    render_video(params, video, width, height, fps, ROOT / "work")

    kinds, duration, rendered_width, rendered_height = probe(video)
    size_bytes = video.stat().st_size
    if not {"video", "audio"} <= kinds or duration < 10 or size_bytes < 200_000:
        raise RuntimeError("Quality check failed: streams=%s duration=%.1f size=%d" %
                           (kinds, duration, size_bytes))
    if rendered_height <= rendered_width:
        raise RuntimeError("Output is not vertical: %dx%d" % (rendered_width, rendered_height))
    print("Quality OK: %dx%d, %.1fs, %.1f MB" %
          (rendered_width, rendered_height, duration, size_bytes / 1e6))

    if dry_run:
        print("DRY RUN: upload nahi hua, topic consume nahi hua. Yehi next PUBLIC run ka preview hai. Video:", video)
        return 0

    from upload_youtube import upload_video
    video_id = upload_video(
        video, topic["title"], topic["description"], topic["tags"],
        privacy="public", made_for_kids=False,
        category_id=config.get("category_id", "24"))
    print("PUBLIC SHORT UPLOADED: https://youtube.com/shorts/%s" % video_id)

    video.unlink(missing_ok=True)
    state["counter"] = counter + 1
    state["last_upload_date"] = today
    state["uploads"] = state.get("uploads", 0) + 1
    state["last_video_id"] = video_id
    state["last_topic_id"] = topic["topic_id"]
    save_state(state)

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as history:
        history.write(json.dumps({
            "counter": counter, "topic_id": topic["topic_id"],
            "title": topic["title"], "video_id": video_id, "date": today,
        }) + "\n")
    print("Topic consumed; local MP4 deleted; next topic counter=%d." % state["counter"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
