#!/usr/bin/env python3
"""Daily image-post generator for authorized content.

Creates two original social-image cards from supplied/licensed video frames.
No web image scraping is performed, so the generated cards do not silently
pull random copyrighted images from the internet.
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
from scene_tools import detect_scene_times, detect_silence_ranges, rank_highlight_windows

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state' / 'state.json'
CONFIG = ROOT / 'config' / 'config.json'
OUT = ROOT / 'output' / 'image_posts'


def load(path, default):
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def safe_name(s):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(s)).strip('_') or 'post'


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        raise RuntimeError(p.stdout[-3000:])
    return p.stdout


def duration(video):
    return float(run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                      '-of', 'default=noprint_wrappers=1:nokey=1', str(video)]).strip())


def extract_frame(video, seconds, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    run(['ffmpeg', '-y', '-ss', f'{max(0, seconds):.3f}', '-i', str(video),
         '-frames:v', '1', '-q:v', '2', str(path)])
    return path


def font(size, bold=False):
    candidates = [
        '/system/fonts/Roboto-Bold.ttf' if bold else '/system/fonts/Roboto-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def wrap(draw, text, fnt, max_width):
    words = str(text).split()
    lines, line = [], ''
    for word in words:
        test = (line + ' ' + word).strip()
        if draw.textbbox((0, 0), test, font=fnt)[2] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def card(frame, title, subtitle, out, badge=None, dark=False, question=None, source=None, accent=None, top_label='CINEMA MOMENT • FAN EDIT'):
    """High-impact 4:5 social card inspired by editorial/meme carousel layouts."""
    im = Image.open(frame).convert('RGB')
    # Keep the original frame/photo as the hero; crop only to the social canvas.
    im = ImageOps.fit(im, (1080, 1350), method=Image.Resampling.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.10)
    im = ImageEnhance.Color(im).enhance(0.94 if dark else 1.04)

    overlay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # Strong lower gradient, similar to meme/editorial reels: readable on mobile.
    for y in range(610, 1350):
        alpha = int(235 * ((y - 610) / 740))
        od.line((0, y, 1080, y), fill=(0, 0, 0, alpha))
    # Small top veil for category/badge readability.
    od.rectangle((0, 0, 1080, 145), fill=(0, 0, 0, 125))
    im = Image.alpha_composite(im.convert('RGBA'), overlay)

    d = ImageDraw.Draw(im)
    margin = 58
    accent = accent or (47, 202, 236)
    white = 'white'
    black = 'black'

    meta_f = font(27, True)
    title_f = font(64, True)
    sub_f = font(31, True)
    q_f = font(30, True)
    tiny_f = font(21, False)

    # Editorial header: not a fake quotation or fake attribution.
    d.text((margin, 42), str(top_label)[:28], font=meta_f, fill=accent)
    if badge:
        badge_w = d.textbbox((0, 0), badge, font=meta_f)[2] + 28
        d.rounded_rectangle(
            (1080 - margin - badge_w, 32, 1080 - margin, 94),
            radius=18, fill=(0, 0, 0, 180), outline=white, width=2
        )
        d.text((1080 - margin - badge_w + 14, 46), badge, font=meta_f, fill=white)

    # Keep the source frame dominant; no fake quotes or distracting sticker stack.
    y = 730
    for line in wrap(d, title, title_f, 950)[:5]:
        d.text((margin, y), line, font=title_f, fill=white, stroke_width=2, stroke_fill=black)
        y += 76

    y += 10
    for line in wrap(d, subtitle, sub_f, 930)[:2]:
        d.text((margin + 4, y), line, font=sub_f, fill=(240, 240, 240), stroke_width=1, stroke_fill=black)
        y += 42

    if question:
        q_y = 1110
        d.rounded_rectangle(
            (margin, q_y - 12, 1022, q_y + 86),
            radius=18, fill=(0, 0, 0, 165), outline=(255, 255, 255, 100), width=2
        )
        q_lines = wrap(d, 'YOUR TAKE: ' + question, q_f, 920)[:2]
        yy = q_y + 6
        for line in q_lines:
            d.text((margin + 18, yy), line, font=q_f, fill=white)
            yy += 38

    # Small source/credit line; no invented attribution.
    if source:
        d.text((margin, 1270), f'Source: {source}', font=tiny_f, fill=(225, 225, 225))
    d.text((margin, 1310), 'Swipe • Read • React', font=tiny_f, fill=(185, 185, 185))

    out.parent.mkdir(parents=True, exist_ok=True)
    im.convert('RGB').save(out, quality=95, optimize=True)
    return out


def choose_source(state, recent_days=30):
    cutoff = time.time() - (recent_days * 86400)
    recent_source_ids = {
        str(x.get('source_item'))
        for x in state.get('image_posts', [])
        if float(x.get('created_at', 0) or 0) >= cutoff
    }
    # Prefer processed authorized items that have not been used recently.
    for item_id, info in state.get('processed', {}).items():
        if str(item_id) in recent_source_ids:
            continue
        outputs = info.get('outputs', [])
        if outputs:
            source = info.get('source')
            if source and (ROOT / source).exists():
                return item_id, ROOT / source, info
    # Backward-compatible fallback to metadata.json, still respecting no-repeat.
    meta = load(ROOT / 'metadata.json', {'items': []})
    for item in meta.get('items', []):
        if str(item.get('id')) in recent_source_ids:
            continue
        if item.get('licensed') and (ROOT / item.get('source', '')).exists():
            return item['id'], ROOT / item['source'], item
    return None, None, None


def generate_daily_images():
    """Build 1-3 cards from a separate, licensed image library, never video/news fallback."""
    state = load(STATE, {'processed': {}, 'queue': [], 'image_posts': [], 'daily': {}})
    cfg = load(CONFIG, {})
    today = time.strftime('%Y-%m-%d')
    target_count = max(1, min(3, int(cfg.get('daily_image_posts', 3))))
    generated_today = [
        x for x in state.get('image_posts', [])
        if x.get('date') == today and x.get('asset_type') == 'licensed_image_source'
    ]
    if len(generated_today) >= target_count:
        print(f'Image posts already generated for {today}: {len(generated_today)}')
        return
    target_count = target_count - len(generated_today)

    manifest_path = ROOT / 'image_sources.json'
    manifest = load(manifest_path, {'items': []})
    daily = state.get('daily', {}).get(today, {})
    video_ids = {
        str(x) for key in ('long', 'short', 'reel') for x in daily.get(key, [])
    }
    video_item_ids = {
        str(x) for key in ('movie_long_item_ids', 'movie_short_item_ids', 'movie_reel_item_ids')
        for x in daily.get(key, [])
    }
    video_topics = {
        str(x) for key in ('movie_long_topics', 'movie_short_topics', 'movie_reel_topics')
        for x in daily.get(key, []) if x
    }
    cutoff = time.time() - int(cfg.get('image_no_repeat_days', 30)) * 86400
    recent_rows = [
        row for row in state.get('image_posts', [])
        if float(row.get('created_at', 0) or 0) >= cutoff
    ]
    recently_used = {str(row.get('source_item')) for row in recent_rows}
    recently_used_topics = {str(row.get('topic_id')) for row in recent_rows if row.get('topic_id')}
    today_image_topics = {
        str(row.get('topic_id')) for row in generated_today if row.get('topic_id')
    }
    blocked_topics = video_topics | recently_used_topics | today_image_topics
    seen_topic_ids = set()

    candidates = []
    seen_paths = set()
    for item in manifest.get('items', []):
        if item.get('licensed') is not True:
            continue
        item_id = str(item.get('id') or '')
        topic_id = str(item.get('topic_id') or item_id).strip()
        if (not item_id or item_id in recently_used or item_id in video_ids
                or item_id in video_item_ids or not topic_id
                or topic_id in blocked_topics or topic_id in seen_topic_ids):
            continue
        rel = str(item.get('source') or '')
        if not rel or rel.startswith(('http://', 'https://')):
            continue
        path = (ROOT / rel).resolve()
        if ROOT.resolve() not in path.parents or not path.is_file():
            continue
        if path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
            continue
        if str(path) in seen_paths:
            continue
        seen_paths.add(str(path))
        seen_topic_ids.add(topic_id)
        candidates.append((item, path))

    if not candidates:
        print('Daily images: no separate, unused licensed image sources configured; no news or video-frame fallback will be used.')
        return

    # Rotate by least-recently-used input order; each post has its own source ID.
    posts = []
    work = OUT / today
    work.mkdir(parents=True, exist_ok=True)
    accents = {
        'anime': (255, 110, 205), 'funny': (255, 220, 70),
        'comedy': (255, 220, 70), 'action': (255, 145, 60),
        'movie': (235, 190, 95), 'series': (75, 220, 230),
        'dark': (175, 160, 255), 'cinematic': (235, 190, 95),
    }
    for index, (item, image) in enumerate(candidates[:target_count], 1):
        title = str(item.get('title') or item.get('category') or 'Cinema moment').strip()
        subtitle = str(item.get('caption_text') or item.get('tagline') or 'A moment worth keeping.').strip()
        category = str(item.get('category') or 'movie').lower()
        accent = accents.get(category, accents['cinematic'])
        out = work / f"{safe_name(item['id'])}_{index:02d}.jpg"
        question = str(item.get('question') or 'Which detail did you notice first?')
        credit = str(item.get('credit') or item.get('license') or 'Rights-cleared source')
        card(
            image, title, subtitle, out,
            badge='18+' if item.get('adult') else None,
            dark=category == 'dark',
            question=question,
            source=credit,
            accent=accent,
            top_label=f'{category.upper()} • MOMENT'
        )
        post = {
            'id': f'{today}-{item["id"]}',
            'date': today,
            'category': category,
            'image': str(out.relative_to(ROOT)),
            'caption': f'{title}\n\n{subtitle}\n\n{str(item.get("hashtags") or "#MovieMoments #AnimeEdit").strip()}',
            'source_item': item['id'],
            'topic_id': str(item.get('topic_id') or item['id']),
            'source': str(image.relative_to(ROOT)),
            'license': str(item.get('license') or 'rights-cleared; user-confirmed'),
            'asset_type': 'licensed_image_source',
            'status': 'ready',
            'created_at': int(time.time()),
        }
        posts.append(post)

    state.setdefault('image_posts', []).extend(posts)
    daily.setdefault('images', [])
    daily['images'].extend([p['source_item'] for p in posts])
    save(STATE, state)
    print(f'Generated {len(posts)} separate image cards from licensed image sources for {today}')
    for post in posts:
        print(post['image'])




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--daily', action='store_true', help='Generate up to 9 professional daily image cards')
    args = ap.parse_args()
    if args.daily:
        generate_daily_images()
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
