#!/usr/bin/env python3
"""Trend + performance scoring for MovieAutoPublisher.

This tracker does not guarantee virality and never fabricates engagement.
It ranks fresh, authorized candidates using current trend metadata, novelty,
content quality signals and the channel's own historical performance.
"""
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "config.json"
STATE = ROOT / "state" / "state.json"
TRACKER = ROOT / "state" / "viral_tracker.json"
SOCIAL_MANIFEST = ROOT / "social_sources.json"


STOP = {
    "the","and","for","with","this","that","from","your","you","are","was","were",
    "has","have","had","will","into","about","after","before","just","very","more",
    "new","latest","video","short","reel","official","india","news"
}


def load(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def tokens(text):
    vals = re.findall(r"[a-z0-9][a-z0-9+#'-]{2,}", str(text or "").lower())
    return {x.strip("#'-") for x in vals if x.strip("#'-") not in STOP}


def now_ts():
    return int(time.time())


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def trend_index():
    yt = load(ROOT / "state" / "youtube_trends.json", {"popular": [], "music": [], "10m_plus_popular_metadata": []})
    ig = load(ROOT / "state" / "instagram_trends.json", {"items": []})

    rows = []
    for item in yt.get("popular", [])[:100]:
        title = str(item.get("title", ""))
        rows.append({
            "text": title,
            "tokens": tokens(title) | tokens(item.get("channel_title")),
            "published": parse_ts(item.get("published_at")),
            "views": int(item.get("view_count", 0) or 0),
            "likes": int(item.get("like_count", 0) or 0),
            "subs": int(item.get("subscribers", 0) or 0),
            "source": "youtube"
        })
    for item in yt.get("music", [])[:50]:
        title = str(item.get("title", ""))
        rows.append({
            "text": title,
            "tokens": tokens(title) | tokens(item.get("channel_title")),
            "published": parse_ts(item.get("published_at")),
            "views": int(item.get("view_count", 0) or 0),
            "likes": int(item.get("like_count", 0) or 0),
            "subs": int(item.get("subscribers", 0) or 0),
            "source": "youtube_music"
        })
    for item in ig.get("items", [])[:100]:
        text = str(item.get("caption", ""))
        rows.append({
            "text": text,
            "tokens": tokens(text) | tokens(item.get("hashtag")),
            "published": parse_ts(item.get("timestamp")),
            "views": 0,
            "likes": 0,
            "subs": 0,
            "source": "instagram"
        })
    return rows


def learned_profile(tracker):
    by_key = {}
    for row in tracker.get("performance", []):
        category = str(row.get("category", "")).lower().strip()
        style = str(row.get("edit_style", "")).lower().strip()
        if not category and not style:
            continue
        key = f"{category}|{style}"
        score = float(row.get("views_24h", row.get("views", 0)) or 0)
        by_key.setdefault(key, []).append(score)

    result = {}
    for key, vals in by_key.items():
        vals = sorted(vals)[-10:]
        result[key] = sum(math.log10(v + 1) for v in vals) / max(1, len(vals))
    return result


def score_candidate(item, trend_rows, tracker):
    text = " ".join([
        str(item.get("title", "")),
        str(item.get("description", "")),
        str(item.get("category", "")),
        str(item.get("creator", "")),
        " ".join(item.get("tags", []) or [])
    ])
    t = tokens(text)

    # Trend relevance: current terms/phrases, weighted by recency.
    trend_points = []
    now = now_ts()
    for row in trend_rows:
        overlap = len(t & row["tokens"])
        if overlap <= 0:
            continue
        age_h = max(0.0, (now - row["published"]) / 3600.0) if row.get("published") else 24.0
        recency = max(0.15, 1.0 - min(age_h, 48.0) / 60.0)
        popularity = 1.0 + min(1.5, math.log10(max(10, row["views"] + 1)) / 8.0)
        trend_points.append(min(4.0, overlap * recency * popularity))
    trend = min(30.0, sum(sorted(trend_points, reverse=True)[:8]) * 3.0)

    # Freshness from an explicit source timestamp when supplied.
    source_ts = parse_ts(item.get("published_at") or item.get("created_at"))
    if source_ts:
        age_h = max(0.0, (now - source_ts) / 3600.0)
        fresh = max(0.0, 15.0 - min(age_h, 72.0) * 0.21)
    else:
        fresh = 9.0

    category = str(item.get("category", "viral")).lower()
    style = str(item.get("edit_style", "clean")).lower()

    # Novelty: no previous source/content fingerprint means full points.
    fingerprint = str(item.get("fingerprint") or item.get("id") or "")
    recent_ids = {str(x.get("fingerprint") or x.get("id") or "") for x in tracker.get("used", [])[-500:]}
    novelty = 15.0 if fingerprint and fingerprint not in recent_ids else 0.0

    # Stronger hook/edit metadata gets a modest boost.
    quality = 6.0
    if item.get("selected_highlight"):
        h = item["selected_highlight"]
        q = float(h.get("score", 0) or 0)
        quality += min(8.0, max(0.0, q * 2.0))
    if item.get("hook_text"):
        quality += 1.5

    creator = str(item.get("creator", "")).lower()
    creator_bonus = 0.0
    for row in trend_rows:
        if row.get("subs", 0) >= 10_000_000 and creator and creator in str(row.get("text", "")).lower():
            creator_bonus = 6.0
            break

    learned = learned_profile(tracker)
    profile_key = f"{category}|{style}"
    learned_bonus = 0.0
    if profile_key in learned:
        learned_bonus = min(8.0, max(0.0, learned[profile_key] - 3.0) * 2.2)

    # Packaging potential: short, clear title with a curiosity-bearing phrase.
    title = str(item.get("title", "")).strip()
    word_count = len(title.split())
    packaging = 0.0
    if 3 <= word_count <= 12:
        packaging += 5.0
    if any(x in title.lower() for x in ("why", "wait", "look", "moment", "watch", "plot twist", "no way", "this is", "when")):
        packaging += 3.0
    if "#" not in title:
        packaging += 1.0

    total = min(100.0, trend + fresh + novelty + quality + creator_bonus + learned_bonus + packaging)
    return round(total, 2), {
        "trend": round(trend, 2),
        "freshness": round(fresh, 2),
        "novelty": round(novelty, 2),
        "quality": round(quality, 2),
        "creator_bonus": round(creator_bonus, 2),
        "learned_bonus": round(learned_bonus, 2),
        "packaging": round(packaging, 2),
    }


def make_pack(item, trend_rows, score):
    title = str(item.get("title") or "").strip()
    if not title:
        title = str(item.get("category") or "Trending moment").strip().title()

    # Keep title truthful; punch comes from structure, not fake claims.
    title = re.sub(r"\s+", " ", title)[:92].strip(" -")
    if score >= 85 and "!" not in title and len(title) < 86:
        title += " 🔥"

    category = str(item.get("category", "viral")).lower()
    hashtag_pool = [category, "viral", "trending", "shorts", "reels"]
    source_tokens = tokens(title)
    matched = []
    for row in trend_rows:
        overlap = len(source_tokens & row["tokens"])
        if overlap:
            matched.extend(sorted(source_tokens & row["tokens"]))
    for x in matched:
        if x not in hashtag_pool and 3 <= len(x) <= 18:
            hashtag_pool.append(x)
    hashtags = ["#" + re.sub(r"[^a-zA-Z0-9]", "", x) for x in hashtag_pool[:10] if x]

    words = [w for w in re.findall(r"[A-Za-z0-9']+", title.upper()) if len(w) >= 3]
    thumb_text = " ".join(words[:4]) or "WATCH THIS"
    return {
        "title": title[:100],
        "hashtags": hashtags,
        "tags": [h[1:] for h in hashtags],
        "thumbnail_text": thumb_text[:28],
        "viral_score": score,
    }


def update_youtube_performance(tracker):
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        return
    rows = tracker.get("published_youtube", [])
    if not rows:
        return

    ids = [str(x.get("video_id")) for x in rows if x.get("video_id")]
    if not ids:
        return

    url = "https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode({
        "part": "statistics,snippet",
        "id": ",".join(ids[:50]),
        "key": key
    })
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MovieAutoPublisher/ViralTracker/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        print(f"Viral tracker YouTube update failed: {exc}")
        return

    found = {x.get("id"): x for x in data.get("items", [])}
    now = now_ts()
    for row in rows:
        item = found.get(str(row.get("video_id")))
        if not item:
            continue
        stats = item.get("statistics", {})
        views = int(stats.get("viewCount", 0) or 0)
        likes = int(stats.get("likeCount", 0) or 0)
        comments = int(stats.get("commentCount", 0) or 0)
        published = parse_ts(item.get("snippet", {}).get("publishedAt")) or row.get("published_at") or now
        age_h = max(0.05, (now - published) / 3600.0)
        row.update({
            "views": views,
            "likes": likes,
            "comments": comments,
            "engagement_rate": round(((likes + comments) / max(1, views)) * 100.0, 3),
            "views_per_hour": round(views / age_h, 2),
            "updated_at": now,
        })

        # 24h snapshot for learning.
        if age_h >= 23.0 and not row.get("views_24h_recorded"):
            row["views_24h"] = views
            row["views_24h_recorded"] = True


def main():
    cfg = load(CONFIG, {})
    tracker = load(TRACKER, {
        "created_at": now_ts(),
        "used": [],
        "published_youtube": [],
        "performance": [],
        "last_update": None,
        "last_plan": None
    })
    state = load(STATE, {"social": [], "news": []})
    trends = trend_index()
    mode = os.getenv("VIRAL_TRACKER_MODE", "").strip() or "update"
    
    if mode == "update":
        update_youtube_performance(tracker)
        for row in tracker.get("published_youtube", []):
            if row.get("views_24h_recorded") and not row.get("learning_saved"):
                tracker.setdefault("performance", []).append({
                    "category": row.get("category"),
                    "edit_style": row.get("edit_style"),
                    "views_24h": row.get("views_24h", 0),
                    "viral_score": row.get("viral_score", 0)
                })
                row["learning_saved"] = True
        tracker["last_update"] = now_ts()
        save(TRACKER, tracker)
        print("Viral tracker: performance updated.")
        return

    if mode == "plan":
        manifest = load(SOCIAL_MANIFEST, {"items": []})
        candidates = []
        for item in manifest.get("items", []):
            if item.get("licensed") is not True:
                continue
            score, breakdown = score_candidate(item, trends, tracker)
            candidates.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "category": item.get("category", "viral"),
                "edit_style": item.get("edit_style", "clean"),
                "viral_score": score,
                "breakdown": breakdown,
            })
        candidates.sort(key=lambda x: x["viral_score"], reverse=True)
        tracker["last_plan"] = {
            "created_at": now_ts(),
            "candidates": candidates[:10],
            "selected_id": candidates[0]["id"] if candidates else None,
        }
        save(TRACKER, tracker)
        print(f"Viral plan: candidates={len(candidates)} selected={tracker['last_plan']['selected_id']}")
        return

    if mode == "gate":
        threshold = float(cfg.get("viral_pre_publish_min_score", 75))
        for collection_name in ("social", "news"):
            for item in state.get(collection_name, []):
                if item.get("status") != "ready":
                    continue
                score, breakdown = score_candidate(item, trends, tracker)
                item["viral_score"] = score
                item["viral_breakdown"] = breakdown
                item.setdefault("viral_pack", make_pack(item, trends, score))
                if score < threshold:
                    item["status"] = "hold"
                    item["hold_reason"] = f"viral_score {score} < {threshold}"
        save(STATE, state)
        print(f"Viral gate applied at {threshold}.")
        return

    print("Usage: VIRAL_TRACKER_MODE=update|plan|gate python viral_tracker.py")


if __name__ == "__main__":
    main()
