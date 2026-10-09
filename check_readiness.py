#!/usr/bin/env python3
"""Check MovieAutoPublisher inputs and publishing credentials without exposing secrets.

Run from the repository root:
    python check_readiness.py
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEDIA_EXTS = {".mp4", ".mkv", ".mov", ".webm"}


def load_items(filename):
    path = ROOT / filename
    if not path.is_file():
        print(f"MISSING: {filename}")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {filename}: {exc}")
        return []
    items = data.get("items", [])
    if not isinstance(items, list):
        print(f"INVALID: {filename}: 'items' must be a list")
        return []
    return items


def inside_root(path):
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def main():
    print("MovieAutoPublisher — readiness check")
    print("=" * 42)
    rows = load_items("metadata.json")
    usable = []
    seen_paths = set()
    seen_topics = set()

    for item in rows:
        if not isinstance(item, dict):
            continue
        source = ROOT / str(item.get("source") or "")
        thumb = ROOT / str(item.get("thumbnail") or "")
        reasons = []
        if item.get("licensed") is not True:
            reasons.append("licensed must be true only after rights are verified")
        if item.get("type") not in {"movie", "series", "anime"}:
            reasons.append("type must be movie, series, or anime")
        if str(item.get("audio_language") or "").lower() not in {"hi", "en"}:
            reasons.append("audio_language must be hi or en")
        if item.get("audio_language_verified") is not True:
            reasons.append("audio language must be manually verified")
        if not inside_root(source) or not source.is_file():
            reasons.append("source video file is missing or outside repository")
        elif source.suffix.lower() not in MEDIA_EXTS:
            reasons.append("source must be an MP4/MKV/MOV/WEBM video")
        if not inside_root(thumb) or not thumb.is_file():
            reasons.append("thumbnail file is missing or outside repository")
        topic = str(item.get("topic_id") or item.get("id") or "").strip().casefold()
        if not topic:
            reasons.append("topic_id is missing")
        if str(source.resolve()) in seen_paths:
            reasons.append("source path is duplicated")
        if topic and topic in seen_topics:
            reasons.append("topic_id is duplicated")
        if reasons:
            print(f"BLOCKED: {item.get('id', '(unnamed)')}:")
            for reason in reasons:
                print(f"  - {reason}")
        else:
            usable.append(item)
            seen_paths.add(str(source.resolve()))
            seen_topics.add(topic)

    print()
    print(f"Metadata entries: {len(rows)}")
    print(f"Usable authorized sources: {len(usable)}")
    if len(usable) < 2:
        print("BLOCKED: at least 2 distinct authorized source videos/topics are needed")
    else:
        print("PASS: enough distinct sources for the basic long-video + Short source check")

    if not os.getenv("YOUTUBE_CLIENT_SECRET_B64", "").strip():
        print("BLOCKED: GitHub secret YOUTUBE_CLIENT_SECRET_B64 is not configured")
    else:
        print("PRESENT: YOUTUBE_CLIENT_SECRET_B64 (value not shown)")
    if not os.getenv("YOUTUBE_TOKEN_B64", "").strip():
        print("BLOCKED: GitHub secret YOUTUBE_TOKEN_B64 is not configured")
    else:
        print("PRESENT: YOUTUBE_TOKEN_B64 (value not shown)")

    print()
    if len(usable) < 2 or not os.getenv("YOUTUBE_CLIENT_SECRET_B64", "").strip() or not os.getenv("YOUTUBE_TOKEN_B64", "").strip():
        print("RESULT: NOT READY — fix the blockers above before expecting an upload.")
        return 1
    print("RESULT: BASIC INPUT CHECK PASSED — a real workflow run is still needed to verify rendering and upload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
