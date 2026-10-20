#!/usr/bin/env python3
"""VYROX DAILY - image-led, no-voice Shorts with original luxury visuals and sourced facts.

What changed vs the first version
  * a new story every run (category rotation + dedupe that also counts drafts)
  * 7-9 slides per Short instead of one static photo: hook, details, key terms, source, follow
  * real source photos when a suitable Wikimedia Commons or NASA image is available; original graphics remain the fallback
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
from urllib.parse import quote, urlparse

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

# VYROX GEN X focuses on fresh AI, science and anime updates.
ROTATION = ["AI", "SCIENCE", "ANIME", "AI", "ANIME", "SCIENCE"]

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
    "SPORTS": dict(top=(6, 18, 38), bot=(12, 70, 125), accent=(80, 220, 170), label="SPORTS",
                   tags="#Sports #SportsNews #Football #Cricket #Shorts",
                   kickers=["THE SPORTS STORY EVERYONE NEEDS", "HERE IS THE BIG SPORTS UPDATE", "THIS RESULT MATTERS"],
                   feeds=[("ESPN", "https://www.espn.com/espn/rss/news", "press"),
                          ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml", "press")]),
    "INDIA": dict(top=(24, 12, 7), bot=(120, 48, 18), accent=(255, 190, 70), label="INDIA",
                  tags="#IndiaNews #India #News #Shorts",
                  kickers=["IMPORTANT INDIA UPDATE", "HERE IS WHAT CHANGED", "THE INDIA STORY TO KNOW"],
                  feeds=[("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss", "press"),
                         ("PIB India", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "official")]),
    "BUSINESS": dict(top=(8, 20, 28), bot=(16, 84, 74), accent=(120, 240, 190), label="BUSINESS",
                     tags="#Business #Markets #Economy #Shorts",
                     kickers=["THE BUSINESS UPDATE", "WHY THIS MATTERS", "A BIG ECONOMIC SHIFT"],
                     feeds=[("Reuters Business", "https://feeds.reuters.com/reuters/businessNews", "press"),
                            ("World Bank News", "https://www.worldbank.org/en/news/all?format=rss", "official")]),
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
    "ANIMALS": dict(top=(5, 22, 12), bot=(18, 92, 44), accent=(160, 255, 120), label="ANIMAL WORLD",
                    tags="#Animals #Wildlife #Nature #Shorts",
                    kickers=["WILDLIFE UPDATE", "NATURE IS WILD", "ANIMAL FACT YOU NEED TO SEE"],
                    feeds=[("ScienceDaily Animals & Plants", "https://www.sciencedaily.com/rss/plants_animals.xml", "press")]),
    "MYSTERIES": dict(top=(14, 8, 26), bot=(54, 24, 92), accent=(205, 165, 255), label="MYSTERIES",
                      tags="#Mystery #Unexplained #History #Shorts",
                      kickers=["A CLUE WORTH A LOOK", "THE DETAIL CHANGES THINGS", "WHAT DOES THE EVIDENCE SAY?"],
                      feeds=[("Smithsonian Magazine", "https://www.smithsonianmag.com/rss/latest_articles/", "press"),
                             ("ScienceDaily", "https://www.sciencedaily.com/rss/top/science.xml", "press")]),
    "FACTS": dict(top=(18, 14, 4), bot=(92, 54, 14), accent=(255, 210, 95), label="SURPRISING FACTS",
                  tags="#Facts #DidYouKnow #Discovery #Shorts",
                  kickers=["THE FACT BEHIND THE STORY", "LOOK CLOSER", "WHAT THE SOURCE FOUND"],
                  feeds=[("ScienceDaily", "https://www.sciencedaily.com/rss/top/science.xml", "press"),
                         ("NASA", "https://www.nasa.gov/feed/", "official")]),
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


def published_timestamp(raw):
    """Parse common RSS/Atom publication dates into an aware UTC datetime."""
    raw = str(raw or "").strip()
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def is_fresh_story(item, now=None, max_age_days=14):
    """Reject undated/stale RSS items rather than disguising them as current."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    published = published_timestamp(item.get("published", ""))
    if published is None:
        return False
    age_days = (now.astimezone(timezone.utc) - published).total_seconds() / 86400
    return -1.0 <= age_days <= max_age_days


def story_interest_score(item):
    """Rank curiosity-led headlines without inventing popularity or trend metrics."""
    title = clean(item.get("title", "")).lower()
    summary = clean(item.get("summary", "")).lower()
    score = 0.0
    title_signals = (
        "mystery", "mysterious", "unexplained", "rare", "hidden", "discovery",
        "reveals", "revealed", "found", "first ever", "ancient", "black hole",
        "exoplanet", "deep sea", "new species", "breakthrough", "strange",
        "surprising", "evidence", "asteroid", "moon", "mars", "ocean", "why",
        "how", "scientists discover", "researchers find"
    )
    for phrase in title_signals:
        if phrase in title:
            score += 2.5
        elif phrase in summary:
            score += 0.7
    words = title.split()
    if 6 <= len(words) <= 15:
        score += 1.5
    if "?" in str(item.get("title", "")):
        score += 0.8
    category = str(item.get("category", "")).upper()
    if category in {"MYSTERIES", "FACTS", "SPACE", "SCIENCE", "ANIMALS"}:
        score += 1.0
    return score


def pick_story(forced=None):
    links, keys = load_state()
    now = datetime.now(timezone.utc)
    slot = 0 if now.hour < 11 else 1
    start = (now.date().toordinal() * 2 + slot) % len(ROTATION)
    order = [forced] if forced else [ROTATION[(start + k) % len(ROTATION)] for k in range(len(ROTATION))]
    for cat in order:
        rows = []
        for source, url, trust in CATS[cat]["feeds"]:
            rows += parse_feed(cat, source, url, trust)
        fresh = []
        for item in rows:
            if item["link"] in links or norm_key(item["title"]) in keys:
                continue
            if not is_fresh_story(item, now=now, max_age_days=14):
                continue
            published = published_timestamp(item.get("published", ""))
            age_days = max(0.0, (now - published).total_seconds() / 86400)
            item["_published_ts"] = published.timestamp()
            item["_freshness_score"] = max(0.0, 14.0 - age_days) * 0.12
            item["_interest_score"] = story_interest_score(item)
            fresh.append(item)
        if fresh:
            fresh.sort(
                key=lambda item: (item["_interest_score"] + item["_freshness_score"], item["_published_ts"]),
                reverse=True,
            )
            chosen = fresh[0]
            print(
                f"STORY_SELECTION: category={cat}; age_days="
                f"{max(0.0, (now.timestamp() - chosen['_published_ts']) / 86400):.1f}; "
                f"interest_score={chosen['_interest_score']:.1f}; source={chosen['source']}"
            )
            return chosen
        print(f"No unseen, dated story within 14 days in {cat}; trying next category.")
    raise RuntimeError(
        "No unseen, dated story within the last 14 days was found in the configured feeds. "
        "Skipping rather than posting stale or undated content."
    )


# --------------------------------------------------------------------------- sourced real photos
def fetch_story_photo(story):
    """Find real, reusable images relevant to the story; never substitute abstract art."""
    OUT.mkdir(parents=True, exist_ok=True)
    title = re.sub(r"[^A-Za-z0-9 ]", " ", story.get("title", ""))[:100].strip()
    cat = story.get("category", "")
    category_queries = {
        "SPACE": ["NASA deep space nebula galaxy", "NASA Sun solar surface", "NASA Moon lunar surface"],
        "SCIENCE": ["scientific research laboratory", "scientists laboratory experiment"],
        "AI": ["robot artificial intelligence technology"],
        "HEALTH": ["public health medical research hospital"],
        "SPORTS": ["football match sports stadium athlete", "cricket match stadium"],
        "INDIA": ["India city public infrastructure people"],
        "BUSINESS": ["global business economy finance"],
        "WORLD": ["world landmarks environment people"],
        "TECH": ["smartphone technology electronics"],
        "HISTORY": ["historical artefact museum", "historical building archive"],
        "ANIMALS": ["wild animals wildlife nature"],
        "FUNNY": ["funny animal", "humorous situation"],
        "ANIME": ["anime illustration"], 
    }
    queries = [title] + category_queries.get(cat, [])
    candidates, seen_urls = [], set()
    # Search Wikimedia Commons with the story title first, then relevant topic terms.
    for query in queries:
        try:
            params = {
                "action": "query", "format": "json", "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": 6, "gsrlimit": 8,
                "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1600,
            }
            r = requests.get("https://commons.wikimedia.org/w/api.php", params=params,
                             headers={**HEADERS, "User-Agent": "VYROXDaily/1.0 (shorts project)"},
                             timeout=18)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                info = (page.get("imageinfo") or [{}])[0]
                url = info.get("thumburl") or info.get("url", "")
                meta = info.get("extmetadata", {})
                license_name = clean(meta.get("LicenseShortName", {}).get("value", ""))
                artist = clean(meta.get("Artist", {}).get("value", ""))
                if (url.startswith("https://") and url not in seen_urls and license_name
                        and license_name.lower() not in {"fair use", "copyrighted"}):
                    seen_urls.add(url)
                    page_title = str(page.get("title", "image"))
                    asset_page = "https://commons.wikimedia.org/wiki/" + quote(page_title.replace(" ", "_"), safe=":/()")
                    candidates.append((url, f"Wikimedia Commons: {page_title}; asset page: {asset_page}; creator: {artist or 'see asset page'}; license: {license_name}; illustrative context image, not necessarily the exact event photo"))
            if len(candidates) >= 5:
                break
        except Exception as exc:
            print(f"Wikimedia lookup unavailable ({query}): {exc}")
    # NASA image library is especially useful for space stories; NASA imagery is public-domain in many cases,
    # but item-specific credit and restrictions must still be checked.
    if cat == "SPACE" and len(candidates) < 2:
        for query in [title, "deep space galaxy nebula NASA", "Sun solar surface NASA", "Moon lunar surface NASA"]:
            try:
                nr = requests.get("https://images-api.nasa.gov/search",
                                  params={"q": query, "media_type": "image", "page_size": 10},
                                  headers=HEADERS, timeout=18)
                nr.raise_for_status()
                for item in nr.json().get("collection", {}).get("items", []):
                    data = (item.get("data") or [{}])[0]
                    links = item.get("links") or []
                    url = next((x.get("href", "") for x in links if x.get("render") == "image"), "")
                    if url.startswith("https://") and url not in seen_urls and data.get("nasa_id"):
                        seen_urls.add(url)
                        candidates.append((url, f"NASA Image and Video Library: {data.get('title','NASA image')} (NASA ID {data['nasa_id']}; verify item-specific credit)"))
            except Exception as exc:
                print(f"NASA lookup unavailable ({query}): {exc}")
            if len(candidates) >= 8:
                break
    downloaded = []
    from io import BytesIO
    for url, credit in candidates:
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("image/") or len(r.content) < 5000:
                continue
            im = Image.open(BytesIO(r.content))
            im.verify()
            path = OUT / f"source_photo_{len(downloaded):02d}.jpg"
            path.write_bytes(r.content)
            downloaded.append((path, credit))
            print(f"Using real source image: {credit}")
            if len(downloaded) >= 1:
                break
        except Exception:
            continue
    if downloaded:
        return [item[0] for item in downloaded], "; ".join(item[1] for item in downloaded)
    print("No reusable source photo found; refusing to render a substitute.")
    return [], "No reusable source photo found"


# --------------------------------------------------------------------------- visuals
def make_bg(cat, seed, variant, photo_path=None):
    c = CATS[cat]
    rng = random.Random(f"{seed}-{variant}")
    top, bot, ac = c["top"], c["bot"], c["accent"]
    photo_list = list(photo_path) if isinstance(photo_path, (list, tuple)) else ([photo_path] if photo_path else [])
    photo_list = [Path(p) for p in photo_list if p and Path(p).exists()]

    def crop_cover(path, size):
        photo = Image.open(path).convert("RGB")
        sw, sh = size
        scale = max(sw / photo.width, sh / photo.height)
        nw, nh = int(photo.width * scale), int(photo.height * scale)
        photo = photo.resize((nw, nh), Image.Resampling.LANCZOS)
        left, topy = max(0, (nw - sw) // 2), max(0, (nh - sh) // 2)
        return photo.crop((left, topy, left + sw, topy + sh))

    # Funny/anime meme-style shorts use four distinct sourced images in a 2x2 grid.
    # The images remain separate panels; captions/branding are composited above them.
    if cat in {"FUNNY", "ANIME"} and len(photo_list) >= 4:
        cell_w, cell_h, gutter = (W - 3 * 18) // 2, (H - 3 * 18) // 2, 18
        img = Image.new("RGB", (W, H), (0, 0, 0))
        chosen = [photo_list[(variant + j) % len(photo_list)] for j in range(4)]
        for j, path in enumerate(chosen):
            x, y = gutter + (j % 2) * (cell_w + gutter), gutter + (j // 2) * (cell_h + gutter)
            img.paste(crop_cover(path, (cell_w, cell_h)), (x, y))
        img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.18)
    elif photo_list:
        # Cycle through distinct real photos across scenes and use varied crops.
        path = photo_list[variant % len(photo_list)]
        photo = Image.open(path).convert("RGB")
        target_ratio = W / H
        pw, ph = photo.size
        crop_h = ph
        crop_w = min(pw, int(crop_h * target_ratio))
        if crop_w > pw:
            crop_w, crop_h = pw, int(pw / target_ratio)
        max_x, max_y = max(0, pw - crop_w), max(0, ph - crop_h)
        x = int(max_x * ((variant % 5) / 4)) if max_x else 0
        y = int(max_y * ((variant % 3) / 2)) if max_y else 0
        img = photo.crop((x, y, x + crop_w, y + crop_h)).resize((W, H), Image.Resampling.LANCZOS)
        img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.28)
    else:
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
    ov = Image.merge("RGBA", (r_, g_, b_, a_.point(lambda v: min(255, int(v * 0.45)))))
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
    elif cat == "MYSTERIES":
        cx, cy = rng.randint(430, 650), rng.randint(760, 1120)
        for r, alpha in ((360, 42), (270, 70), (180, 95), (90, 135)):
            d.ellipse((cx-r, cy-r, cx+r, cy+r), outline=(*ac, alpha), width=5)
        for _ in range(24):
            x, y = rng.randint(50, W-50), rng.randint(220, H-220)
            d.ellipse((x-3, y-3, x+3, y+3), fill=(255, 255, 255, rng.randint(80, 180)))
    elif cat == "FACTS":
        pts = [(x, rng.randint(700, 1250) + int(65 * math.sin(x / 90))) for x in range(-40, W+80, 70)]
        d.line(pts, fill=(*ac, 115), width=5)
        for x, y in pts:
            d.ellipse((x-8, y-8, x+8, y+8), fill=(*ac, 190))
        for x in range(80, W, 160):
            d.line((x, 300, x, H-260), fill=(*ac, 28), width=2)
    else:  # SERIES-style fallback
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
    spaced(d, (64, 70), "VYROX-2008", font(SERIF_B, 46), GOLD + (255,), gap=12)
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
    hook_line = {"ANIMALS": "DID YOU KNOW THIS ANIMAL?", "SCIENCE": "A DISCOVERY THAT CHANGES PERSPECTIVE", "SPACE": "WHAT IS OUT THERE?", "AI": "THE NEXT BIG AI BREAKTHROUGH?", "TECH": "THE FUTURE IS HERE", "WORLD": "HERE IS WHY IT MATTERS", "INDIA": "THE DETAIL YOU SHOULD KNOW", "BUSINESS": "WHY THIS MATTERS", "SPORTS": "THE MOMENT TO WATCH", "HEALTH": "WHAT THE EVIDENCE SAYS"}.get(cat, "DID YOU KNOW THIS?")
    spaced(d, (W / 2, 500), hook_line, font(SANS_B, 30), GOLD + (255,), gap=4, anchor="m")
    spaced(d, (W / 2, 550), kicker, font(SANS_B, 30), ac + (255,), gap=5, anchor="m")
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


def add_lower_subtitle(img, text):
    """Render a restrained, premium gold/silver lower-third subtitle."""
    text = shorten(clean(text), 100)
    if not text:
        return img
    d = ImageDraw.Draw(img, "RGBA")
    max_w = W - 150
    f, lines, size = fit_lines(d, text, SANS_B, max_w - 48, 150, 38, 28, spacing=1.2, max_lines=3)
    line_h = int(size * 1.2)
    box_h = len(lines) * line_h + 38
    y0 = 1430
    d.rounded_rectangle((64, y0, W - 64, y0 + box_h), radius=22,
                        fill=(4, 8, 16, 205), outline=GOLD + (220,), width=2)
    y = y0 + 18
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=f)
        x = (W - tw) / 2
        d.text((x + 2, y + 2), line, font=f, fill=(0, 0, 0, 220))
        color = GOLD + (255,) if i == 0 else (225, 230, 238, 255)
        d.text((x, y), line, font=f, fill=color)
        y += line_h
    return img


def fg_cta(cat, idx, total):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    chrome(img, cat, idx, total)
    spaced(d, (W / 2, 640), "SUBSCRIBE", font(SANS_B, 44), CATS[cat]["accent"] + (255,), gap=10, anchor="m")
    f = font(SERIF_B, 150)
    w = d.textlength("VYROX", font=f)
    shadow_text(d, ((W - w) / 2, 720), "VYROX", f, GOLD + (255,))
    spaced(d, (W / 2, 930), "DAILY", font(SANS_B, 64), (255, 255, 255, 255), gap=24, anchor="m")
    d.rectangle((W / 2 - 90, 1040, W / 2 + 90, 1046), fill=GOLD + (255,))
    spaced(d, (W / 2, 1100), "SUBSCRIBE FOR DAILY UPDATES", font(SANS_B, 30), (235, 240, 250, 255), gap=5, anchor="m")
    spaced(d, (W / 2, 1190), "VYROX-2008", font(SANS_B, 28), GOLD + (255,), gap=4, anchor="m")
    return img


def make_hook(story):
    """Create a story-specific spoken opener without unsupported sensational claims."""
    cat = str(story.get("category", "WORLD")).upper()
    title = clean(story.get("title", "")).rstrip(" .!?")
    templates = {
        "SPACE": "Here's the space detail worth a closer look: {title}.",
        "MYSTERIES": "There's a curious detail in this story: {title}.",
        "FACTS": "This finding deserves a closer look: {title}.",
        "SCIENCE": "Researchers have reported something worth checking: {title}.",
        "ANIMALS": "Nature has a story worth a closer look: {title}.",
        "AI": "Here's the AI detail that matters in this story: {title}.",
        "TECH": "Here's the technology detail worth knowing: {title}.",
        "HISTORY": "This piece of history has a detail worth knowing: {title}.",
        "HEALTH": "Here's what the health report actually says: {title}.",
    }
    return templates.get(cat, "Here's the key detail behind this story: {title}.").format(title=title)


def hook_kicker(story):
    """Short visual hook label; the actual story headline remains the main focal point."""
    cat = str(story.get("category", "WORLD")).upper()
    labels = {
        "SPACE": "LOOK BEYOND EARTH",
        "MYSTERIES": "FOLLOW THE CLUES",
        "FACTS": "THE FACTS, CLEARLY",
        "SCIENCE": "WHAT THE EVIDENCE SAYS",
        "ANIMALS": "NATURE'S SURPRISE",
        "AI": "THE AI DETAIL",
        "TECH": "THE TECH DETAIL",
        "HISTORY": "A DETAIL FROM HISTORY",
        "HEALTH": "CHECK THE EVIDENCE",
    }
    return labels.get(cat, "THE DETAIL THAT MATTERS")


# --------------------------------------------------------------------------- planning
def plan_slides(story, rng):
    cat = story["category"]
    title = re.split(r"\s+[\|\u2013\u2014-]\s+", story["title"])[0]
    title = shorten(title if len(title) >= 25 else story["title"], 92)
    kicker = hook_kicker(story)
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
    """Pick a properly licensed local track by topic/mood; never scrape copyrighted chart songs."""
    exts = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    mood = {
        "AI": "tech", "TECH": "tech", "SCIENCE": "cinematic",
        "SPACE": "ambient", "HEALTH": "calm", "WORLD": "news",
        "HISTORY": "cinematic", "ANIME": "anime", "FUNNY": "funny", "ANIMALS": "nature",
    }.get(cat, "cinematic")
    for folder in (ROOT / "input" / "music" / cat.lower(),
                   ROOT / "input" / "music" / mood,
                   ROOT / "input" / "music"):
        if folder.is_dir():
            files = sorted(p for p in folder.iterdir() if p.suffix.lower() in exts)
            if files:
                return files[int(hashlib.sha1(seed.encode()).hexdigest(), 16) % len(files)]
    return None


def make_voiceover(story):
    """Generate a natural Indian-English narration with a story-specific opening."""
    summary = clean(story.get("summary", ""))
    hook = make_hook(story)
    body_sentences = sentences(summary)[:3]
    body = " ".join(body_sentences)
    if len(body.split()) < 8:
        raise RuntimeError("Voiceover QA failed: source summary has too little usable detail.")
    spoken = f"{hook} {body} The original source is linked in the description. Follow VYROX GEN X for more."
    spoken = shorten(spoken, 430)
    if len(spoken.split()) < 12:
        raise RuntimeError("Voiceover QA failed: narration is too short to tell a complete mini-story.")
    voice_path = OUT / "voiceover.mp3"
    voice_name = os.getenv("VYROX_TTS_VOICE", "en-IN-PrabhatNeural").strip() or "en-IN-PrabhatNeural"
    cmd = [
        "edge-tts", "--voice", voice_name, "--rate=-3%",
        "--text", spoken, "--write-media", str(voice_path)
    ]
    try:
        run(cmd)
    except Exception as exc:
        raise RuntimeError(f"Professional voiceover generation failed; refusing silent/music-only draft: {exc}") from exc
    if not voice_path.is_file() or voice_path.stat().st_size < 10000:
        raise RuntimeError("Voiceover QA failed: generated narration file is missing or too small.")
    print(f"VOICEOVER_READY: {voice_name} ({len(spoken.split())} words)")
    return voice_path, spoken


def mix_voice_and_music(bed_path, voice_path, total):
    """Mix clear narration over a quiet music bed using broadly supported FFmpeg filters."""
    mixed = OUT / "final_audio.m4a"
    # Keep the voice and music on separate inputs, normalize the narration, and mix
    # with a conservative music level. Avoid sidechaincompress because FFmpeg builds
    # differ in how they negotiate short voice tracks and this previously failed CI.
    filter_complex = (
        "[0:a]aresample=44100,volume=0.16[music];"
        "[1:a]aresample=44100,highpass=f=80,lowpass=f=12000,"
        "loudnorm=I=-16:TP=-1.5:LRA=7,volume=1.0[voice];"
        "[music][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"atrim=0:{total:.3f},afade=t=in:st=0:d=0.25,"
        f"afade=t=out:st={max(0.1,total-1.0):.3f}:d=0.8,"
        "alimiter=limit=0.95[a]"
    )
    run(["ffmpeg", "-y", "-i", str(bed_path), "-i", str(voice_path),
         "-filter_complex", filter_complex, "-map", "[a]", "-t", f"{total:.3f}",
         "-c:a", "aac", "-b:a", "192k", str(mixed)])
    return mixed


def media_quality_report(video_path, expected_duration, voice_path):
    """Fail closed unless the final vertical video, audio level and narration pass QA."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,sample_rate,r_frame_rate", "-show_entries", "format=duration,size",
         "-of", "json", str(video_path)], capture_output=True, text=True
    )
    if probe.returncode:
        raise RuntimeError("Media QA failed: ffprobe could not inspect the rendered video.")
    info = json.loads(probe.stdout or "{}")
    streams = info.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video_stream or video_stream.get("width") != W or video_stream.get("height") != H:
        raise RuntimeError("Media QA failed: expected 1080x1920 vertical video stream is missing.")
    if not audio_stream:
        raise RuntimeError("Media QA failed: final audio stream is missing.")
    duration = float((info.get("format") or {}).get("duration") or 0)
    file_size = int((info.get("format") or {}).get("size") or 0)
    if duration < 8 or abs(duration - expected_duration) > 2.0:
        raise RuntimeError(f"Media QA failed: unexpected duration {duration:.2f}s.")
    if file_size < 250000:
        raise RuntimeError(f"Media QA failed: final MP4 is unexpectedly small ({file_size} bytes).")
    if not voice_path.is_file() or voice_path.stat().st_size < 10000:
        raise RuntimeError("Media QA failed: professional voiceover is absent or incomplete.")
    voice_probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(voice_path)],
        capture_output=True, text=True
    )
    if voice_probe.returncode:
        raise RuntimeError("Media QA failed: voiceover duration could not be inspected.")
    voice_duration = float((voice_probe.stdout or "0").strip() or 0)
    if voice_duration < 4.0 or voice_duration > duration + 1.0:
        raise RuntimeError(
            f"Media QA failed: voiceover duration {voice_duration:.2f}s is implausible for a {duration:.2f}s Short."
        )
    vol = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video_path), "-vn", "-af", "volumedetect",
         "-f", "null", "-"], capture_output=True, text=True
    )
    audio_log = (vol.stderr or "")[-12000:]
    mean_match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", audio_log)
    peak_match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", audio_log)
    if vol.returncode or not mean_match or not peak_match:
        raise RuntimeError("Media QA failed: could not measure final audio loudness and peak.")
    mean_db = float(mean_match.group(1))
    peak_db = float(peak_match.group(1))
    if mean_db < -35.0:
        raise RuntimeError(f"Media QA failed: final audio is too quiet (mean {mean_db:.1f} dB).")
    if peak_db > -0.1:
        raise RuntimeError(f"Media QA failed: audio peak risks clipping ({peak_db:.1f} dBFS).")
    report = {
        "passed": True, "video_width": W, "video_height": H,
        "duration_seconds": round(duration, 2), "file_size_bytes": file_size,
        "audio_stream_present": True, "voiceover_present": True,
        "voiceover_duration_seconds": round(voice_duration, 2),
        "mean_audio_db": round(mean_db, 2), "peak_audio_dbfs": round(peak_db, 2),
    }
    print(f"MEDIA_QA_PASS: {json.dumps(report)}")
    return report


def make_audio(total, cat, seed, times):
    wav = OUT / "audio.m4a"
    music = pick_music(cat, seed)
    if music:
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(music), "-t", f"{total:.3f}",
             "-af", f"afade=t=in:d=1.2,afade=t=out:st={total - 2.5:.3f}:d=2.5,loudnorm=I=-16:TP=-1.5:LRA=11",
             "-c:a", "aac", "-b:a", "160k", str(wav)])
        return wav, f"Music: {music.name} (licensed local library)"
    minor = cat in ("AI", "SCIENCE", "SPACE", "SERIES", "ANIME", "TECH", "MYSTERIES", "FACTS")
    root = {"AI": 110.0, "SCIENCE": 98.0, "SPACE": 87.31, "HEALTH": 130.81, "WORLD": 110.0,
            "TECH": 98.0, "ANIME": 130.81, "SERIES": 82.41, "SPORTS": 146.83, "INDIA": 110.0,
            "BUSINESS": 98.0, "MYSTERIES": 82.41, "FACTS": 110.0}.get(cat, 110.0)
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
    photo_path, photo_credit = fetch_story_photo(story)
    if not photo_path:
        # Original designed graphics are the fallback, never a fake photograph.
        photo_credit = "Original VYROX GEN X visual; generated in-project with procedural graphics; no external image asset used"
        print("VISUAL_FALLBACK: generating original VYROX GEN X artwork (no external photo found).")
    if cat in {"FUNNY", "ANIME"} and len(photo_path) < 4:
        print(f"NOTE: {cat} has only {len(photo_path)} reusable image(s); 4-panel collage needs 4.")
    segs, durs = [], []
    for i, s in enumerate(plan):
        bg = OUT / f"bg_{i:02d}.png"
        fg = OUT / f"fg_{i:02d}.png"
        make_bg(cat, seed, i, photo_path).save(bg)
        if s["kind"] == "hook":
            img = fg_hook(cat, s["kicker"], s["title"], i, total_slides)
        elif s["kind"] == "detail":
            img = fg_detail(cat, s["num"], s["label"], s["text"], i, total_slides, s["stat"])
        elif s["kind"] == "terms":
            img = fg_terms(cat, s["terms"], i, total_slides)
        elif s["kind"] == "source":
            img = fg_source(cat, story["source"], story["link"], [photo_credit], i, total_slides)
        else:
            img = fg_cta(cat, i, total_slides)
        # Captions stay in a consistent lower-third safe area, never in the centre.
        if s["kind"] == "detail":
            img = add_lower_subtitle(img, s["text"])
        elif s["kind"] == "hook":
            summary_lines = sentences(story.get("summary", ""))
            context_line = shorten(summary_lines[0], 100) if summary_lines else "Source and supporting details are linked in the description."
            img = add_lower_subtitle(img, context_line)
        img.save(fg)
        segs.append(render_segment(bg, fg, s["dur"], i, rng))
        durs.append(s["dur"])
    silent, total, times = combine(segs, durs, rng)
    bed_audio, music_credit = make_audio(total, cat, seed, times)
    voice_path, spoken_text = make_voiceover(story)
    final_audio = mix_voice_and_music(bed_audio, voice_path, total)
    video = OUT / "vyrox_daily_short.mp4"
    run(["ffmpeg", "-y", "-i", str(silent), "-i", str(final_audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(video)])
    quality_report = media_quality_report(video, total, voice_path)
    source_url_ok = str(story.get("link", "")).startswith("https://")
    if not source_url_ok:
        raise RuntimeError("Source QA failed: source URL must use HTTPS.")
    is_original_visual = "original vyrox gen x visual" in photo_credit.lower()
    license_match = re.search(r"license:\\s*([^;]+)", photo_credit, flags=re.IGNORECASE)
    license_name = license_match.group(1).strip() if license_match else ("Original in-project visual" if is_original_visual else "")
    license_normalized = license_name.lower()
    recognized_reuse_license = is_original_visual or any(token in license_normalized for token in (
        "cc0", "cc by", "cc-by", "cc by-sa", "cc-by-sa", "public domain", "pdm"
    ))
    rights_report = {
        "source_url_https": source_url_ok,
        "photo_credit_present": bool(photo_credit and ("creator:" in photo_credit.lower() or is_original_visual)),
        "photo_license_name": license_name or "not extracted",
        "recognized_reuse_license": recognized_reuse_license,
        "human_review_required": True,
        "note": "A recognizable license is a screening signal, not a substitute for checking the exact asset page and license terms."
    }
    try:
        from viral_tracker import score_candidate, trend_index
        tracker_path = ROOT / "state" / "viral_tracker.json"
        tracker = json.loads(tracker_path.read_text(encoding="utf-8")) if tracker_path.exists() else {}
        score_item = {
            "id": norm_key(story["title"]), "title": story["title"],
            "description": story.get("summary", ""), "category": story.get("category", "WORLD").lower(),
            "published_at": story.get("published", ""), "created_at": int(time.time()),
            "tags": CATS[cat]["tags"].split(),
        }
        viral_score, score_breakdown = score_candidate(score_item, trend_index(), tracker)
    except Exception as exc:
        raise RuntimeError(f"Viral scoring failed; draft cannot be approved without a measured score: {exc}") from exc
    score_threshold = 75.0
    approval_status = (
        "pending_human_review"
        if quality_report["passed"] and viral_score >= score_threshold and recognized_reuse_license
        else "rejected_by_pre_publish_gate"
    )
    if not recognized_reuse_license:
        print(f"RIGHTS_GATE_FAIL: photo license was not confidently recognized ({license_name or 'missing'}); review only, do not upload.")
    if viral_score < score_threshold:
        print(f"PRE_PUBLISH_GATE_FAIL: viral_score={viral_score:.2f} required={score_threshold:.2f}; review only, do not upload.")
    shutil.copy(OUT / "fg_00.png", OUT / "preview_hook_overlay.png")
    for p in OUT.glob("seg_*.mp4"):
        p.unlink()
    for p in (OUT / "video_silent.mp4",):
        p.unlink(missing_ok=True)

    title = shorten(short_title, 78) + " | VYROX GEN X #Shorts"
    description = (f"{CATS[cat]['label']} from {story['source']}.\n\n{shorten(story['summary'], 600) if story['summary'] else short_title}\n\n"
                   f"Original source (read the full story): {story['link']}\n\n"
                   f"Visual credits: {photo_credit}.\n{music_credit}\n"
                   f"Facts come from the source above; this Short is a quick summary.\n\n{CATS[cat]['tags']}")
    meta = {"title": title, "description": description, "source": story["link"], "category": cat,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "video": str(video),
            "duration_seconds": round(total, 1), "slides": total_slides, "music": music_credit,
            "voiceover": {"provider": "Microsoft Edge TTS", "voice": os.getenv("VYROX_TTS_VOICE", "en-IN-PrabhatNeural"),
                          "text": spoken_text, "verified_file": voice_path.name},
            "viral_score": round(viral_score, 2), "viral_score_breakdown": score_breakdown,
            "viral_score_threshold": score_threshold, "quality_report": quality_report,
            "approval_required": True, "approval_status": approval_status,
            "upload_allowed": approval_status == "pending_human_review", "rights_report": rights_report, "factual_review_status": "source_attributed_single_source; independent corroboration pending"}
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
                       tags=["VYROX GEN X", story["category"], "Shorts", "Updates"], privacy=privacy)
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
        if (meta.get("approval_status") != "pending_human_review"
                or not meta.get("quality_report", {}).get("passed")
                or not meta.get("rights_report", {}).get("recognized_reuse_license")):
            raise RuntimeError("Upload blocked: viral score, media QA or photo-rights screen did not pass. Review upload_metadata.json and exact asset license.")
        if meta.get("viral_score", 0) < meta.get("viral_score_threshold", 75):
            raise RuntimeError("Upload blocked: viral score is below the configured minimum.")
        print("APPROVAL_GATE: workflow_dispatch --publish is the explicit human approval; score and media QA passed.")
        upload(video, title, description, story)
    else:
        print(f"DRAFT_ONLY: score={meta.get('viral_score')} status={meta.get('approval_status')}; no upload attempted.")


if __name__ == "__main__":
    main()