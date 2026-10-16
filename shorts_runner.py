#!/usr/bin/env python3
"""Daily YouTube Shorts-only runner for rights-cleared local source media."""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
import time
from rights_gate import rights_gate

ROOT = Path(__file__).resolve().parent
CREDS = ROOT / "credentials"
STATE = ROOT / "state" / "state.json"


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def restore_secret(name, target):
    value = os.getenv(name, "").strip()
    if not value:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(base64.b64decode(value, validate=True))
    except Exception as exc:
        raise RuntimeError(f"{name} is not valid base64: {exc}") from exc
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return True


def usable_sources():
    rows = load_json(ROOT / "metadata.json", {"items": []}).get("items", [])
    video_root = (ROOT / "input" / "videos").resolve()
    valid = []
    seen_sources, seen_topics = set(), set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        approved, reason = rights_gate(item)
        if not approved:
            print(f"RIGHTS GATE: skip {item.get('id', 'unknown')}: {reason}")
            continue
        if str(item.get("type") or "").strip().lower() not in {"movie", "series", "anime"}:
            continue
        license_note = str(item.get("license") or "").strip()
        if not license_note or any(word in license_note.casefold() for word in ("replace", "placeholder", "todo")):
            continue
        language = str(item.get("audio_language") or "").strip().lower()
        if language not in {"hi", "en"} or item.get("audio_language_verified") is not True:
            continue
        source_raw = str(item.get("source") or "").strip()
        thumb_raw = str(item.get("thumbnail") or "").strip()
        if not source_raw or not thumb_raw:
            continue
        source = (ROOT / source_raw).resolve()
        thumbnail = (ROOT / thumb_raw).resolve()
        if video_root not in source.parents or ROOT.resolve() not in thumbnail.parents:
            continue
        if source.suffix.lower() not in {".mp4", ".mkv", ".mov", ".webm"}:
            continue
        if not source.is_file() or not thumbnail.is_file():
            continue
        topic = str(item.get("topic_id") or item.get("id") or "").strip().casefold()
        if not topic:
            continue
        source_key = str(source)
        if source_key in seen_sources or topic in seen_topics:
            continue
        seen_sources.add(source_key)
        seen_topics.add(topic)
        valid.append(item)
    return valid


def run(*args):
    command = [sys.executable, "-m", *args]
    print("RUN:", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    sources = usable_sources()
    if not sources:
        print(
            "SAFE SKIP: no media passed the rights-review and explicit upload-approval gate. "
            "No YouTube credentials were restored and no upload was attempted."
        )
        return

    for name, path in (
        ("YOUTUBE_CLIENT_SECRET_B64", CREDS / "client_secret.json"),
        ("YOUTUBE_TOKEN_B64", CREDS / "token.json"),
    ):
        restore_secret(name, path)
        if not path.is_file():
            raise RuntimeError(f"Missing required YouTube Actions secret: {name}")

    if os.getenv("YOUTUBE_API_KEY", "").strip():
        run("trend_engine")
    else:
        print("WARNING: YOUTUBE_API_KEY missing; trend metadata discovery is disabled.")

    if os.getenv("VIRAL_TRACKER_DISABLED", "").strip().lower() != "true":
        run("viral_tracker", "--update")
        run("viral_tracker", "--plan")

    run("process", "--daily")
    run("upload_queue", "--daily-shorts")

    today = time.strftime("%Y-%m-%d")
    daily = load_json(STATE, {}).get("daily", {}).get(today, {})
    if not daily.get("short_video_id") or not daily.get("movie_short_sources"):
        raise RuntimeError("Shorts audit failed: YouTube upload ID/source was not recorded.")
    print("SHORTS SUCCESS: https://youtube.com/shorts/" + str(daily["short_video_id"]))


if __name__ == "__main__":
    main()
