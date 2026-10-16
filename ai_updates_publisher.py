#!/usr/bin/env python3
"""Create a short original AI-news explainer from official RSS feeds.

This uses an original graphic layout and local TTS, not copied publisher video.
The source links are included in the output metadata and YouTube description.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "ai_updates"
STATE = ROOT / "state" / "ai_updates_seen.json"
FEEDS = [
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("Google DeepMind", "https://deepmind.google/blog/rss.xml"),
    ("Google AI Blog", "https://blog.google/innovation-and-ai/technology/ai/rss/"),
]
WIDTH, HEIGHT = 720, 1280
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def clean(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def parse_feed(name, url):
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "AIUpdatesPublisher/1.0"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        rows = []
        for item in root.findall(".//item")[:30]:
            title = clean(item.findtext("title"))
            link = clean(item.findtext("link"))
            desc = clean(item.findtext("description"))
            pub = clean(item.findtext("pubDate"))
            if title and link and urlparse(link).scheme == "https":
                rows.append({"source": name, "title": title, "link": link,
                             "summary": desc[:700], "published": pub})
        # Atom support for feeds that use it.
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns)[:30]:
            title = clean(entry.findtext("a:title", default="", namespaces=ns))
            link_el = entry.find("a:link", ns)
            link = link_el.attrib.get("href", "") if link_el is not None else ""
            desc_el = entry.find("a:summary", ns) or entry.find("a:content", ns)
            desc = clean("".join(desc_el.itertext())) if desc_el is not None else ""
            pub = clean(entry.findtext("a:updated", default="", namespaces=ns))
            if title and link and urlparse(link).scheme == "https":
                rows.append({"source": name, "title": title, "link": link,
                             "summary": desc[:700], "published": pub})
        return rows
    except Exception as exc:
        print(f"Feed skipped ({name}): {exc}")
        return []


def load_seen():
    try:
        return json.loads(STATE.read_text(encoding="utf-8")).get("links", [])
    except Exception:
        return []


def choose_story():
    seen = set(load_seen())
    stories = []
    for name, url in FEEDS:
        stories.extend(parse_feed(name, url))
    fresh = [x for x in stories if x["link"] not in seen]
    if not fresh:
        raise RuntimeError("No new official AI news found. Safe stop; no duplicate upload.")
    # RSS feed order is generally newest first. Prefer the first unseen official item.
    return fresh[0]


def wrap_lines(draw, text, font, max_width):
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def make_card(story, path):
    im = Image.new("RGB", (WIDTH, HEIGHT), (10, 18, 38))
    d = ImageDraw.Draw(im)
    # Original abstract background shapes; no publisher images are copied.
    d.ellipse((430, -130, 850, 290), fill=(25, 62, 117))
    d.ellipse((-210, 900, 330, 1450), fill=(31, 45, 94))
    d.rounded_rectangle((42, 55, 678, 1225), radius=34, fill=(16, 29, 56), outline=(58, 102, 180), width=3)
    small = ImageFont.truetype(FONT_BOLD, 26)
    title_font = ImageFont.truetype(FONT_BOLD, 43)
    body_font = ImageFont.truetype(FONT_REG, 28)
    foot_font = ImageFont.truetype(FONT_REG, 19)
    d.rounded_rectangle((72, 86, 390, 142), radius=20, fill=(40, 101, 211))
    d.text((91, 98), "AI UPDATE  •  VERIFIED SOURCE", font=ImageFont.truetype(FONT_BOLD, 17), fill="white")
    d.text((78, 184), "WHAT'S NEW IN AI", font=small, fill=(110, 190, 255))
    y = 248
    for line in wrap_lines(d, story["title"], title_font, 560)[:8]:
        d.text((78, y), line, font=title_font, fill=(255, 255, 255))
        y += 57
    y += 28
    summary = story["summary"] or "A new update has been published by an official AI research or product team. Open the source link for the full details."
    summary = summary[:430]
    for line in wrap_lines(d, summary, body_font, 555)[:8]:
        d.text((80, y), line, font=body_font, fill=(210, 222, 242))
        y += 41
    d.line((78, 1040, 640, 1040), fill=(64, 95, 145), width=2)
    d.text((80, 1064), "SOURCE", font=small, fill=(110, 190, 255))
    d.text((80, 1105), story["source"][:46], font=body_font, fill=(255, 255, 255))
    d.text((80, 1162), "Full source link in video description", font=foot_font, fill=(170, 190, 220))
    im.save(path, quality=95)


def run(cmd):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="Upload publicly to YouTube after rendering")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    story = choose_story()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = "AI Update: " + story["title"]
    title = title[:95]
    summary = story["summary"] or "Check the official source for the full announcement."
    narration = f"Here is your AI update. {story['title']}. {summary[:420]}. This update is from {story['source']}. Read the original source link in the description."
    (OUT / "narration.txt").write_text(narration, encoding="utf-8")
    (OUT / "story.json").write_text(json.dumps(story, indent=2, ensure_ascii=False), encoding="utf-8")
    card = OUT / "ai_update_card.png"
    wav = OUT / "narration.wav"
    mp3 = OUT / "narration.mp3"
    video = OUT / "ai_update_short.mp4"
    make_card(story, card)
    run(["espeak-ng", "-v", "en-us", "-s", "150", "-w", str(wav), "-f", str(OUT / "narration.txt")])
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(card), "-i", str(wav),
         "-vf", "scale=720:1280,format=yuv420p", "-c:v", "libx264", "-tune", "stillimage",
         "-r", "25", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(video)])
    description = (
        f"{summary[:900]}\n\nOriginal AI-news summary with synthetic narration and original graphics. "
        f"Please check the primary source for full context.\n\nSource: {story['source']}\n{story['link']}\n\n"
        "#AI #ArtificialIntelligence #TechNews #Shorts"
    )
    metadata = {"title": title, "description": description, "source": story["link"], "video": str(video)}
    (OUT / "upload_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print("DRAFT_READY:", video)
    if args.publish:
        if os.getenv("GITHUB_ACTIONS") == "true":
            import base64
            creds = ROOT / "credentials"
            creds.mkdir(exist_ok=True)
            for secret, target in [
                ("YOUTUBE_CLIENT_SECRET_B64", creds / "client_secret.json"),
                ("YOUTUBE_TOKEN_B64", creds / "token.json"),
            ]:
                value = os.getenv(secret, "").strip()
                if not value:
                    raise RuntimeError(f"Missing GitHub Actions secret: {secret}")
                target.write_bytes(base64.b64decode(value, validate=True))
                target.chmod(0o600)
        sys.path.insert(0, str(ROOT))
        from uploaders.youtube import upload_video
        video_id = upload_video(str(video), title, description, tags=["AI", "Artificial Intelligence", "Tech News", "Shorts"], privacy="public")
        print("YOUTUBE_UPLOAD_SUCCESS: https://youtube.com/shorts/" + video_id)
        seen = load_seen()
        seen.append(story["link"])
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"links": seen[-500:]}, indent=2), encoding="utf-8")
    else:
        print("DRAFT_ONLY: no upload attempted; inspect the video artifact first.")


if __name__ == "__main__":
    main()
