#!/usr/bin/env python3
"""Write an honest daily audit of scene selection, edits, and platform publishing.

This reports evidence present in state files; it never invents upload success.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "state.json"
TRACKER_FILE = STATE_DIR / "viral_tracker.json"
REPORT_JSON = STATE_DIR / "daily_tracker.json"
REPORT_MD = STATE_DIR / "daily_tracker.md"


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = load(STATE_FILE, {})
    tracker = load(TRACKER_FILE, {})
    today = datetime.now(timezone.utc).date().isoformat()
    daily = state.get("daily", {}).get(today, {})
    trends = state.get("trends", {})
    # Preserve the app's actual recorded state; do not infer success from a green workflow.
    platforms = {
        "youtube_long": {"video_id": daily.get("long_video_id"), "sources": daily.get("movie_long_sources", []), "topics": daily.get("movie_long_topics", [])},
        "youtube_short": {"video_id": daily.get("short_video_id"), "sources": daily.get("movie_short_sources", []), "topics": daily.get("movie_short_topics", [])},
        "facebook_reel": {"sources": daily.get("movie_reel_sources", []), "topics": daily.get("movie_reel_topics", [])},
    }
    images = [
        {"topic_id": x.get("topic_id"), "asset_type": x.get("asset_type"),
         "facebook_status": x.get("facebook", {}).get("status"),
         "instagram_status": x.get("instagram", {}).get("status")}
        for x in state.get("image_posts", []) if x.get("date") == today
    ]
    result = {
        "date_utc": today,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
        "workflow_run_number": os.getenv("GITHUB_RUN_NUMBER"),
        "status": "recorded_state_only",
        "daily_platforms": platforms,
        "image_posts": images,
        "trend_tracker": {
            "candidate_count": len(tracker.get("candidates", [])),
            "performance_rows": len(tracker.get("performance", [])),
            "recent_picks": tracker.get("recent_picks", [])[-10:],
        },
        "notes": [
            "A source/topic is only considered published when the uploader state records a platform ID or uploaded status.",
            "This report does not verify copyright ownership, audience retention, or whether content is funny.",
            "Missing credentials, missing media, API limits, and platform rejections can prevent publication.",
            "Trend scores are estimates, not a guarantee of popularity or views."
        ]
    }
    REPORT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Daily Publishing Tracker",
        "",
        f"- Date (UTC): {today}",
        f"- Workflow run: {result['workflow_run_id'] or 'local/manual'}",
        "- Report mode: recorded state only; no success is fabricated.",
        "",
        "## Platform results",
        "",
    ]
    for name, data in platforms.items():
        ident = data.get("video_id")
        sources = data.get("sources") or []
        topics = data.get("topics") or []
        ok = bool(ident) if name.startswith("youtube_") else bool(sources)
        lines.append(f"- **{name}**: {'recorded' if ok else 'NOT RECORDED'}; source(s)={', '.join(map(str, sources)) or 'none'}; topic(s)={', '.join(map(str, topics)) or 'none'}; platform ID={ident or 'none'}")
    lines.extend(["", "## Image posts", ""])
    if images:
        for item in images:
            lines.append(f"- Topic: {item.get('topic_id') or 'unknown'}; type: {item.get('asset_type') or 'unknown'}; Facebook: {item.get('facebook_status') or 'not recorded'}; Instagram: {item.get('instagram_status') or 'not recorded'}")
    else:
        lines.append("- No image-post records found for this date.")
    lines.extend(["", "## Tracker health", "",
        f"- Trend candidates: {result['trend_tracker']['candidate_count']}",
        f"- Performance records: {result['trend_tracker']['performance_rows']}",
        "",
        "## Important limits", ""] + [f"- {note}" for note in result["notes"]] + [""])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_MD.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
