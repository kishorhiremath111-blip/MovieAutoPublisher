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
import sys
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


def _news_story_scores(item, trend_rows):
    """Score individual news stories so a generic roundup title cannot hide strong trends."""
    stories = item.get("stories") or []
    results = []
    now = now_ts()

    for story in stories:
        title = str(story.get("title", ""))
        category = str(story.get("category", "")).lower()
        text = " ".join([title, category, str(story.get("source", ""))])
        story_tokens = tokens(text)

        trend_points = []
        for row in trend_rows:
            overlap = len(story_tokens & row["tokens"])
            if overlap <= 0:
                continue
            age_h = max(0.0, (now - row["published"]) / 3600.0) if row.get("published") else 24.0
            recency = max(0.15, 1.0 - min(age_h, 48.0) / 60.0)
            popularity = 1.0 + min(1.5, math.log10(max(10, row["views"] + 1)) / 8.0)
            trend_points.append(min(5.0, overlap * recency * popularity))

        external_trend = min(30.0, sum(sorted(trend_points, reverse=True)[:6]) * 3.0)

        title_lower = title.lower()
        trigger_words = {
            "breaking", "latest", "update", "announced", "launch", "launched",
            "record", "wins", "won", "deal", "warning", "alert", "discovery",
            "breakthrough", "decision", "ruling", "ban", "banned", "crash",
            "earthquake", "storm", "wildfire", "hack", "arrested", "missing",
            "rescue", "election", "release", "reveals", "teased"
        }
        trigger_hits = sum(1 for x in trigger_words if x in title_lower)
        urgency = min(7.0, trigger_hits * 1.5)

        high_interest_categories = {
            "india": 4.0, "sports": 3.5, "technology": 3.5, "electronics": 3.0,
            "space": 3.0, "cars": 3.0, "bikes": 3.0, "gaming": 3.0,
            "entertainment": 3.0, "anime": 3.0, "world": 2.5, "crime": 3.5,
            "environment": 3.0, "science": 2.5, "business": 2.5, "health": 2.5
        }
        category_signal = high_interest_categories.get(category, 2.0)

        curiosity = 0.0
        if any(x in title_lower for x in (
            "why", "how", "could", "will", "what", "major", "new", "first",
            "record", "surprise", "shakes", "teased", "named", "boost"
        )):
            curiosity += 3.0
        if 6 <= len(title.split()) <= 18:
            curiosity += 2.0

        published = parse_ts(story.get("published"))
        freshness = 0.0
        if published:
            age_h = max(0.0, (now - published) / 3600.0)
            freshness = max(0.0, 5.0 - min(age_h, 30.0) * 0.16)
        else:
            freshness = 2.0

        source_bonus = 2.0 if story.get("source") and story.get("source") != "News source" else 0.0
        score = min(100.0, external_trend + urgency + category_signal + curiosity + freshness + source_bonus)
        results.append({
            "title": title,
            "category": category,
            "score": round(score, 2),
            "external_trend": round(external_trend, 2),
            "urgency": round(urgency, 2),
            "category_signal": round(category_signal, 2),
            "curiosity": round(curiosity, 2),
            "freshness": round(freshness, 2),
        })

    return sorted(results, key=lambda x: x["score"], reverse=True)


def score_candidate(item, trend_rows, tracker):
    # News roundups are scored from their strongest individual stories, not
    # from the generic phrase "World News Roundup".
    if item.get("stories"):
        story_scores = _news_story_scores(item, trend_rows)
        top = story_scores[:3]
        if top:
            top_external = max(x["external_trend"] for x in top)
            top_story = top[0]
            avg_top = sum(x["score"] for x in top) / len(top)

            source_ts = parse_ts(
                item.get("published_at")
                or item.get("created_at")
                or next((s.get("published") for s in item.get("stories", []) if s.get("published")), None)
            )
            now = now_ts()
            if source_ts:
                age_h = max(0.0, (now - source_ts) / 3600.0)
                fresh = max(0.0, 15.0 - min(age_h, 72.0) * 0.21)
            else:
                fresh = 10.0

            fingerprint = str(item.get("fingerprint") or item.get("id") or "")
            recent_ids = {
                str(x.get("fingerprint") or x.get("id") or "")
                for x in tracker.get("used", [])[-500:]
            }
            novelty = 15.0 if fingerprint and fingerprint not in recent_ids else 0.0

            story_count = len(item.get("stories") or [])
            media_count = sum(len(s.get("media") or []) for s in item.get("stories") or [])
            quality = 7.0 + min(4.0, story_count / 3.0) + min(3.0, media_count / 6.0)

            category = str(top_story.get("category", item.get("category", "news"))).lower()
            learned = learned_profile(tracker)
            learned_bonus = min(
                8.0,
                max(0.0, learned.get(f"{category}|news", 3.0) - 3.0) * 2.2
            )

            packaging = 4.0
            if 5 <= len(str(top_story.get("title", "")).split()) <= 16:
                packaging += 3.0
            if any(x in str(top_story.get("title", "")).lower() for x in (
                "why", "how", "will", "could", "breaking", "latest", "record",
                "launch", "warning", "earthquake", "hack", "teased"
            )):
                packaging += 3.0

            # Blend the strongest story's trend signal with the average of the
            # top three. This rewards a real trend without requiring every story
            # in a broad roundup to be trending.
            # News momentum keeps fresh, high-interest headlines scoreable even when external trend overlap is weak.
            trend = min(35.0, max(top_external, top_story["score"] * 2.0) + max(0.0, (avg_top - top_story["score"]) * 0.35))

            total = min(
                100.0,
                trend + fresh + novelty + quality + learned_bonus + packaging
            )
            breakdown = {
                "trend": round(trend, 2),
                "freshness": round(fresh, 2),
                "novelty": round(novelty, 2),
                "quality": round(quality, 2),
                "creator_bonus": 0.0,
                "learned_bonus": round(learned_bonus, 2),
                "packaging": round(packaging, 2),
                "top_story": top_story["title"],
                "top_story_score": top_story["score"],
                "top_story_category": top_story["category"],
                "story_scores": story_scores[:5],
            }
            return round(total, 2), breakdown

    text = " ".join([
        str(item.get("title", "")),
        str(item.get("description", "")),
        str(item.get("category", "")),
        str(item.get("creator", "")),
        " ".join(item.get("tags", []) or [])
    ])
    t = tokens(text)

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

    source_ts = parse_ts(item.get("published_at") or item.get("created_at"))
    if source_ts:
        age_h = max(0.0, (now - source_ts) / 3600.0)
        fresh = max(0.0, 15.0 - min(age_h, 72.0) * 0.21)
    else:
        fresh = 9.0

    category = str(item.get("category", "viral")).lower()
    style = str(item.get("edit_style", "clean")).lower()
    fingerprint = str(item.get("fingerprint") or item.get("id") or "")
    recent_ids = {str(x.get("fingerprint") or x.get("id") or "") for x in tracker.get("used", [])[-500:]}
    novelty = 15.0 if fingerprint and fingerprint not in recent_ids else 0.0

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
    if item.get("stories"):
        ranked = sorted(
            item.get("stories") or [],
            key=lambda s: parse_ts(s.get("published")) or 0,
            reverse=True
        )
        top = ranked[0] if ranked else {}
        top_title = re.sub(r"\s+", " ", str(top.get("title") or "")).strip()
        if top_title:
            title = f"Today's Big Update: {top_title}"
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
    mode = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("VIRAL_TRACKER_MODE", "").strip() or "update").lstrip("-")
    
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

        # Score news first; image posts can inherit the exact score of the
        # fresh news story they visually represent.
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

        news_by_id = {
            str(x.get("id")): x
            for x in state.get("news", [])
            if x.get("id")
        }
        for item in state.get("image_posts", []):
            if item.get("status") != "ready":
                continue
            parent = news_by_id.get(str(item.get("viral_parent_id")))
            if parent and parent.get("viral_score") is not None:
                item["viral_score"] = parent.get("viral_score")
                item["viral_breakdown"] = parent.get("viral_breakdown", {})
                if item["viral_score"] < threshold:
                    item["status"] = "hold"
                    item["hold_reason"] = f"viral_score {item['viral_score']} < {threshold}"

        save(STATE, state)
        print(f"Viral gate applied at {threshold}.")
        return

    print("Usage: VIRAL_TRACKER_MODE=update|plan|gate python viral_tracker.py")


if __name__ == "__main__":
    main()
