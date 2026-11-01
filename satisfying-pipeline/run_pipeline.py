#!/usr/bin/env python3
"""Daily flow:
  1. state se agla topic lo (counter)
  2. video render karo (3D scene + audio)
  3. quality check
  4. YouTube par upload
  5. SIRF upload success hone par topic "use ho gaya" mark karo, video file delete karo

DRY_RUN=true  -> sirf video banao, upload nahi, counter aage nahi badhta
FORCE=true    -> aaj ka daily limit ignore karo
"""
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
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_state(st):
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
         "-of", "json", str(path)], capture_output=True, text=True)
    info = json.loads(r.stdout or "{}")
    kinds = {s.get("codec_type") for s in info.get("streams", [])}
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    return kinds, dur


def main():
    cfg = load_json(CONFIG, {})
    dry, force = env_true("DRY_RUN"), env_true("FORCE")
    st = load_json(STATE, {"counter": 0, "last_upload_date": None, "uploads": 0})
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    if not dry and not force and st.get("last_upload_date") == today:
        print("Aaj ka video pehle hi upload ho chuka hai. Skip. (FORCE=true se override)")
        return 0

    topic = topics.build_topic(st["counter"], cfg.get("target_seconds", 28))
    p = topic["params"]
    print("Topic #%d  %s" % (topic["counter"], topic["topic_id"]))
    print("Title :", topic["title"])
    print("Scene : %s | %s | %s | %s | %d BPM | camera %s | %.1fs" % (
        p["scene"], p["palette"], p["shape"], p["material"], p["bpm"], p["camera"], p["duration"]))

    width = int(cfg.get("width", 720))
    height = int(cfg.get("height", 1280))
    if os.getenv("RES") == "1080":
        width, height = 1080, 1920
    fps = int(cfg.get("fps", 30))

    out_dir = ROOT / "out"
    video = out_dir / ("%s.mp4" % topic["topic_id"])

    from render_video import render_video
    render_video(p, video, width, height, fps, ROOT / "work")

    kinds, dur = probe(video)
    if not {"video", "audio"} <= kinds or dur < 10 or video.stat().st_size < 200_000:
        raise RuntimeError("Quality check fail: kinds=%s dur=%.1f size=%d" % (
            kinds, dur, video.stat().st_size if video.exists() else 0))
    print("Quality check OK: %.1fs, %.1f MB" % (dur, video.stat().st_size / 1e6))

    if dry:
        print("DRY RUN: upload nahi kiya, topic consume nahi hua. Video: %s" % video)
        return 0

    from upload_youtube import upload_video
    video_id = upload_video(
        video, topic["title"], topic["description"], topic["tags"],
        privacy=cfg.get("privacy", "public"),
        made_for_kids=cfg.get("made_for_kids", True),
        category_id=cfg.get("category_id", "24"))
    print("UPLOADED: https://youtube.com/shorts/%s" % video_id)

    # ---- topic consume: counter aage, history me entry, video file delete ----
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"counter": topic["counter"], "topic_id": topic["topic_id"],
                            "title": topic["title"], "video_id": video_id, "date": today}) + "\n")
    st["counter"] += 1
    st["last_upload_date"] = today
    st["uploads"] = st.get("uploads", 0) + 1
    save_state(st)
    video.unlink(missing_ok=True)
    print("Topic %s use ho gaya, hata diya. Next counter = %d" % (topic["topic_id"], st["counter"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
