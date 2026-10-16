#!/usr/bin/env python3
"""Build a source-intake queue from trend metadata and review-only rights-cleared candidates.

This module never downloads third-party videos. Trend videos are signals only; the only
download path remains internet_archive_collector.py --download-approved, which requires
a separately reviewed allowlist entry and independent rights evidence.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TREND_FILE = ROOT / "output" / "pop_culture_trends.json"
ARCHIVE_FILE = ROOT / "output" / "internet_archive_candidates.json"
OUT_FILE = ROOT / "output" / "source_intake_queue.json"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main():
    trends = read_json(TREND_FILE)
    archive = read_json(ARCHIVE_FILE)
    trend_rows = trends.get("items", []) if isinstance(trends, dict) else []
    archive_rows = archive.get("items", []) if isinstance(archive, dict) else []

    # Trending references are ranked as research leads only; they are never treated as
    # source files or permission to download/repost the referenced video.
    trend_leads = []
    seen = set()
    for row in trend_rows:
        if not isinstance(row, dict):
            continue
        video_id = str(row.get("video_id") or "").strip()
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        trend_leads.append({
            "title": str(row.get("title") or "Untitled trend"),
            "channel_title": str(row.get("channel_title") or ""),
            "published_at": str(row.get("published_at") or ""),
            "url": str(row.get("url") or ""),
            "query": str(row.get("query") or ""),
            "use": "topic_research_only",
            "media_download_allowed": False,
            "next_step": "Find an independently licensed, permissioned, or public-domain source for this topic.",
        })

    candidate_leads = []
    for row in archive_rows:
        if not isinstance(row, dict):
            continue
        candidate_leads.append({
            "identifier": str(row.get("identifier") or ""),
            "title": str(row.get("title") or "Untitled archive candidate"),
            "archive_url": str(row.get("archive_url") or ""),
            "licenseurl": str(row.get("licenseurl") or ""),
            "rights": str(row.get("rights") or ""),
            "review_required": True,
            "approved_for_download": False,
            "next_step": "Verify the exact edition and reuse rights in India; add independent evidence to config/internet_archive_public_domain.json before download.",
        })

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "review_required",
        "summary": {
            "trend_topic_leads": len(trend_leads),
            "public_domain_candidates": len(candidate_leads),
            "downloaded_by_this_script": 0,
        },
        "safety_notice": (
            "Trend popularity is not permission. No video is downloaded by this intake step. "
            "Editing or shortening a copyrighted scene does not clear copyright. Only source "
            "files that pass the existing rights gate and explicit upload approval may publish."
        ),
        "trend_topic_leads": trend_leads,
        "public_domain_candidates": candidate_leads,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Source intake queue written: {len(trend_leads)} trend leads, "
        f"{len(candidate_leads)} archive candidates; no media downloaded."
    )


if __name__ == "__main__":
    main()
