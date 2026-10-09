#!/usr/bin/env python3
"""Daily publisher for approved movie/series/anime clips.

The cloud runner does not synthesize news videos or voiceovers and does not
scrape/download random third-party clips. It edits supplied authorized source
files, keeps their scene audio, adds restrained on-screen caption text, and
requires separate sources for the long video, Short, Reel, and image cards.
"""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CREDS = ROOT / "credentials"
STATE = ROOT / "state" / "state.json"


def restore_secret(name, target):
    value = os.getenv(name, "").strip()
    if not value:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(base64.b64decode(value, validate=True))
    except Exception as exc:
        raise RuntimeError(f"{name} is not valid base64: {exc}")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return True


def run(*args):
    cmd = [sys.executable, "-m", *args]
    print("RUN:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def has_movie_sources():
    """Require actual local source videos and thumbnails, not placeholder metadata."""
    rows = load_json(ROOT / "metadata.json", {"items": []}).get("items", [])
    for item in rows:
        if item.get("licensed") is not True or item.get("type") not in {"movie", "series", "anime"}:
            continue
        source = ROOT / str(item.get("source") or "")
        thumb = ROOT / str(item.get("thumbnail") or "")
        if source.is_file() and thumb.is_file():
            return True
    return False


def verify_daily_youtube_quota():
    state = load_json(STATE, {})
    today = time.strftime("%Y-%m-%d")
    daily = state.get("daily", {}).get(today, {})
    long_sources = [str(x) for x in daily.get("movie_long_sources", [])]
    short_sources = [str(x) for x in daily.get("movie_short_sources", [])]
    long_ok = len(long_sources) >= 1 and bool(daily.get("long_video_id"))
    short_ok = len(short_sources) >= 1 and bool(daily.get("short_video_id"))
    distinct = bool(long_sources and short_sources and long_sources[0] != short_sources[0])
    print(
        f"Movie YouTube audit: long={int(long_ok)}/1 source={long_sources[:1]}, "
        f"short={int(short_ok)}/1 source={short_sources[:1]}, distinct={distinct}"
    )
    if not long_ok or not short_ok or not distinct:
        raise RuntimeError(
            "Movie upload audit failed: need one accepted long video and one accepted Short "
            "from different authorized source items. No news/voiceover fallback is allowed."
        )


def verify_facebook_quota():
    if not (CREDS / "facebook_page.json").is_file():
        raise RuntimeError(
            "YouTube movie uploads may have completed, but Facebook was NOT published: "
            "FACEBOOK_PAGE_B64 is missing. Configure the Page access token before claiming full daily success."
        )
    state = load_json(STATE, {})
    today = time.strftime("%Y-%m-%d")
    daily = state.get("daily", {}).get(today, {})
    reels = [str(x) for x in daily.get("movie_reel_sources", [])]
    if not reels:
        raise RuntimeError(
            "Facebook Reel audit failed: no separate unused licensed Reel source was published today."
        )
    image_posts = [
        x for x in state.get("image_posts", [])
        if x.get("date") == today and x.get("asset_type") == "licensed_image_source"
    ]
    image_uploaded = [
        x for x in image_posts
        if x.get("facebook", {}).get("status") == "uploaded"
    ]
    print(f"Facebook audit: reels={len(reels)}/1; separate image cards uploaded={len(image_uploaded)}")
    if not image_uploaded:
        raise RuntimeError(
            "Facebook image audit failed: no separate licensed image-source card was uploaded. "
            "Add at least one unused item to image_sources.json and provide its licensed local image file."
        )


def main():
    restore_secret("YOUTUBE_CLIENT_SECRET_B64", CREDS / "client_secret.json")
    restore_secret("YOUTUBE_TOKEN_B64", CREDS / "token.json")
    restore_secret("FACEBOOK_PAGE_B64", CREDS / "facebook_page.json")
    restore_secret("INSTAGRAM_ACCESS_TOKEN_B64", CREDS / "instagram_access_token.txt")

    missing_youtube = [
        name for name, path in (
            ("YOUTUBE_CLIENT_SECRET_B64", CREDS / "client_secret.json"),
            ("YOUTUBE_TOKEN_B64", CREDS / "token.json"),
        ) if not path.is_file()
    ]
    if missing_youtube:
        raise RuntimeError("Missing required YouTube Actions secrets: " + ", ".join(missing_youtube))

    if not os.getenv("YOUTUBE_API_KEY", "").strip():
        print("WARNING: YOUTUBE_API_KEY missing; trend metadata discovery is disabled.")
    if not (CREDS / "facebook_page.json").is_file():
        print("WARNING: Facebook Page secret missing; Facebook publishing cannot complete.")

    # Trends are metadata signals only: never download the popular videos themselves.
    if os.getenv("YOUTUBE_API_KEY", "").strip():
        run("trend_engine")
    if (CREDS / "instagram_access_token.txt").is_file() and os.getenv("INSTAGRAM_USER_ID", "").strip():
        os.environ["INSTAGRAM_ACCESS_TOKEN"] = (
            CREDS / "instagram_access_token.txt"
        ).read_text(encoding="utf-8").strip()
        run("instagram_trends")
    if os.getenv("VIRAL_TRACKER_DISABLED", "").strip().lower() != "true":
        run("viral_tracker", "--update")
        run("viral_tracker", "--plan")

    # No generated news replacement: today's content must come from supplied,
    # rights-cleared movie/series/anime source media.
    if not has_movie_sources():
        raise RuntimeError(
            "No usable authorized movie/series/anime source videos found. metadata.json must point "
            "to real local files under input/videos and each item must have licensed=true plus a real thumbnail. "
            "The uploaded ZIP contains the Movie APK but no standalone scene clips; no news/AI-voice fallback will run."
        )

    run("process")
    # A different licensed short-source may be selected for the Facebook Reel.
    run("upload_queue", "--social")
    run("upload_queue", "--daily")

    if (CREDS / "facebook_page.json").is_file():
        run("upload_queue", "--facebook-movie-reels")

    # Photo posts use an independent source manifest so their theme is not the day's video theme.
    run("upload_queue", "--daily-images")
    if (CREDS / "facebook_page.json").is_file():
        run("upload_queue", "--facebook-images")

    verify_daily_youtube_quota()
    verify_facebook_quota()


if __name__ == "__main__":
    main()
