#!/usr/bin/env python3
"""Discover pop-culture trend metadata only; never downloads or republishes videos."""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "pop_culture_trends.json"
API = "https://www.googleapis.com/youtube/v3/search"
QUERIES = [
    "anime trailer India",
    "popular anime discussion",
    "anime dark comedy",
    "web series dark comedy",
    "adult animation comedy",
    "popular anime moments commentary",
    "Hindi web series comedy scene",
]
BLOCKED_TERMS = ("full episode", "full movie", "download", "episode free", "watch free")


def search(api_key, query):
    params = {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "regionCode": "IN",
        "relevanceLanguage": "hi",
        "maxResults": 10,
        "publishedAfter": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 14 * 86400)),
        "q": query,
        "key": api_key,
    }
    req = urllib.request.Request(
        API + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "MovieAutoPublisher/TrendDiscovery/1.0"},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    report = {
        "created_at": int(time.time()),
        "region": "IN",
        "mode": "metadata_only",
        "queries": QUERIES,
        "notice": "Trend candidates only. No third-party media is downloaded. Source clips must be independently authorized before editing/upload.",
        "items": [],
        "errors": [],
    }
    if not api_key:
        report["notice"] += " YOUTUBE_API_KEY is missing, so discovery was skipped."
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Pop-culture trend discovery skipped: YOUTUBE_API_KEY missing.")
        return

    seen = set()
    for query in QUERIES:
        try:
            payload = search(api_key, query)
            for row in payload.get("items", []):
                video_id = str((row.get("id") or {}).get("videoId") or "")
                snippet = row.get("snippet") or {}
                title = str(snippet.get("title") or "").strip()
                if not video_id or video_id in seen:
                    continue
                if any(term in title.casefold() for term in BLOCKED_TERMS):
                    continue
                seen.add(video_id)
                report["items"].append({
                    "video_id": video_id,
                    "title": title,
                    "channel_title": str(snippet.get("channelTitle") or ""),
                    "published_at": str(snippet.get("publishedAt") or ""),
                    "query": query,
                    "url": "https://www.youtube.com/watch?v=" + video_id,
                    "use": "trend_signal_only",
                })
        except Exception as exc:
            report["errors"].append({"query": query, "error": type(exc).__name__ + ": " + str(exc)})
            print(f"Trend query failed ({query}): {type(exc).__name__}: {exc}")

    report["items"].sort(key=lambda item: item.get("published_at", ""), reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pop-culture trend metadata saved: {len(report['items'])} video references; no videos downloaded.")


if __name__ == "__main__":
    main()
