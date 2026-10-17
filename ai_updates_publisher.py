#!/usr/bin/env python3
"""VYROX DAILY - image-led, no-voice Shorts with original luxury visuals and sourced facts.

What changed vs the first version
  * a new story every run (category rotation + dedupe that also counts drafts)
  * 7-9 slides per Short instead of one static photo: hook, details, key terms, source, follow
  * original generated visuals per category (no scraped og:image photos)
  * Ken Burns motion, crossfade/xfade transitions, fade-in text, sound-design whooshes
  * licensed music from input/music/<category>/ when present, otherwise generated ambient bed
  * uploads are PRIVATE unless VYROX_PRIVACY=public is set

Usage
  python ai_updates_publisher.py                 # render a draft from live feeds
  python ai_updates_publisher.py --publish       # render + upload (privacy from VYROX_PRIVACY)
  python ai_updates_publisher.py --demo ANIME    # offline sample, no feeds, no state change
  python ai_updates_publisher.py --category AI   # force a category
"""
import argparse, hashlib, html, json, math, os, random, re, shutil, subprocess, sys, time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "ai_updates"
STATE = ROOT / "state" / "ai_updates_seen.json"
W, H, FPS = 1080, 1920, 25
T = 0.5                      # transition length (s)
TARGET = 35.0                # wanted video length (s); final length stays within 30-40
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VYROXDaily/2.0)"}
GOLD = (212, 175, 55)

SERIF_B = ["assets/fonts/PlayfairDisplay-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]
SANS_B = ["assets/fonts/Montserrat-ExtraBold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
SANS = ["assets/fonts/Montserrat-Medium.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]

# Rotate through useful news, history and light entertainment; one fresh story per run.
ROTATION = ["AI", "FUNNY", "SCIENCE", "HISTORY", "HEALTH", "WORLD", "SPACE", "TECH", "ANIME", "FUNNY", "HISTORY", "AI"]

CATS = {
    "AI": dict(top=(5, 9, 28), bot=(18, 42, 100), accent=(0, 210, 255), label="AI UPDATE",
               tags="#AI #ArtificialIntelligence #TechNews #Shorts",
               kickers=["AI JUST MOVED AGAIN", "NEW IN AI TODAY", "THIS AI UPDATE MATTERS"],
               feeds=[("Google AI Blog", "https://blog.google/technology/ai/rss/", "official"),
                      ("OpenAI News", "https://openai.com/news/rss.xml", "official")]),
    "SCIENCE": dict(top=(3, 16, 22), bot=(8, 72, 72), accent=(90, 255, 200), label="SCIENCE",
                    tags="#Science #Discovery #Research #Shorts",
                    kickers=["SCIENCE JUST DROPPED THIS", "A NEW DISCOVERY", "WORTH KNOWING TODAY"],
                    feeds=[("NASA", "https://www.nasa.gov/feed/", "official"),
                           ("ScienceDaily", "https://www.sciencedaily.com/rss/top/science.xml", "press")]),
    "SPACE": dict(top=(6, 4, 20), bot=(42, 20, 96), accent=(176, 136, 255), label="SPACE",
                  tags="#Space #NASA #Astronomy #Shorts",
                  kickers=["BREAKING FROM SPACE", "LOOK UP: NEW UPDATE", "SPACE NEWS TODAY"],
                  feeds=[("NASA", "https://www.nasa.gov/feed/", "official"),
                         ("Space.com", "https://www.space.com/feeds/all", "press")]),
    "HEALTH": dict(top=(4, 20, 22), bot=(10, 84, 80), accent=(255, 128, 140), label="HEALTH",
                   tags="#Health #Wellness #Science #Shorts",
                   kickers=["HEALTH UPDATE", "WHAT HEALTH EXPERTS SAY", "KNOW THIS TODAY"],
                   feeds=[("World Health Organization", "https://www.who.int/rss-feeds/news-english.xml", "official")]),
    "WORLD": dict(top=(8, 16, 36), bot=(20, 62, 112), accent=(96, 190, 255), label="WORLD",
                  tags="#WorldNews #News #Global #Shorts",
                  kickers=["WORLD UPDATE", "WHAT JUST HAPPENED", "IMPORTANT TODAY"],
                  feeds=[("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "official")]),
    "TECH": dict(top=(10, 10, 16), bot=(44, 44, 66), accent=(255, 172, 64), label="TECH",
                 tags="#Tech #Technology #Gadgets #Shorts",
                 kickers=["NEW IN TECH", "TECH UPDATE", "DEVELOPERS ARE TALKING ABOUT THIS"],
                 feeds=[("Android Developers Blog", "https://android-developers.googleblog.com/feeds/posts/default?alt=rss", "official"),
                        ("Google Blog", "https://blog.google/rss/", "official")]),
    "ANIME": dict(top=(26, 6, 24), bot=(104, 22, 86), accent=(255, 122, 202), label="ANIME UPDATE",
                  tags="#Anime #AnimeNews #Otaku #Shorts",
                  kickers=["ANIME UPDATE", "ANIME FANS, LISTEN UP", "NEW ANIME NEWS"],
                  feeds=[("Anime News Network", "https://www.animenewsnetwork.com/news/rss.xml", "press"),
                         ("MyAnimeList News", "https://myanimelist.net/rss/news.xml", "press")]),
    "HISTORY": dict(top=(22, 14, 7), bot=(88, 49, 20), accent=(255, 196, 88), label="HISTORY",
                    tags="#History #DidYouKnow #Facts #Shorts",
                    kickers=["HISTORY THEY DIDN'T TEACH YOU", "A MOMENT FROM HISTORY", "DID YOU KNOW?"],
                    feeds=[("History Extra", "https://www.historyextra.com/feed/", "press"),
                           ("Smithsonian Magazine", "https://www.smithsonianmag.com/rss/latest_articles/", "press")]),
    "FUNNY": dict(top=(22, 5, 18), bot=(100, 22, 52), accent=(255, 190, 60), label="FUNNY FACTS",
                  tags="#Funny #FunFacts #DidYouKnow #Shorts",
                  kickers=["THIS IS WILD", "WAIT FOR IT", "YOU CAN'T MAKE THIS UP"],
                  feeds=[("Reddit Funny", "https://www.reddit.com/r/funny/.rss", "press"),
                         ("Reddit Today I Learned", "https://www.reddit.com/r/todayilearned/.rss", "press")]),
}

DEMO = {
    "AI": ("A new AI model can plan multi-step tasks with fewer mistakes",
           "Researchers released an AI model that plans multi-step tasks more reliably. In internal tests it made 40% fewer errors on long tasks. The team says it is aimed at coding and research work. A public preview opens to developers next month.",
           "Demo Source"),
    "ANIME": ("A long-running anime announces a new season for next year",
              "The studio confirmed a new season will premiere next year. The original cast is returning for all main roles. A first teaser trailer is expected in the coming weeks. Episode count has not been announced yet.",
              "Demo Source"),
    "SERIES": ("A popular streaming series is renewed for a third season",
               "The streamer renewed the series after its season two finale drew record viewers. Filming begins early next year. The returning cast was confirmed alongside the renewal. A release window has not been shared.",
               "Demo Source"),
    "SPACE": ("A spacecraft sends back its sharpest images of a distant asteroid",
              "The probe passed within 3,000 km of the asteroid and captured high-resolution images. Scientists will study its surface for signs of water ice. More data arrives over the next two weeks.",
              "Demo Source"),
    "SCIENCE": ("Scientists find a faster way to grow lab-made bone tissue",
                "A research team developed a method that grows bone tissue 3 times faster in the lab. The approach uses a new scaffold material. Early results are published in a peer-reviewed journal. Clinical trials are still years away.",
                "Demo Source"),
    "HEALTH": ("New guidance highlights the value of regular sleep for adults",
               "Health experts say consistent sleep timing supports heart and brain health. Adults are advised to aim for 7 to 9 hours each night. The guidance also covers screen use before bed.",
               "Demo Source"),
    "WORLD": ("Countries agree on a new framework to protect ocean ecosystems",
              "Delegates from more than 100 countries agreed on a framework for protecting ocean areas. It sets new limits on harmful fishing. Implementation begins next year.",
              "Demo Source"),
    "TECH": ("A new Android release focuses on faster apps and better battery life",
             "The update includes performance tools for developers. It adds new options for background work that save battery. Developers can test it today in the preview channel.",
             "Demo Source"),
}


# --------------------------------------------------------------------------- text helpers
def clean(v):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", v or ""))).strip()


def norm_key(title):
    return hashlib.sha1(re.sub(r"[^a-z0-9]+", " ", title.lower()).strip().encode()).hexdigest()[:16]


def font(paths, size):
    for p in paths:
        path = Path(p) if p.startswith("/") else ROOT / p
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def wrap(draw, text, f, maxw):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=f) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def spaced(draw, xy, text, f, fill, gap=6, anchor="l"):
    """Draw letter-spaced text; anchor 'l' (left), 'm' (center) or 'r' (right)."""
    widths = [draw.textlength(c, font=f) for c in text]
    total = sum(widths) + gap * max(0, len(text) - 1)
    x, y = xy
    if anchor == "m":
        x -= total / 2
    elif anchor == "r":
        x -= total
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=f, fill=fill)
        x += w + gap
    return total


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", clean(text))
    return [p.strip() for p in parts if len(p.strip()) >= 25]


def split_long(sent, limit=135):
    out = []
    while len(sent) > limit:
        cut = -1
        for m in re.finditer(r"[,;:]\s|\s[-\u2013\u2014]\s|\sand\s|\sbut\s", sent[:limit]):
            if m.end() > 50:
                cut = m.end()
        if cut == -1:
            cut = sent.rfind(" ", 0, limit)
        if cut <= 20:
            break
        out.append(sent[:cut].strip(" ,;:"))
        sent = sent[cut:].strip()
    out.append(sent)
    return [x for x in out if x]


def shorten(text, n):
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "\u2026"


def key_terms(text, limit=5):
    terms, seen = [], set()
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9]{2,}(?:\s+[A-Z][A-Za-z0-9]{2,})*|[A-Z]{2,}[A-Za-z0-9]*|\d[\d,\.]*\s?(?:%|percent|million|billion|trillion|km|GB|TB|MB|years?|days?|times)?)", text):
        t = m.group(1).strip()
        low = t.lower()
        before = text[:m.start()].rstrip()
        starts_sentence = (not before) or before.endswith((".", "!", "?", ":"))
        plain_word = t[0].isupper() and not t.isupper() and not any(ch.isdigit() for ch in t) and " " not in t
        if starts_sentence and plain_word:
            continue
        if low in seen or len(t) < 3 or re.fullmatch(r"(19|20)\d\d", t):
            continue
        if low in {"the", "this", "that", "with", "from", "they", "their", "there", "when", "while", "after", "will", "have"}:
            continue
        seen.add(low)
        terms.append(t)
        if len(terms) >= limit:
            break
    return terms


STAT_RE = re.compile(r"(\$?\d[\d,\.]*\s?(?:%|percent|million|billion|trillion|times|x|km|GB|TB|MB)?)")


def stat_of(piece):
    for m in STAT_RE.finditer(piece):
        t = m.group(1).strip()
        digits = re.sub(r"\D", "", t)
        if len(digits) >= 1 and not re.fullmatch(r"(19|20)\d\d", digits) and (len(digits) >= 2 or "%" in t or "x" in t or "times" in t):
            return t
    return None


# --------------------------------------------------------------------------- feeds, state, selection
def parse_feed(category, source, url, trust):
    limit = 420 if trust == "official" else 200
    rows = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:25]:
            title, link = clean(item.findtext("title")), clean(item.findtext("link"))
            desc, pub = clean(item.findtext("description")), clean(item.findtext("pubDate"))
            if title and link.startswith("https://"):
                rows.append((category, source, title, link, desc, pub))
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for e in root.findall(".//a:entry", ns)[:25]:
            title = clean(e.findtext("a:title", default="", namespaces=ns))
            le = e.find("a:link", ns)
            link = le.attrib.get("href", "") if le is not None else ""
            de = e.find("a:summary", ns)
            if de is None:
                de = e.find("a:content", ns)
            desc = clean(" ".join(de.itertext())) if de is not None else ""
            pub = clean(e.findtext("a:updated", default="", namespaces=ns))
            if title and link.startswith("https://"):
                rows.append((category, source, title, link, desc, pub))
    except Exception as exc:
        print(f"Feed unavailable {source}: {exc}")
    out = []
    for category, source, title, link, desc, pub in rows:
        text, total = [], 0
        for s in sentences(desc):
            if total + len(s) > limit and text:
                break
            text.append(s)
            total += len(s)
        out.append({"category": category, "source": source, "title": title, "link": link,
                    "summary": " ".join(text)[:limit + 80], "published": pub, "trust": trust})
    return out


def load_state():
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return set(d.get("links", [])), set(d.get("keys", []))
    except Exception:
        return set(), set()


def save_state(links, keys):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"links": sorted(links)[-800:], "keys": sorted(keys)[-800:]}, indent=2), encoding="utf-8")


def pick_story(forced=None):
    links, keys = load_state()
    now = datetime.now(timezone.utc)
    slot = 0 if now.hour < 11 else 1
    start = (now.date().toordinal() * 2 + slot) % len(ROTATION)
    order = [forced] if forced else [ROTATION[(start + k) % len(ROTATION)] for k in range(len(ROTATION))]
    rng = random.SystemRandom()
    for cat in order:
        rows = []
        for source, url, trust in CATS[cat]["feeds"]:
            rows += parse_feed(cat, source, url, trust)
        fresh = [r for r in rows if r["link"] not in links and norm_key(r["title"]) not in keys]
        if fresh:
            return rng.choice(fresh[:6])
        print(f"No unseen story in {cat}; trying next category.")
    raise RuntimeError("No unseen source story found in any category. Skipping rather than reposting.")


# --------------------------------------------------------------------------- visuals
def make_bg(cat, seed, variant):
    c = CATS[cat]
    rng = random.Random(f"{seed}-{variant}")
    top, bot, ac = c["top"], c["bot"], c["accent"]
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line((0, y, W, y), fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    blobs = Image.new("RGB", (W // 4, H // 4), (0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    for _ in range(4):
        cx, cy, r = rng.randint(0, W // 4), rng.randint(0, H // 4), rng.randint(70, 140)
        col = tuple(int(x * rng.uniform(0.28, 0.6)) for x in ac)
        bd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    blobs = blobs.filter(ImageFilter.GaussianBlur(38)).resize((W, H), Image.Resampling.BICUBIC)
    img = ImageChops.add(img, blobs).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_motif(cat, ov, rng, ac)
    r_, g_, b_, a_ = ov.split()
    ov = Image.merge("RGBA", (r_, g_, b_, a_.point(lambda v: min(255, int(v * 1.6)))))
    img.alpha_composite(ov.filter(ImageFilter.GaussianBlur(1.1)))
    g = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(max(0, v - 95) * 1.25))
    img.paste((0, 0, 0), mask=g)
    return img.convert("RGB")


def draw_motif(cat, ov, rng, ac):
    d = ImageDraw.Draw(ov)
    if cat == "AI":
        pts = [(rng.randint(-40, W + 40), rng.randint(120, H - 120)) for _ in range(48)]
        for i, p in enumerate(pts):
            for q in pts[i + 1:]:
                dist = math.dist(p, q)
                if dist < 320:
                    d.line([p, q], fill=(*ac, int(110 * (1 - dist / 320))), width=2)
        for p in pts:
            r = rng.randint(4, 11)
            d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=(*ac, 165))
    elif cat == "SCIENCE":
        cx, cy = rng.randint(400, 680), rng.randint(760, 1180)
        for ang in (0, 60, 120):
            layer = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            ld.ellipse((40, 300, 860, 600), outline=(*ac, 150), width=4)
            ld.ellipse((410, 288, 450, 328), fill=(*ac, 230))
            layer = layer.rotate(ang + rng.randint(-8, 8))
            ov.paste(layer, (cx - 450, cy - 450), layer)
        for r, a in ((70, 60), (46, 120), (26, 230)):
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*ac, a))
    elif cat == "SPACE":
        for _ in range(260):
            x, y, r = rng.randint(0, W), rng.randint(0, H), rng.choice((1, 1, 2, 3))
            d.ellipse((x, y, x + r, y + r), fill=(255, 255, 255, rng.randint(90, 230)))
        px, py, pr = rng.randint(420, 800), rng.randint(780, 1100), rng.randint(250, 330)
        for k in range(pr, 0, -6):
            f = k / pr
            d.ellipse((px - k, py - k, px + k, py + k), fill=(int(ac[0] * (0.35 + 0.65 * (1 - f))), int(ac[1] * (0.3 + 0.5 * (1 - f))), int(ac[2] * (0.45 + 0.55 * (1 - f))), 150))
        d.ellipse((px - pr * 1.7, py - pr * 0.28, px + pr * 1.7, py + pr * 0.28), outline=(*ac, 140), width=8)
    elif cat == "HEALTH":
        cx, ph = rng.randint(400, 680), rng.uniform(0, 6)
        prev = None
        for y in range(0, H, 5):
            a = 190 * math.sin(y / 150 + ph)
            x1, x2 = cx + a, cx - a
            d.ellipse((x1 - 5, y - 5, x1 + 5, y + 5), fill=(*ac, 190))
            d.ellipse((x2 - 5, y - 5, x2 + 5, y + 5), fill=(255, 255, 255, 110))
            if y % 45 == 0:
                d.line((x1, y, x2, y), fill=(*ac, 90), width=2)
        ey = rng.randint(1250, 1450)
        pts = [(0, ey)] + [(x, ey - (int(120 * math.sin((x % 260) / 260 * math.pi * 2)) if 80 < x % 260 < 180 else 0)) for x in range(0, W, 6)]
        d.line(pts, fill=(*ac, 120), width=4)
    elif cat == "WORLD":
        cx, cy, R = rng.randint(480, 600), rng.randint(820, 1100), 430
        d.ellipse((cx - R, cy - R, cx + R, cy + R), outline=(*ac, 170), width=4)
        for lat in range(-60, 61, 30):
            y = cy + R * math.sin(math.radians(lat))
            hw = R * math.cos(math.radians(lat))
            d.ellipse((cx - hw, y - hw * 0.1, cx + hw, y + hw * 0.1), outline=(*ac, 100), width=2)
        for lon in range(15, 90, 25):
            hw = R * math.cos(math.radians(lon))
            d.ellipse((cx - hw, cy - R, cx + hw, cy + R), outline=(*ac, 85), width=2)
        for _ in range(16):
            a, r = rng.uniform(0, 6.28), rng.uniform(0, R * 0.9)
            x, y = cx + r * math.cos(a), cy + r * math.sin(a) * 0.9
            d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(*ac, 220))
    elif cat == "TECH":
        for _ in range(22):
            x, y = rng.randint(0, W), rng.randint(100, H - 100)
            pts = [(x, y)]
            for _ in range(rng.randint(3, 6)):
                step = rng.randint(90, 260)
                dx, dy = rng.choice(((1, 0), (0, 1), (1, 1), (-1, 1), (-1, 0), (0, -1)))
                x, y = x + dx * step, y + dy * step
                pts.append((x, y))
            d.line(pts, fill=(*ac, 120), width=3)
            for px, py in (pts[0], pts[-1]):
                d.ellipse((px - 9, py - 9, px + 9, py + 9), outline=(*ac, 200), width=3)
    elif cat == "ANIME":
        cx, cy = rng.randint(380, 700), rng.randint(760, 1100)
        d.ellipse((cx - 330, cy - 330, cx + 330, cy + 330), fill=(*ac, 38))
        for _ in range(110):
            a, r0 = rng.uniform(0, 6.283), rng.randint(300, 520)
            r1 = r0 + rng.randint(300, 900)
            d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
                   fill=(255, 255, 255, rng.randint(40, 120)), width=rng.randint(2, 5))
        for _ in range(26):
            x, y, s = rng.randint(0, W), rng.randint(0, H), rng.randint(10, 24)
            d.ellipse((x, y, x + s * 1.6, y + s), fill=(255, 190, 225, rng.randint(90, 190)))
    else:  # SERIES
        cx = rng.randint(440, 640)
        d.polygon([(cx - 40, -40), (cx + 40, -40), (cx + 520, H), (cx - 520, H)], fill=(*ac, 34))
        for x0 in (0, W - 96):
            d.rectangle((x0, 0, x0 + 96, H), fill=(0, 0, 0, 130))
            for y in range(24, H, 84):
                d.rounded_rectangle((x0 + 28, y, x0 + 68, y + 46), radius=8, fill=(255, 255, 255, 60))
        for _ in range(6):
            x = rng.randint(0, W)
            d.line((x, 0, x - 600, H), fill=(*ac, 36), width=rng.randint(8, 24))


def chrome(img, cat, idx, total):
    d = ImageDraw.Draw(img)
    c = CATS[cat]
    spaced(d, (64, 70), "VYROX", font(SERIF_B, 54), GOLD + (255,), gap=12)
    spaced(d, (66, 138), "D A I L Y", font(SANS_B, 20), c["accent"] + (255,), gap=2)
    d.line((64, 178, W - 64, 178), fill=GOLD + (150,), width=2)
    chip = font(SANS_B, 24)
    tw = spaced(ImageDraw.Draw(Image.new("RGB", (1, 1))), (0, 0), c["label"], chip, (0, 0, 0), gap=3)
    d.rounded_rectangle((W - 64 - tw - 40, 84, W - 64, 140), radius=28, outline=c["accent"] + (255,), width=3, fill=(0, 0, 0, 120))
    spaced(d, (W - 64 - tw - 20, 99), c["label"], chip, (255, 255, 255, 255), gap=3)
    gapx = 34
    x0 = W / 2 - (total - 1) * gapx / 2
    for i in range(total):
        r = 9 if i == idx else 6
        d.ellipse((x0 + i * gapx - r, 1560 - r, x0 + i * gapx + r, 1560 + r), fill=(GOLD + (255,)) if i == idx else (255, 255, 255, 90))


def panel(img, box, alpha=150):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=34, fill=(3, 8, 20, alpha), outline=GOLD + (170,), width=2)


def shadow_text(d, xy, text, f, fill=(255, 255, 255, 255)):
    x, y = xy
    d.text((x + 3, y + 4), text, font=f, fill=(0, 0, 0, 170))
    d.text((x, y), text, font=f, fill=fill)


def fit_lines(d, text, paths, max_w, max_h, start, minimum, spacing=1.28, max_lines=9):
    size = start
    while True:
        f = font(paths, size)
        lines = wrap(d, text, f, max_w)
        if (len(lines) * size * spacing <= max_h and len(lines) <= max_lines) or size <= minimum:
            return f, lines, size
        size -= 2


def fg_hook(cat, kicker, title, idx, total):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    chrome(img, cat, idx, total)
    ac = CATS[cat]["accent"]
    spaced(d, (W / 2, 520), kicker, font(SANS_B, 40), ac + (255,), gap=5, anchor="m")
    d.rectangle((W / 2 - 70, 590, W / 2 + 70, 598), fill=GOLD + (255,))
    f, lines, size = fit_lines(d, title.upper(), SERIF_B, W - 150, 640, 96, 54, spacing=1.22, max_lines=7)
    y = 650
    for line in lines:
        w = d.textlength(line, font=f)
        shadow_text(d, ((W - w) / 2, y), line, f, GOLD + (255,))
        y += int(size * 1.22)
    spaced(d, (W / 2, 1420), "WATCH TILL THE END", font(SANS_B, 28), GOLD + (255,), gap=6, anchor="m")
    return img


def fg_detail(cat, num, label, text, idx, total, stat=None):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    chrome(img, cat, idx, total)
    ac = CATS[cat]["accent"]
    d.text((72, 300), f"{num:02d}", font=font(SERIF_B, 170), fill=GOLD + (95,))
    spaced(d, (76, 520), label, font(SANS_B, 34), ac + (255,), gap=5)
    d.rectangle((76, 582, 196, 588), fill=GOLD + (255,))
    top = 640
    if stat:
        sf = font(SERIF_B, 190 if len(stat) <= 7 else 120)
        sw = d.textlength(stat, font=sf)
        shadow_text(d, ((W - sw) / 2, 620), stat, sf, GOLD + (255,))
        top = 880
    f, lines, size = fit_lines(d, text, SANS_B, W - 220, 600 if not stat else 430, 76 if not stat else 58, 38, spacing=1.36)
    block = int(len(lines) * size * 1.36) + 70
    if not stat:
        top = max(660, 940 - block // 2)
    panel(img, (56, top - 36, W - 56, min(1500, top - 36 + block)))
    y = top
    for line in lines:
        shadow_text(d, (96, y), line, f)
        y += int(size * 1.36)
    return img


def fg_terms(cat, terms, idx, total):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    chrome(img, cat, idx, total)
    ac = CATS[cat]["accent"]
    spaced(d, (W / 2, 470), "KEY TERMS", font(SANS_B, 38), ac + (255,), gap=6, anchor="m")
    d.rectangle((W / 2 - 60, 536, W / 2 + 60, 542), fill=GOLD + (255,))
    f = font(SANS_B, 58)
    y = 620
    for t in terms[:5]:
        t = shorten(t, 26)
        w = d.textlength(t, font=f)
        d.rounded_rectangle(((W - w) / 2 - 44, y, (W + w) / 2 + 44, y + 108), radius=54, fill=(3, 8, 20, 150), outline=ac + (255,), width=3)
        d.text(((W - w) / 2, y + 22), t, font=f, fill=(255, 255, 255, 255))
        y += 150
    return img


def fg_source(cat, source, link, credits, idx, total):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    chrome(img, cat, idx, total)
    ac = CATS[cat]["accent"]
    spaced(d, (W / 2, 520), "SOURCE", font(SANS_B, 38), ac + (255,), gap=6, anchor="m")
    d.rectangle((W / 2 - 60, 586, W / 2 + 60, 592), fill=GOLD + (255,))
    f, lines, size = fit_lines(d, source, SERIF_B, W - 200, 300, 86, 50, spacing=1.2, max_lines=3)
    y = 650
    for line in lines:
        w = d.textlength(line, font=f)
        shadow_text(d, ((W - w) / 2, y), line, f)
        y += int(size * 1.2)
    host = urlparse(link).netloc.replace("www.", "")
    spaced(d, (W / 2, y + 40), host.upper(), font(SANS_B, 30), GOLD + (255,), gap=3, anchor="m")
    f2 = font(SANS, 34)
    for i, line in enumerate(["Full story: link in the description"] + credits):
        w = d.textlength(line, font=f2)
        d.text(((W - w) / 2, y + 130 + i * 52), line, font=f2, fill=(235, 240, 250, 235))
    return img


def fg_cta(cat, idx, total):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    chrome(img, cat, idx, total)
    spaced(d, (W / 2, 640), "FOLLOW", font(SANS_B, 44), CATS[cat]["accent"] + (255,), gap=10, anchor="m")
    f = font(SERIF_B, 150)
    w = d.textlength("VYROX", font=f)
    shadow_text(d, ((W - w) / 2, 720), "VYROX", f, GOLD + (255,))
    spaced(d, (W / 2, 930), "DAILY", font(SANS_B, 64), (255, 255, 255, 255), gap=24, anchor="m")
    d.rectangle((W / 2 - 90, 1040, W / 2 + 90, 1046), fill=GOLD + (255,))
    spaced(d, (W / 2, 1100), "A NEW UPDATE EVERY DAY", font(SANS_B, 32), (235, 240, 250, 255), gap=5, anchor="m")
    return img


# --------------------------------------------------------------------------- planning
def plan_slides(story, rng):
    cat = story["category"]
    title = re.split(r"\s+[\|\u2013\u2014-]\s+", story["title"])[0]
    title = shorten(title if len(title) >= 25 else story["title"], 92)
    kicker = rng.choice(CATS[cat]["kickers"])
    pieces = []
    for s in sentences(story["summary"]):
        pieces += split_long(s)
    pieces = pieces[:5]
    if not pieces:
        pieces = ["The full details are in the original report linked in the description."]
    if len(pieces) == 1 and len(pieces[0]) > 70:
        mid = pieces[0].rfind(" ", 0, len(pieces[0]) // 2 + 15)
        pieces = [pieces[0][:mid], pieces[0][mid + 1:]]
    terms = key_terms(title + ". " + story["summary"])
    labels = ["THE UPDATE", "THE DETAILS", "KEY POINT", "WORTH KNOWING", "ALSO", "ONE MORE THING"]
    fixed = 3.4 + (5.0 if len(terms) >= 2 else 0) + 4.5 + 3.5

    def total_len(n):
        slides = 1 + n + (1 if len(terms) >= 2 else 0) + 2
        dd = min(9.0, max(4.2, (TARGET - fixed + (slides - 1) * T) / n))
        return fixed + dd * n - (slides - 1) * T

    while total_len(len(pieces)) < 31 and len(pieces) < 6:
        i = max(range(len(pieces)), key=lambda k: len(pieces[k]))
        p = pieces[i]
        if len(p) < 70:
            break
        mid = p.rfind(" ", 0, len(p) // 2 + 12)
        if mid < 20:
            break
        pieces[i:i + 1] = [p[:mid].strip(), p[mid + 1:].strip()]
    n = len(pieces)
    slides_n = 1 + n + (1 if len(terms) >= 2 else 0) + 2
    dd = min(9.0, max(4.2, (TARGET - fixed + (slides_n - 1) * T) / n))
    plan = [dict(kind="hook", dur=3.4, kicker=kicker, title=title)]
    stat_used = False
    for i, p in enumerate(pieces):
        st = None if stat_used else stat_of(p)
        stat_used = stat_used or bool(st)
        plan.append(dict(kind="detail", dur=dd, label=labels[i % len(labels)], text=p, stat=st, num=i + 1))
    if len(terms) >= 2:
        plan.append(dict(kind="terms", dur=5.0, terms=terms))
    plan.append(dict(kind="source", dur=4.5))
    plan.append(dict(kind="cta", dur=3.5))
    return plan, title


# --------------------------------------------------------------------------- video + audio
def run(cmd):
    print("+", " ".join(map(str, cmd))[:260])
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def render_segment(bg, fg, dur, idx, rng):
    seg = OUT / f"seg_{idx:02d}.mp4"
    ax, bx = rng.choice(((0, 1), (1, 0), (0.15, 0.85), (0.85, 0.15)))
    ay, by = rng.choice(((0, 1), (1, 0), (0.2, 0.9), (0.9, 0.2)))
    fx = f"(iw-ow)*({ax}+({bx}-{ax})*t/{dur:.3f})"
    fy = f"(ih-oh)*({ay}+({by}-{ay})*t/{dur:.3f})"
    fc = (f"[0:v]scale=1350:2400:flags=bicubic,crop=1080:1920:x='{fx}':y='{fy}',noise=alls=4:allf=t,format=yuv420p[b];"
          f"[1:v]format=rgba,fade=t=in:st=0.2:d=0.5:alpha=1,fade=t=out:st={max(0.6, dur - 0.45):.3f}:d=0.4:alpha=1[f];"
          f"[b][f]overlay=x=0:y='28*max(0,1-t/0.7)':format=auto,format=yuv420p[v]")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(bg),
         "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(fg),
         "-filter_complex", fc, "-map", "[v]", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "21", "-pix_fmt", "yuv420p", str(seg)])
    return seg


def combine(segs, durs, rng):
    trans = ["fade", "slideleft", "circleopen", "wipeup", "smoothleft", "fadeblack", "slideright", "dissolve"]
    cmd = ["ffmpeg", "-y"]
    for s in segs:
        cmd += ["-i", str(s)]
    parts, prev, cum, times = [], "[0:v]", durs[0], []
    for k in range(1, len(segs)):
        off = cum - k * T
        tr = "fade" if k == 1 else rng.choice(trans)
        parts.append(f"{prev}[{k}:v]xfade=transition={tr}:duration={T}:offset={off:.3f}[x{k}]")
        prev = f"[x{k}]"
        times.append(off + T / 2)
        cum += durs[k]
    total = sum(durs) - (len(segs) - 1) * T
    parts.append(f"{prev}eq=contrast=1.04:saturation=1.08,fade=t=in:st=0:d=0.25,fade=t=out:st={total - 0.45:.3f}:d=0.45,format=yuv420p[v]")
    out = OUT / "video_silent.mp4"
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-r", str(FPS), "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)]
    run(cmd)
    return out, total, times


def pick_music(cat, seed):
    exts = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    for folder in (ROOT / "input" / "music" / cat.lower(), ROOT / "input" / "music"):
        if folder.is_dir():
            files = sorted(p for p in folder.iterdir() if p.suffix.lower() in exts)
            if files:
                return files[int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(files)]
    return None


def make_audio(total, cat, seed, times):
    wav = OUT / "audio.m4a"
    music = pick_music(cat, seed)
    if music:
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(music), "-t", f"{total:.3f}",
             "-af", f"afade=t=in:d=1.2,afade=t=out:st={total - 2.5:.3f}:d=2.5,loudnorm=I=-16:TP=-1.5:LRA=11",
             "-c:a", "aac", "-b:a", "160k", str(wav)])
        return wav, f"Music: {music.name} (licensed local library)"
    minor = cat in ("AI", "SCIENCE", "SPACE", "SERIES", "ANIME", "TECH")
    root = {"AI": 110.0, "SCIENCE": 98.0, "SPACE": 87.31, "HEALTH": 130.81, "WORLD": 110.0,
            "TECH": 98.0, "ANIME": 130.81, "SERIES": 82.41}[cat]
    ratios = (1, 1.189, 1.498, 2.0) if minor else (1, 1.26, 1.498, 2.0)
    cmd = ["ffmpeg", "-y"]
    labels = []
    for i, r in enumerate(ratios):
        f = root * r
        cmd += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", f"sine=f={f:.2f}:sample_rate=44100"]
        cmd += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", f"sine=f={f * 1.004:.2f}:sample_rate=44100"]
    cmd += ["-f", "lavfi", "-t", f"{total:.2f}", "-i",
            "aevalsrc='0.9*sin(2*PI*58*mod(t,0.5))*exp(-9*mod(t,0.5))':s=44100"]
    fc = ["".join(f"[{i}:a]" for i in range(len(ratios) * 2)) + f"amix=inputs={len(ratios) * 2}:normalize=0,lowpass=f=1300,tremolo=f=0.12:d=0.4,volume=0.55[pad]"]
    kick_idx = len(ratios) * 2
    fc.append(f"[{kick_idx}:a]lowpass=f=160,volume=0.55,afade=t=in:st=0:d=2[kick]")
    mix = ["[pad]", "[kick]"]
    n_in = kick_idx + 1
    for j, tt in enumerate(times):
        cmd += ["-f", "lavfi", "-t", "0.8", "-i", "anoisesrc=d=0.8:c=pink:a=0.6:r=44100"]
        ms = max(0, int((tt - 0.35) * 1000))
        fc.append(f"[{n_in}:a]highpass=f=700,lowpass=f=7000,afade=t=in:d=0.38,afade=t=out:st=0.38:d=0.4,volume=0.45,adelay={ms}|{ms}[w{j}]")
        mix.append(f"[w{j}]")
        n_in += 1
    fc.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=longest,atrim=0:{total:.3f},"
              f"afade=t=in:d=0.6,afade=t=out:st={total - 1.8:.3f}:d=1.8,alimiter=limit=0.9,loudnorm=I=-17:TP=-1.5:LRA=9[a]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[a]", "-c:a", "aac", "-b:a", "160k", str(wav)]
    run(cmd)
    return wav, "Music: generated ambient bed (no downloaded song)"


# --------------------------------------------------------------------------- main
def build(story, publish):
    cat = story["category"]
    seed = norm_key(story["title"])
    rng = random.Random(seed)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    plan, short_title = plan_slides(story, rng)
    total_slides = len(plan)
    segs, durs = [], []
    for i, s in enumerate(plan):
        bg = OUT / f"bg_{i:02d}.png"
        fg = OUT / f"fg_{i:02d}.png"
        make_bg(cat, seed, i).save(bg)
        if s["kind"] == "hook":
            img = fg_hook(cat, s["kicker"], s["title"], i, total_slides)
        elif s["kind"] == "detail":
            img = fg_detail(cat, s["num"], s["label"], s["text"], i, total_slides, s["stat"])
        elif s["kind"] == "terms":
            img = fg_terms(cat, s["terms"], i, total_slides)
        elif s["kind"] == "source":
            img = fg_source(cat, story["source"], story["link"], ["Visuals: original VYROX DAILY graphics"], i, total_slides)
        else:
            img = fg_cta(cat, i, total_slides)
        img.save(fg)
        segs.append(render_segment(bg, fg, s["dur"], i, rng))
        durs.append(s["dur"])
    silent, total, times = combine(segs, durs, rng)
    audio, music_credit = make_audio(total, cat, seed, times)
    video = OUT / "vyrox_daily_short.mp4"
    run(["ffmpeg", "-y", "-i", str(silent), "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(video)])
    shutil.copy(OUT / "fg_00.png", OUT / "preview_hook_overlay.png")
    for p in OUT.glob("seg_*.mp4"):
        p.unlink()
    for p in (OUT / "video_silent.mp4",):
        p.unlink(missing_ok=True)

    title = shorten(short_title, 78) + " | VYROX DAILY #Shorts"
    description = (f"{CATS[cat]['label']} from {story['source']}.\n\n{shorten(story['summary'], 600) if story['summary'] else short_title}\n\n"
                   f"Original source (read the full story): {story['link']}\n\n"
                   f"Visuals: original VYROX DAILY graphics (no third-party photos).\n{music_credit}\n"
                   f"Facts come from the source above; this Short is a quick summary.\n\n{CATS[cat]['tags']}")
    meta = {"title": title, "description": description, "source": story["link"], "category": cat,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "video": str(video),
            "duration_seconds": round(total, 1), "slides": total_slides, "music": music_credit}
    (OUT / "upload_metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"DRAFT_READY: {video} ({total:.1f}s, {total_slides} slides, {cat})")
    return video, title, description, meta


def upload(video, title, description, story):
    if os.getenv("GITHUB_ACTIONS") == "true":
        import base64
        creds = ROOT / "credentials"
        creds.mkdir(exist_ok=True)
        for secret, target in [("YOUTUBE_CLIENT_SECRET_B64", creds / "client_secret.json"), ("YOUTUBE_TOKEN_B64", creds / "token.json")]:
            value = os.getenv(secret, "").strip()
            if not value:
                raise RuntimeError(f"Missing GitHub Actions secret: {secret}")
            target.write_bytes(base64.b64decode(value, validate=True))
            target.chmod(0o600)
    sys.path.insert(0, str(ROOT))
    from uploaders.youtube import upload_video
    privacy = os.getenv("VYROX_PRIVACY", "private").strip().lower()
    if privacy not in ("private", "unlisted", "public"):
        privacy = "private"
    vid = upload_video(str(video), title, description,
                       tags=["VYROX DAILY", story["category"], "Shorts", "News"], privacy=privacy)
    print(f"YOUTUBE_UPLOAD_SUCCESS ({privacy}): https://youtube.com/shorts/{vid}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--category", choices=sorted(CATS))
    ap.add_argument("--demo", nargs="?", const="AI", choices=sorted(CATS), help="offline sample, no feeds, no state")
    args = ap.parse_args()
    if args.demo:
        t, s, src = DEMO[args.demo]
        story = {"category": args.demo, "source": src, "title": t, "link": "https://example.com/demo",
                 "summary": s, "published": "", "trust": "official"}
        build(story, False)
        print("DEMO_ONLY: nothing recorded, nothing uploaded.")
        return
    story = pick_story(args.category)
    print(f"STORY: [{story['category']}] {story['title']} ({story['source']})")
    video, title, description, meta = build(story, args.publish)
    links, keys = load_state()
    links.add(story["link"])
    keys.add(norm_key(story["title"]))
    save_state(links, keys)
    if args.publish:
        upload(video, title, description, story)
    else:
        print("DRAFT_ONLY: no upload attempted.")


if __name__ == "__main__":
    main()