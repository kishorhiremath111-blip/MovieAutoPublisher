#!/usr/bin/env python3
"""Official Instagram trend metadata collector.

Third-party Instagram media is not downloaded or reposted. The collector is
used only as a trend/topic signal for generating original media.
"""
import json, os, time, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"state"/"instagram_trends.json"
VERSION=os.getenv("INSTAGRAM_GRAPH_API_VERSION","v24.0")
TOKEN=os.getenv("INSTAGRAM_ACCESS_TOKEN","").strip()
USER_ID=os.getenv("INSTAGRAM_USER_ID","").strip()
HASHTAGS=[x.strip().lstrip("#") for x in os.getenv(
    "INSTAGRAM_HASHTAGS",
    "worldnews,breakingnews,technology,ai,science,india,entertainment,anime"
).split(",") if x.strip()]

def api(path, params):
    q=urllib.parse.urlencode({**params,"access_token":TOKEN})
    req=urllib.request.Request(
        f"https://graph.facebook.com/{VERSION}/{path}?{q}",
        headers={"User-Agent":"MovieAutoPublisher/Instagram-Trends/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def collect(limit_per_tag=8):
    if not TOKEN or not USER_ID:
        print("Instagram trends: not configured; skipping.")
        return []
    rows=[]
    for tag in HASHTAGS:
        try:
            found=api("ig_hashtag_search",{"user_id":USER_ID,"q":tag})
            tag_id=(found.get("data") or [{}])[0].get("id")
            if not tag_id: continue
            data=api(f"{tag_id}/recent_media",{
                "user_id":USER_ID,
                "fields":"id,caption,media_type,permalink,timestamp",
                "limit":str(limit_per_tag)})
            for m in data.get("data",[]):
                rows.append({
                    "hashtag":tag,"id":m.get("id"),
                    "caption":(m.get("caption") or "")[:1000],
                    "media_type":m.get("media_type"),
                    "permalink":m.get("permalink"),
                    "timestamp":m.get("timestamp")})
        except Exception as exc:
            print(f"Instagram hashtag failed #{tag}: {exc}")
    seen=set(); unique=[]
    for row in rows:
        key=row.get("id") or row.get("permalink")
        if not key or key in seen: continue
        seen.add(key); unique.append(row)
    unique.sort(key=lambda x:x.get("timestamp") or "",reverse=True)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({
        "collected_at":int(time.time()),
        "items":unique[:80],
        "rights_note":"Use third-party Instagram media only when separate reuse rights are documented."
    },indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Instagram trends: {len(unique[:80])}")
    return unique[:80]

if __name__=="__main__":
    collect()
