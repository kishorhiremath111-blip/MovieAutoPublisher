#!/usr/bin/env python3
"""Generate professional Shorts/Reels from explicitly authorized short-form sources.

This module never downloads third-party social-media videos. Put owned/licensed
source clips in input/social_sources/ and describe them in social_sources.json.
It uses trend metadata only as a topic/style signal.
"""
import json
import re
import subprocess
import time
from pathlib import Path

from scene_tools import detect_scene_times, detect_silence_ranges, rank_highlight_windows

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "config.json"
MANIFEST = ROOT / "social_sources.json"
STATE = ROOT / "state" / "state.json"
SRC_DIR = ROOT / "input" / "social_sources"
OUT_DIR = ROOT / "output" / "social"


def load(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def run(cmd):
    print(">", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        print(p.stdout)
        raise RuntimeError("FFmpeg command failed")
    return p.stdout


def duration(path):
    return float(run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ]).strip())


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_") or "social_clip"


def best_window(path, cfg):
    d = duration(path)
    scenes = detect_scene_times(path, float(cfg.get("scene_threshold", 0.35)))
    silence = detect_silence_ranges(path, float(cfg.get("silence_db", -34)))
    ranked = rank_highlight_windows(
        d, scenes,
        count=int(cfg.get("social_candidate_count", 10)),
        clip_seconds=float(cfg.get("social_clip_seconds", 45)),
        silence_ranges=silence,
        min_gap_seconds=float(cfg.get("social_min_gap_seconds", 8)),
    )
    if not ranked:
        length = min(float(cfg.get("social_clip_seconds", 45)), d)
        return 0.0, length, 0.0
    return max(ranked, key=lambda x: x[2])


def render(src, out, start, end, cfg, style):
    width, height = 1080, 1920
    vf = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ]
    # Human-editor look: restrained grading, no synthetic/AI-looking text.
    if style == "dark":
        vf.append("eq=brightness=-0.03:contrast=1.08:saturation=0.88")
        vf.append("vignette=PI/6")
    elif style in {"funny", "roast"}:
        vf.append("eq=contrast=1.04:saturation=1.06")
        vf.append("unsharp=5:5:0.22:5:5:0.0")

    vf.append("format=yuv420p")
    run([
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(src),
        "-t", f"{max(0.5, end-start):.3f}",
        "-vf", ",".join(vf),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", cfg.get("video_bitrate", "3500k"),
        "-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "160k"),
        "-movflags", "+faststart", str(out)
    ])


def main():
    cfg = load(CONFIG, {})
    manifest = load(MANIFEST, {"items": []})
    state = load(STATE, {"social": []})
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    items = manifest.get("items", [])
    if not items:
        print("Social clips: no authorized sources configured; skipping.")
        return

    today = time.strftime("%Y-%m-%d")
    limit = int(cfg.get("daily_social_clips", 2))
    created = 0

    for item in items:
        if created >= limit:
            break
        if item.get("licensed") is not True:
            print(f"SKIP {item.get('id','unknown')}: licensed=true required")
            continue

        source = ROOT / str(item.get("source", ""))
        if not source.exists():
            source = SRC_DIR / Path(str(item.get("source", ""))).name
        if not source.exists():
            print(f"SKIP missing source: {source}")
            continue

        item_id = str(item.get("id") or safe_name(source.stem))
        if any(x.get("id") == item_id for x in state.get("social", [])):
            continue

        start, end, score = best_window(source, cfg)
        style = str(item.get("edit_style", "clean")).lower()
        out = OUT_DIR / f"{safe_name(item_id)}_{today}_SHORT.mp4"
        render(source, out, start, end, cfg, style)

        row = {
            "id": item_id,
            "date": today,
            "status": "ready",
            "video": str(out.relative_to(ROOT)),
            "title": str(item.get("title") or source.stem).strip()[:100],
            "description": str(item.get("description", "")).strip()[:5000],
            "tags": item.get("tags", []),
            "category": item.get("category", "viral"),
            "source": str(source.relative_to(ROOT)),
            "licensed": True,
            "edit_style": style,
            "selected_highlight": {
                "start": round(start, 2),
                "end": round(end, 2),
                "score": round(score, 4),
            },
        }
        state.setdefault("social", []).append(row)
        save(STATE, state)
        created += 1
        print(f"READY social clip: {out}")

    print(f"Social clips created: {created}/{limit}")


if __name__ == "__main__":
    main()
