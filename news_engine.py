#!/usr/bin/env python3
"""Fresh worldwide-news roundup generator.

The daily job:
- pulls fresh headlines from multiple worldwide/category feeds,
- removes stale, repetitive and low-interest items,
- keeps broad category coverage (sports, health, tech/electronics, cars/bikes,
  crime, science/space, entertainment/anime, etc.),
- uses only real images that are explicitly rights-cleared on Wikimedia Commons,
- otherwise creates an original news graphic instead of silently reusing
  arbitrary copyrighted photos,
- shows a story-specific "Our Take" + audience question,
- uses related local licensed music when available,
- builds ONE daily roundup video plus one vertical Short.
It stores only metadata/state for external Instagram trends and never reposts
third-party Instagram media.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps, ImageFont
from human_narration import create_narration, mix_voice_music

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config' / 'config.json'
STATE = ROOT / 'state' / 'state.json'
OUT = ROOT / 'output' / 'news'
BRAND_DIR = ROOT / 'input' / 'brand_assets'
MUSIC_DIR = ROOT / 'input' / 'music'

DEFAULT_FEEDS = {
    'world': 'world international global diplomacy conflict economy when:1d',
    'india': 'India national government business society when:1d',
    'sports': 'sports cricket football tennis F1 Olympics when:1d',
    'business': 'business markets companies economy startups finance when:1d',
    'health': 'health medicine public health medical research when:1d',
    'technology': 'technology cybersecurity software internet when:1d',
    'electronics': 'smartphone gadgets laptop electronics chip semiconductor when:1d',
    'science': 'science research discovery physics biology when:1d',
    'space': 'space NASA astronomy rocket satellite when:1d',
    'environment': 'climate environment wildfire earthquake weather nature when:1d',
    'cars': 'cars automobile EV auto industry recall launch when:1d',
    'bikes': 'motorcycle bikes scooters two wheeler EV bike when:1d',
    'crime': 'crime police investigation court arrest safety when:1d',
    'gaming': 'gaming video games PlayStation Xbox Nintendo PC gaming when:1d',
    'entertainment': 'entertainment films TV streaming music celebrities when:1d',
    'anime': 'anime manga Naruto One Piece Dragon Ball Solo Leveling when:1d',
}

CATEGORY_ORDER = [
    'world', 'india', 'sports', 'business', 'health', 'technology',
    'electronics', 'science', 'space', 'environment', 'cars', 'bikes',
    'crime', 'gaming', 'entertainment', 'anime'
]

TRIGGER_TERMS = {
    'breaking', 'latest', 'update', 'updates', 'announces', 'announced',
    'launch', 'launches', 'launched', 'new', 'record', 'wins', 'won',
    'victory', 'deal', 'agreement', 'approval', 'recall', 'warning',
    'alert', 'discovered', 'discovery', 'breakthrough', 'reveals',
    'revealed', 'research', 'trial', 'decision', 'ruling', 'ban', 'banned',
    'crash', 'earthquake', 'storm', 'wildfire', 'hack', 'cyberattack',
    'arrested', 'missing', 'rescue', 'election', 'policy', 'release',
    'released', 'premiere', 'renewed', 'renewal', 'episode', 'chapter'
}
NOISE_TERMS = {
    'horoscope', 'quiz', 'sponsored', 'coupon', 'deals', 'deal of the day',
    'opinion', 'editorial', 'slideshow', 'gallery', 'photos:', 'list:',
    'top 10', 'best ', 'buying guide', 'live blog', 'watch live',
    'forecast for next week', 'predictions'
}


CATEGORY_WEIGHTS = {
    'world': 1.0,
    'india': 1.8,
    'sports': 1.15,
    'business': 1.0,
    'health': 1.1,
    'technology': 1.15,
    'electronics': 1.05,
    'science': 1.0,
    'space': 1.05,
    'environment': 0.95,
    'cars': 1.15,
    'bikes': 1.15,
    'crime': 1.05,
    'gaming': 1.0,
    'entertainment': 1.05,
    'anime': 1.15,
}

SLIDE_LABELS = [
    'WHAT HAPPENED', 'KEY DETAIL', 'THE SCENE',
    'WHY IT MATTERS', 'WHAT CHANGES', 'YOUR TAKE?'
]

CATEGORY_TAKE = {
    'world': 'OUR TAKE: The next official moves matter more than the first headline.',
    'india': 'OUR TAKE: The real impact will show up in what changes next on the ground.',
    'sports': 'OUR TAKE: The result is only half the story; the next game or selection call could matter more.',
    'business': 'OUR TAKE: Watch what this changes for customers, jobs, prices and the company next.',
    'health': 'OUR TAKE: Health headlines need evidence and qualified medical guidance, not panic or hype.',
    'technology': 'OUR TAKE: The useful question is what this changes for privacy, security, cost or everyday life.',
    'electronics': 'OUR TAKE: Specs look impressive, but real value depends on price, reliability and everyday use.',
    'science': 'OUR TAKE: One result is exciting, but follow-up evidence is what makes a discovery durable.',
    'space': 'OUR TAKE: The headline is big, but mission results and the next milestone tell the real story.',
    'environment': 'OUR TAKE: The important part is how this changes risk, policy and local impact from here.',
    'cars': 'OUR TAKE: Look beyond the launch hype: safety, range, reliability, price and service will decide it.',
    'bikes': 'OUR TAKE: The interesting part is what changes for riders on price, performance, safety and ownership.',
    'crime': 'OUR TAKE: Stick to confirmed facts and official statements; the investigation can still change details.',
    'gaming': 'OUR TAKE: The update matters most for players through gameplay, pricing, availability and support.',
    'entertainment': 'OUR TAKE: Official announcements and release details are more useful than early rumours.',
    'anime': 'OUR TAKE: Official studio, publisher or creator announcements beat fan rumours every time.'
}

CATEGORY_QUESTION = {
    'world': 'What do you think happens next?',
    'india': 'Do you think this will make a real difference in India?',
    'sports': 'Was this the right call? Tell us why.',
    'business': 'Would this change your buying or investing decision?',
    'health': 'What question should people ask their doctor before reacting to this?',
    'technology': 'Would you use this, trust this or avoid it?',
    'electronics': 'Worth buying or just marketing hype?',
    'science': 'What should researchers test next?',
    'space': 'What do you think the next big milestone will be?',
    'environment': 'What should be the priority response now?',
    'cars': 'Would you choose this over the current alternatives?',
    'bikes': 'What matters more here: price, performance or safety?',
    'crime': 'What do you think the biggest unanswered question is?',
    'gaming': 'Would this change make you play the game again?',
    'entertainment': 'Hype or genuinely worth watching?',
    'anime': 'Are you excited for this update, or waiting for more official details?'
}

MUSIC_HINTS = {
    'world': ['news', 'documentary', 'tension', 'cinematic'],
    'india': ['india', 'news', 'cinematic', 'documentary'],
    'sports': ['sports', 'hype', 'energy', 'action'],
    'business': ['business', 'corporate', 'news', 'modern'],
    'health': ['health', 'calm', 'ambient', 'documentary'],
    'technology': ['tech', 'technology', 'future', 'electronic'],
    'electronics': ['tech', 'electronic', 'future', 'gadget'],
    'science': ['science', 'ambient', 'future', 'documentary'],
    'space': ['space', 'ambient', 'cinematic', 'future'],
    'environment': ['nature', 'ambient', 'documentary'],
    'cars': ['car', 'auto', 'drive', 'action'],
    'bikes': ['bike', 'motorcycle', 'ride', 'action'],
    'crime': ['crime', 'dark', 'tension', 'thriller'],
    'gaming': ['gaming', 'game', 'action', 'hype'],
    'entertainment': ['entertainment', 'pop', 'cinematic', 'music'],
    'anime': ['naruto', 'anime', 'manga', 'dragonball', 'onepiece', 'action', 'japan']
}


def load(path, default):
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def fetch(url, timeout=25):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'MovieAutoPublisher/Worldwide-News/2.0'}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def clean(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    return re.sub(r'\s+', ' ', text).strip()


def feed_url(query):
    return (
        'https://news.google.com/rss/search?q='
        + urllib.parse.quote(query)
        + '&hl=en-IN&gl=IN&ceid=IN:en'
    )


def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def feed_items(category, query):
    root = ET.fromstring(fetch(feed_url(query)))
    items = []
    for node in root.findall('.//item'):
        title = clean(node.findtext('title'))
        link = clean(node.findtext('link'))
        desc = clean(node.findtext('description'))
        pub = clean(node.findtext('pubDate'))
        source_node = node.find('source')
        source = clean(source_node.text if source_node is not None else '')
        if not title or not link:
            continue
        items.append({
            'category': category,
            'title': title,
            'description': desc[:900],
            'link': link,
            'published': pub,
            'source': source or 'News source'
        })
    return items


def normalize_title(text):
    text = clean(text).lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(
        r'\b(live|watch|breaking|latest|update|updates|report|reports)\b',
        ' ',
        text
    )
    return re.sub(r'\s+', ' ', text).strip()


def token_set(text):
    stop = {
        'the', 'a', 'an', 'to', 'of', 'for', 'and', 'in', 'on', 'at', 'with',
        'from', 'after', 'before', 'as', 'is', 'are', 'this', 'that', 'new',
        'latest', 'update', 'updates', 'says', 'say', 'over'
    }
    return {
        x for x in re.findall(r'[a-z0-9]{3,}', normalize_title(text))
        if x not in stop
    }


def fingerprint(item):
    base = normalize_title(item.get('title', '')) + '|' + clean(item.get('link', ''))
    return hashlib.sha256(base.encode('utf-8')).hexdigest()


def age_hours(item):
    dt = parse_date(item.get('published', ''))
    if not dt:
        return 24.0
    age = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    return max(0.0, age)


def score_item(item, trend_terms=None):
    title = normalize_title(item.get('title', ''))
    age = age_hours(item)
    tokens = token_set(title)
    trigger_hits = len(tokens.intersection(TRIGGER_TERMS))
    noise_hits = sum(1 for term in NOISE_TERMS if term in title)
    recency = max(0.0, 8.0 - min(age, 30.0) * 0.22)
    score = recency + trigger_hits * 1.7 - noise_hits * 5.0
    if item.get('source') and item.get('source') != 'News source':
        score += 0.8
    if trend_terms and len(tokens.intersection(trend_terms)) >= 2:
        score += 2.4
    if item.get('category') in {'crime', 'health'}:
        score += 0.3
    score *= CATEGORY_WEIGHTS.get(item.get('category'), 1.0)
    if item.get('category') == 'india':
        score += 1.5
    return score


def trend_terms():
    terms = set()

    instagram_path = ROOT / 'state' / 'instagram_trends.json'
    instagram = load(instagram_path, {'items': []})
    for row in instagram.get('items', [])[:60]:
        terms.update(token_set(row.get('caption', '')))

    youtube_path = ROOT / 'state' / 'youtube_trends.json'
    youtube = load(youtube_path, {'popular': [], 'music': []})
    for row in youtube.get('popular', [])[:80]:
        terms.update(token_set(row.get('title', '')))
        terms.update(token_set(row.get('channel_title', '')))
    for row in youtube.get('music', [])[:40]:
        terms.update(token_set(row.get('title', '')))
        terms.update(token_set(row.get('channel_title', '')))

    return terms


def choose_stories(items, limit, seen_fingerprints, trend_words):
    fresh_hours = float(load(CONFIG, {}).get('news_fresh_hours', 30))
    candidates = []
    seen_norm = set()
    for item in items:
        fp = fingerprint(item)
        norm = normalize_title(item.get('title', ''))
        if fp in seen_fingerprints:
            continue
        if not norm or norm in seen_norm:
            continue
        if age_hours(item) > fresh_hours:
            continue
        if any(term in norm for term in NOISE_TERMS):
            continue
        item['fingerprint'] = fp
        item['_score'] = score_item(item, trend_words)
        candidates.append(item)
        seen_norm.add(norm)

    # Collapse near-duplicate headlines across different sources.
    deduped = []
    for item in sorted(candidates, key=lambda x: x['_score'], reverse=True):
        a = token_set(item['title'])
        duplicate = False
        for chosen in deduped:
            b = token_set(chosen['title'])
            if a and b:
                overlap = len(a & b) / max(1, min(len(a), len(b)))
                similarity = SequenceMatcher(None, normalize_title(item['title']), normalize_title(chosen['title'])).ratio()
                if overlap >= 0.75 or similarity >= 0.86:
                    duplicate = True
                    break
        if not duplicate:
            deduped.append(item)

    # First pass: broad category coverage, max one strong item per category.
    selected = []
    by_cat = {}
    for item in deduped:
        by_cat.setdefault(item['category'], []).append(item)
    for category in CATEGORY_ORDER:
        if len(selected) >= limit:
            break
        pool = by_cat.get(category, [])
        if pool:
            selected.append(max(pool, key=lambda x: x['_score']))

    # Second pass: strongest remaining stories, max two per category.
    counts = {cat: 0 for cat in CATEGORY_ORDER}
    counts.update({x['category']: 1 for x in selected})
    for item in deduped:
        if len(selected) >= limit:
            break
        if item in selected:
            continue
        if counts.get(item['category'], 0) >= 2:
            continue
        selected.append(item)
        counts[item['category']] = counts.get(item['category'], 0) + 1

    for item in selected:
        item.pop('_score', None)
    return selected


def allowed_license(text):
    lic = clean(text).lower()
    if any(bad in lic for bad in ('nc', 'noncommercial', 'nd', 'noderivatives')):
        return False
    return any(
        good in lic
        for good in ('cc by-sa', 'cc by', 'cc0', 'public domain', 'pd-')
    )


def commons_images(item, work, max_count=6):
    """Return up to max_count relevant, real, rights-cleared Commons images."""
    title = item.get('title', '')
    query = title[:180]
    url = (
        'https://commons.wikimedia.org/w/api.php?action=query'
        '&generator=search&gsrnamespace=6&gsrlimit=15&prop=imageinfo'
        '&iiprop=url|extmetadata|mime|size&iiurlwidth=1600&format=json&gsrsearch='
        + urllib.parse.quote(query)
    )
    try:
        data = json.loads(fetch(url, timeout=25).decode('utf-8'))
    except Exception:
        return []

    title_tokens = token_set(title)
    results = []
    pages = data.get('query', {}).get('pages', {})
    ordered = sorted(pages.values(), key=lambda p: p.get('index', 9999))
    for page in ordered:
        info = (page.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata') or {}
        mime = clean(info.get('mime', '')).lower()
        if not mime.startswith('image/'):
            continue
        if mime in {'image/svg+xml', 'image/gif'}:
            continue
        lic_short = clean(meta.get('LicenseShortName', {}).get('value', ''))
        usage = clean(meta.get('UsageTerms', {}).get('value', ''))
        lic_blob = (lic_short + ' ' + usage).strip()
        if not allowed_license(lic_blob):
            continue

        file_title = clean(page.get('title', ''))
        file_tokens = token_set(file_title)
        overlap = len(title_tokens & file_tokens)
        if title_tokens and overlap == 0:
            continue
        width = int(info.get('width') or 0)
        height = int(info.get('height') or 0)
        if width < 600 or height < 350:
            continue

        source_url = info.get('thumburl') or info.get('url')
        if not source_url:
            continue
        if any(x.get('url') == source_url for x in results):
            continue

        filename = (
            work / 'rights_cleared'
            / f"{len(results)+1:02d}_{hashlib.sha1(source_url.encode()).hexdigest()[:10]}.jpg"
        )
        try:
            filename.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(
                source_url,
                headers={'User-Agent': 'MovieAutoPublisher/Worldwide-News/2.0'}
            )
            with urllib.request.urlopen(req, timeout=35) as response:
                raw = response.read()
            filename.write_bytes(raw)
            artist = clean(meta.get('Artist', {}).get('value', '')) or 'Unknown author'
            license_name = lic_short or usage or 'Rights-cleared'
            page_url = (
                'https://commons.wikimedia.org/wiki/File:'
                + urllib.parse.quote(file_title.replace('File:', '').replace(' ', '_'))
            )
            results.append({
                'path': filename,
                'artist': artist,
                'license': license_name,
                'page': page_url,
                'url': source_url
            })
            if len(results) >= max_count:
                break
        except Exception:
            continue
    return results


def font(size, bold=False):
    candidates = [
        '/system/fonts/Roboto-Bold.ttf' if bold else '/system/fonts/Roboto-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap(draw, text, fnt, width):
    words = str(text).split()
    lines, line = [], ''
    for word in words:
        test = (line + ' ' + word).strip()
        if draw.textbbox((0, 0), test, font=fnt)[2] <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def safe_name(text):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(text)).strip('_')[:70] or 'news'


def category_name(category):
    return {
        'ai': 'AI',
        'f1': 'F1',
    }.get(category, category.upper())


def brand_logo():
    if not BRAND_DIR.exists():
        return None
    files = [
        p for p in BRAND_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}
    ]
    return sorted(files, key=lambda p: p.stat().st_size, reverse=True)[0] if files else None


def make_fallback_visual(item, out, size=(1920, 1080)):
    w, h = size
    im = Image.new('RGB', (w, h), (12, 14, 20))
    d = ImageDraw.Draw(im)
    # Original graphic elements, deliberately not AI-generated or scraped.
    for y in range(h):
        shade = int(10 + 42 * y / max(1, h - 1))
        d.line((0, y, w, y), fill=(shade, shade, min(255, shade + 8)))
    cx, cy = int(w * 0.74), int(h * 0.56)
    for r in (260, 190, 120, 70):
        d.ellipse((cx-r, cy-r, cx+r, cy+r), outline=(75, 78, 86), width=4)
    label = category_name(item['category'])
    d.text((70, 80), label, font=font(38, True), fill='white')
    for i, line in enumerate(wrap(d, item['title'], font(66, True), int(w * 0.55))[:5]):
        d.text((70, 160 + i * 78), line, font=font(66, True), fill='white', stroke_width=2, stroke_fill='black')
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=94, optimize=True)
    return out


def make_slide(item, source_image, out, slide_no, total_slides, size=(1920, 1080), real_photo=False):
    w, h = size
    if source_image and source_image.exists():
        try:
            im = ImageOps.fit(Image.open(source_image).convert('RGB'), (w, h), method=Image.Resampling.LANCZOS)
            im = ImageEnhance.Contrast(im).enhance(1.06)
            im = ImageEnhance.Color(im).enhance(1.03)
            # Keep the real image visible; add readability layers only where text sits.
            im = im.convert('RGBA')
        except Exception:
            im = Image.new('RGBA', (w, h), (12, 14, 20, 255))
            real_photo = False
    else:
        im = Image.new('RGBA', (w, h), (12, 14, 20, 255))
        real_photo = False

    if not source_image or not source_image.exists() or not real_photo:
        base = Image.new('RGB', (w, h), (12, 14, 20))
        make_fallback_visual(item, out.with_name(out.stem + '_fallback.jpg'), size=size)
        try:
            im = Image.open(out.with_name(out.stem + '_fallback.jpg')).convert('RGBA')
        except Exception:
            im = base.convert('RGBA')

    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, 0, w, int(h * 0.31)), fill=(0, 0, 0, 190))
    for y in range(int(h * 0.55), h):
        alpha = int(210 * (y - h * 0.55) / max(1, h * 0.45))
        od.line((0, y, w, y), fill=(0, 0, 0, alpha))
    im = Image.alpha_composite(im, overlay)

    d = ImageDraw.Draw(im)
    margin = int(w * 0.04)
    top_f = font(max(28, int(w * 0.022)), True)
    title_f = font(max(48, int(w * 0.035)), True)
    take_f = font(max(24, int(w * 0.016)), False)
    q_f = font(max(26, int(w * 0.017)), True)
    tiny_f = font(max(18, int(w * 0.012)), False)

    d.text((margin, int(h * 0.045)), f"LATEST • {category_name(item['category'])}", font=top_f, fill='white')
    badge = 'REAL PHOTO • RIGHTS-CLEARED' if real_photo else 'ORIGINAL VISUAL'
    badge_box = d.textbbox((0, 0), badge, font=tiny_f)
    bx = w - margin - (badge_box[2] - badge_box[0]) - 28
    d.rounded_rectangle((bx, int(h * 0.04), w - margin, int(h * 0.105)),
                        radius=18, fill=(0, 0, 0, 165), outline=(255, 255, 255, 170), width=2)
    d.text((bx + 14, int(h * 0.055)), badge, font=tiny_f, fill='white')

    title_lines = wrap(d, item['title'], title_f, int(w * 0.90))[:4]
    y = int(h * 0.125)
    line_step = int(title_f.size * 1.08)
    for line in title_lines:
        d.text((margin, y), line, font=title_f, fill='white', stroke_width=2, stroke_fill='black')
        y += line_step

    d.text(
        (margin, int(h * 0.62)),
        f"{SLIDE_LABELS[(slide_no - 1) % len(SLIDE_LABELS)]}  •  {slide_no}/{total_slides}",
        font=top_f,
        fill='white'
    )

    take = CATEGORY_TAKE.get(
        item['category'],
        'OUR TAKE: We are separating confirmed facts from speculation and waiting for the official update.'
    )
    question = CATEGORY_QUESTION.get(item['category'], 'What do you think happens next?')
    take_lines = wrap(d, take, take_f, int(w * 0.92))[:2]
    q_lines = wrap(d, 'YOUR TAKE: ' + question, q_f, int(w * 0.92))[:2]
    yy = int(h * 0.71)
    for line in take_lines:
        d.text((margin, yy), line, font=take_f, fill=(238, 238, 238), stroke_width=1, stroke_fill='black')
        yy += int(take_f.size * 1.25)
    yy += 6
    for line in q_lines:
        d.text((margin, yy), line, font=q_f, fill='white', stroke_width=1, stroke_fill='black')
        yy += int(q_f.size * 1.25)

    source = item.get('source') or 'News source'
    d.text((margin, h - int(h * 0.07)), f"Source: {source} • Verify the original report before sharing.", font=tiny_f, fill=(220, 220, 220))
    d.text((margin, h - int(h * 0.04)), f"Published: {item.get('published', 'today')}", font=tiny_f, fill=(175, 175, 175))

    logo = brand_logo()
    if logo:
        try:
            lg = Image.open(logo).convert('RGBA')
            lg.thumbnail((int(w * 0.10), int(h * 0.10)), Image.Resampling.LANCZOS)
            im.alpha_composite(lg, (w - lg.width - margin, h - lg.height - margin))
        except Exception:
            pass

    out.parent.mkdir(parents=True, exist_ok=True)
    im.convert('RGB').save(out, quality=94, optimize=True)
    return out


def pick_music(stories):
    if not MUSIC_DIR.exists():
        return None
    tracks = [
        p for p in MUSIC_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {'.mp3', '.m4a', '.wav', '.aac'}
    ]
    if not tracks:
        return None

    full_text = ' '.join(
        [str(s.get('category', '')) + ' ' + str(s.get('title', '')) for s in stories]
    ).lower()
    hints = set()
    for story in stories:
        hints.update(MUSIC_HINTS.get(story.get('category'), []))
        # Anime must prefer the matching franchise/style track when present.
        t = story.get('title', '').lower()
        for franchise in ('naruto', 'one piece', 'dragon ball', 'solo leveling'):
            if franchise in t:
                hints.add(franchise.replace(' ', ''))

    def track_score(path):
        name = re.sub(r'[^a-z0-9]+', ' ', path.stem.lower())
        score = sum(5 for hint in hints if hint in name)
        if 'anime' in full_text and any(x in name for x in ('anime', 'japan', 'action', 'naruto', 'manga')):
            score += 8
        if 'crime' in full_text and any(x in name for x in ('dark', 'tension', 'thriller')):
            score += 8
        if 'sports' in full_text and any(x in name for x in ('sports', 'hype', 'energy', 'action')):
            score += 7
        return score

    best_score = max(track_score(p) for p in tracks)
    best = sorted([p for p in tracks if track_score(p) == best_score])
    if best_score > 0:
        return best[0]
    return sorted(tracks)[0]


def run(cmd):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stdout[-4000:])
    return proc.stdout


def render_image_clip(image, out, duration, size='1920x1080'):
    sw, sh = (int(x) for x in size.split('x'))
    vf = (
        f'scale={sw}:{sh}:force_original_aspect_ratio=increase,'
        f'crop={sw}:{sh},'
        "zoompan=z='min(zoom+0.0009,1.07)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':d=1:"
        f's={sw}x{sh}:fps=25,'
        'format=yuv420p'
    )
    fade_start = max(0.25, float(duration) - 0.22)
    vf += f',fade=t=in:st=0:d=0.18,fade=t=out:st={fade_start:.2f}:d=0.18'
    run([
        'ffmpeg', '-y', '-loop', '1', '-i', str(image),
        '-t', f'{float(duration):.3f}',
        '-vf', vf,
        '-r', '25',
        '-an',
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        str(out)
    ])
    return out

def _concat_list(clips, out):
    list_file = out.with_suffix('.concat.txt')
    list_file.write_text(
        ''.join(
            "file '" + str(Path(c).resolve()).replace("'", "'\\''") + "'\n"
            for c in clips
        ),
        encoding='utf-8'
    )
    return list_file


def concat_videos(clips, out):
    list_file = _concat_list(clips, out)
    run([
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', str(list_file),
        '-c:v', 'libx264', '-preset', 'veryfast',
        '-pix_fmt', 'yuv420p', '-an',
        '-movflags', '+faststart',
        str(out)
    ])
    return out


def concat_av_videos(clips, out):
    """Concatenate clips that all contain matching video + stereo AAC audio."""
    list_file = _concat_list(clips, out)
    run([
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', str(list_file),
        '-c:v', 'libx264', '-preset', 'veryfast',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '128k',
        '-ar', '44100', '-ac', '2',
        '-movflags', '+faststart',
        str(out)
    ])
    return out


def add_music(video, out, music):
    """Add a related licensed track, or a silent stereo track when unavailable."""
    if music:
        input_args = ['-stream_loop', '-1', '-i', str(music)]
        audio_map = ['1:a:0']
    else:
        input_args = [
            '-f', 'lavfi', '-t', '999999',
            '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100'
        ]
        audio_map = ['1:a:0']

    run([
        'ffmpeg', '-y',
        '-i', str(video),
        *input_args,
        '-map', '0:v:0',
        '-map', *audio_map,
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '128k',
        '-ar', '44100', '-ac', '2',
        '-shortest',
        '-movflags', '+faststart',
        str(out)
    ])
    return out


def ff_duration(path):
    value = run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(path)
    ]).strip()
    return float(value or 0.0)


def description_for(stories):
    lines = [
        '🌍 DAILY WORLDWIDE NEWS ROUNDUP',
        '',
        'Fresh, high-interest updates selected across world, India, sports, health, tech/electronics, science/space, cars/bikes, crime, gaming, entertainment and anime.'
    ]
    for idx, story in enumerate(stories, 1):
        lines.append(f"{idx}. [{category_name(story['category'])}] {story['title']}")
        lines.append(f"   Source: {story.get('source', 'News source')} | {story.get('link', '')}")
        lines.append(
            '   ' + CATEGORY_TAKE.get(
                story['category'],
                'Our take: confirmed facts first; speculation second.'
            )
        )
        lines.append('   Your take: ' + CATEGORY_QUESTION.get(story['category'], 'What do you think happens next?'))
        for media in story.get('media', []):
            lines.append(f"   Image credit: {media['artist']} — {media['license']} | {media['page']}")
    lines.append('')
    lines.append('Some stories may use an original visual when a relevant rights-cleared real photo is not available.')
    return '\n'.join(lines)


def make_hook(stories, work):
    w, h = 1920, 1080
    hook = Image.new('RGB', (w, h), (8, 10, 14))
    d = ImageDraw.Draw(hook)
    d.text((70, 50), "TODAY'S BIGGEST UPDATES", font=font(56, True), fill='white')
    d.text((70, 122), "Real photos where rights-cleared • No random reposts", font=font(26), fill=(205, 205, 205))

    cols = min(3, max(1, len(stories)))
    gap = 28
    card_w = (w - gap * (cols + 1)) // cols
    card_h = 650
    y = 210
    for idx, story in enumerate(stories[:cols]):
        x = gap + idx * (card_w + gap)
        media = story.get('media', [])
        if media:
            try:
                img = ImageOps.fit(Image.open(media[0]['path']).convert('RGB'), (card_w, card_h))
            except Exception:
                img = Image.new('RGB', (card_w, card_h), (24, 26, 32))
        else:
            img = Image.new('RGB', (card_w, card_h), (24, 26, 32))
        hook.paste(img, (x, y))
        d = ImageDraw.Draw(hook)
        d.rectangle((x, y + card_h - 180, x + card_w, y + card_h), fill=(0, 0, 0))
        d.text((x + 24, y + card_h - 150), category_name(story['category']), font=font(26, True), fill='white')
        lines = wrap(d, story['title'], font(31, True), card_w - 48)[:3]
        for li, line in enumerate(lines):
            d.text((x + 24, y + card_h - 112 + li * 38), line, font=font(31, True), fill='white')
    d.text((70, 930), "Global • India • Sports • Health • Tech • Cars/Bikes • Crime • Science • Anime", font=font(28, True), fill='white')
    out = work / 'hook.jpg'
    out.parent.mkdir(parents=True, exist_ok=True)
    hook.save(out, quality=94, optimize=True)
    return out


def make_vertical_slide(item, source_image, out, slide_no, total_slides, real_photo):
    return make_slide(
        item,
        source_image,
        out,
        slide_no,
        total_slides,
        size=(1080, 1920),
        real_photo=real_photo
    )


def generate_roundup():
    cfg = load(CONFIG, {})
    target = max(1, min(12, int(cfg.get('daily_news_stories', 12))))
    max_slides = max(1, min(6, int(cfg.get('news_max_slides_per_story', 6))))
    min_slides = max(1, min(max_slides, int(cfg.get('news_min_slides_per_story', 1))))
    slide_seconds = max(1.5, float(cfg.get('news_slide_seconds', 2.4)))
    fresh_hours = float(cfg.get('news_fresh_hours', 30))

    state = load(STATE, {'news': []})
    today = time.strftime('%Y-%m-%d')
    if any(x.get('date') == today and x.get('status') == 'ready' for x in state.get('news', [])):
        print(f'News roundup already generated for {today}')
        return

    seen = set()
    for row in state.get('news', []):
        seen.update(row.get('story_fingerprints', []))
        if row.get('fingerprint'):
            seen.add(row['fingerprint'])

    all_items = []
    configured = cfg.get('news_categories', CATEGORY_ORDER)
    for category in configured:
        query = DEFAULT_FEEDS.get(
            category,
            f'{category} news when:1d'
        )
        try:
            all_items.extend(feed_items(category, query)[:10])
        except Exception as exc:
            print(f'Feed failed {category}: {exc}')

    if not all_items:
        print('No news feeds returned data today; nothing uploaded.')
        return

    stories = choose_stories(all_items, target, seen, trend_terms())
    if not stories:
        print(f'No fresh meaningful stories within {fresh_hours:.0f}h; nothing uploaded.')
        return

    work = OUT / today
    work.mkdir(parents=True, exist_ok=True)

    # Download only rights-cleared Commons photos; otherwise use original visuals.
    for idx, story in enumerate(stories, 1):
        story_dir = work / f'story_{idx:02d}_{safe_name(story["category"])}'
        media = commons_images(story, story_dir, max_count=max_slides)
        story['media'] = media
        if media:
            wanted = max(min_slides, min(max_slides, len(media)))
            story['media'] = media[:wanted]

    # Build the visual slides. Every story gets 1-6 slides, depending on available
    # relevant rights-cleared photos.
    story_clips = []
    story_music = []
    for idx, story in enumerate(stories, 1):
        media = story.get('media', [])
        total = max(1, min(max_slides, len(media)))
        slide_files = []
        story_dir = work / f'story_{idx:02d}_{safe_name(story["category"])}'
        if not media:
            fallback = story_dir / 'slide_01.jpg'
            make_slide(story, None, fallback, 1, 1, real_photo=False)
            slide_files.append(fallback)
        else:
            for j, media_row in enumerate(media[:max_slides], 1):
                slide = story_dir / f'slide_{j:02d}.jpg'
                make_slide(story, media_row['path'], slide, j, total, real_photo=True)
                slide_files.append(slide)

        # Generate spoken narration before rendering so visuals last for the full voiceover.
        story['take'] = CATEGORY_TAKE.get(story.get('category'), '')
        story['question'] = CATEGORY_QUESTION.get(story.get('category'), '')
        voice_file = story_dir / 'narration.mp3'
        create_narration(story, voice_file)
        voice_seconds = ff_duration(voice_file)
        per_slide_seconds = max(slide_seconds, (voice_seconds + 0.8) / max(1, len(slide_files)))

        clips = []
        for j, slide in enumerate(slide_files, 1):
            clip = story_dir / f'slide_{j:02d}.mp4'
            render_image_clip(slide, clip, per_slide_seconds)
            clips.append(clip)

        story_silent = story_dir / 'story_silent.mp4'
        concat_videos(clips, story_silent)

        # Prefer relevant licensed music; narration is mandatory even if no music exists.
        music = pick_music([story])
        story['music'] = str(music.relative_to(ROOT)) if music and music.exists() else None
        story_music.append(story.get('music'))
        story_audio = story_dir / 'story_with_audio.mp4'
        mix_voice_music(story_silent, voice_file, music, story_audio)
        story_clips.append(story_audio)

    hook = make_hook(stories, work)
    hook_video_silent = work / 'hook_silent.mp4'
    hook_seconds = max(4.0, min(6.0, float(cfg.get('news_hook_seconds', 5.0))))
    render_image_clip(hook, hook_video_silent, hook_seconds)
    hook_audio = work / 'hook_with_audio.mp4'
    add_music(hook_video_silent, hook_audio, pick_music(stories[:1]))

    final_video = work / 'daily_world_roundup.mp4'
    concat_av_videos([hook_audio] + story_clips, final_video)

    # A compact vertical Short: first 3 strongest stories, one real-photo/original
    # slide each. Each Short segment keeps the matching story music.
    short_count = max(1, min(6, int(cfg.get('news_short_story_count', 3))))
    short_clips = []
    for idx, story in enumerate(stories[:short_count], 1):
        story_dir = work / f'short_{idx:02d}'
        story_dir.mkdir(parents=True, exist_ok=True)
        src = story.get('media', [])
        vslide = story_dir / 'slide.jpg'
        make_vertical_slide(
            story,
            src[0]['path'] if src else None,
            vslide,
            1,
            1,
            bool(src)
        )
        story['take'] = CATEGORY_TAKE.get(story.get('category'), '')
        story['question'] = CATEGORY_QUESTION.get(story.get('category'), '')
        voice_file = story_dir / 'narration_short.mp3'
        create_narration(story, voice_file, short=True)
        voice_seconds = ff_duration(voice_file)
        silent = story_dir / 'silent.mp4'
        render_image_clip(vslide, silent, max(7.0, voice_seconds + 0.5), size='1080x1920')
        with_audio = story_dir / 'with_audio.mp4'
        music_ref = ROOT / story['music'] if story.get('music') else pick_music([story])
        mix_voice_music(silent, voice_file, music_ref, with_audio)
        short_clips.append(with_audio)

    short_video = work / 'daily_world_short.mp4'
    concat_av_videos(short_clips, short_video)

    title = f'🌍 World News Roundup • {time.strftime("%d %b %Y")}'
    record = {
        'id': f'{today}-world-roundup',
        'date': today,
        'category': 'world-roundup',
        'title': title,
        'video': str(final_video.relative_to(ROOT)),
        'short': str(short_video.relative_to(ROOT)),
        'thumbnail': str(hook.relative_to(ROOT)),
        'caption': description_for(stories),
        'stories': [
            {
                'category': s['category'],
                'title': s['title'],
                'source': s.get('source'),
                'link': s.get('link'),
                'published': s.get('published'),
                'fingerprint': s.get('fingerprint'),
                'media': [
                    {
                        'artist': m['artist'],
                        'license': m['license'],
                        'page': m['page']
                    }
                    for m in s.get('media', [])
                ]
            }
            for s in stories
        ],
        'story_fingerprints': [s['fingerprint'] for s in stories],
        'fingerprint': hashlib.sha256(
            ('|'.join(s['fingerprint'] for s in stories)).encode('utf-8')
        ).hexdigest(),
        'fresh_hours_window': fresh_hours,
        'status': 'ready',
        'created_at': int(time.time()),
        'music_tracks': [s.get('music') for s in stories]
    }
    state.setdefault('news', []).append(record)
    save(STATE, state)
    print(f'WORLD ROUNDUP READY: {final_video}')
    print(f'WORLD SHORT READY: {short_video}')
    print(f'Stories selected: {len(stories)}')
    for idx, story in enumerate(stories, 1):
        print(f'  {idx}. [{story["category"]}] {story["title"]} | slides={len(story.get("media", [])) or 1}')
    return record


def generate(limit=None):
    # Kept as the public entry point used by upload_queue.py.
    return generate_roundup()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--daily', action='store_true', help='Build one fresh worldwide daily roundup')
    ap.add_argument('--limit', type=int, default=None, help='Legacy argument; daily roundup uses config daily_news_stories')
    args = ap.parse_args()
    if args.daily:
        generate_roundup()
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
