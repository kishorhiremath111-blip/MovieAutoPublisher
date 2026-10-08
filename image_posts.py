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

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

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


def card(frame, title, subtitle, out, badge=None, dark=False):
    im = Image.open(frame).convert('RGB').resize((1080, 1350))
    # Cinematic treatment: contrast, slight blur behind text, dark lower gradient.
    im = ImageEnhance.Contrast(im).enhance(1.08)
    im = ImageEnhance.Color(im).enhance(1.04 if not dark else 0.86)
    overlay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(700, 1350):
        alpha = int(215 * ((y - 700) / 650))
        od.line((0, y, 1080, y), fill=(0, 0, 0, alpha))
    im = Image.alpha_composite(im.convert('RGBA'), overlay).convert('RGB')
    d = ImageDraw.Draw(im)
    title_f = font(66, True)
    sub_f = font(34, False)
    badge_f = font(28, True)

    y = 885
    for line in wrap(d, title, title_f, 950):
        d.text((60, y), line, font=title_f, fill='white', stroke_width=2, stroke_fill='black')
        y += 78
    y += 8
    for line in wrap(d, subtitle, sub_f, 930):
        d.text((62, y), line, font=sub_f, fill=(235, 235, 235), stroke_width=1, stroke_fill='black')
        y += 44
    if badge:
        box = (60, 65, 60 + d.textbbox((0, 0), badge, font=badge_f)[2] + 36, 125)
        d.rounded_rectangle(box, radius=18, fill=(0, 0, 0, 190), outline='white', width=2)
        d.text((78, 79), badge, font=badge_f, fill='white')
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=94, optimize=True)
    return out


def choose_source(state):
    # Prefer the first processed item with a source path in metadata.
    for item_id, info in state.get('processed', {}).items():
        outputs = info.get('outputs', [])
        if outputs:
            # Recover original source through state metadata when available.
            source = info.get('source')
            if source and (ROOT / source).exists():
                return item_id, ROOT / source, info
    # Backward-compatible fallback: inspect metadata.json.
    meta = load(ROOT / 'metadata.json', {'items': []})
    for item in meta.get('items', []):
        if item.get('licensed') and (ROOT / item.get('source', '')).exists():
            return item['id'], ROOT / item['source'], item
    return None, None, None


def generate_two():
    state = load(STATE, {'processed': {}, 'queue': [], 'image_posts': []})
    today = time.strftime('%Y-%m-%d')
    if any(x.get('date') == today for x in state.get('image_posts', [])):
        print(f'Images already generated for {today}')
        return

    item_id, video, info = choose_source(state)
    if not video:
        raise SystemExit('No licensed input video found. Put an authorized video in input/videos/ first.')

    dur = duration(video)
    # Two different moments so the daily pair does not look duplicated.
    points = [dur * 0.32, dur * 0.68] if dur > 20 else [dur * 0.35, dur * 0.65]
    work = OUT / today
    frames = []
    for i, point in enumerate(points, 1):
        frame = work / f'frame_{i}.jpg'
        extract_frame(video, point, frame)
        frames.append(frame)

    title = info.get('detected_title') or info.get('title') or item_id
    typ = str(info.get('type', '')).lower()
    if not typ:
        typ = 'content'

    captions = [
        (f'{title} • BEST MOMENT', 'The kind of scene you replay twice.', 'MOMENT'),
        (f'{title} • MOOD CHECK', 'When the scene says everything without saying much.', 'MOOD'),
    ]
    # Category-aware copy without pretending the system knows a scene is truly viral.
    if typ == 'anime':
        captions = [
            (f'{title} • ANIME MOMENT', 'That frame hits different. ⚡', 'ANIME'),
            (f'{title} • MOOD', 'Peak anime energy. 🔥', 'ANIME'),
        ]
    elif typ == 'series':
        captions = [
            (f'{title} • SCENE OF THE DAY', 'One scene. Full mood.', 'SERIES'),
            (f'{title} • DARK MOOD', 'When the episode takes a turn.', 'DARK'),
        ]

    posts = []
    for idx, (cap, sub, badge) in enumerate(captions, 1):
        out = work / f'{safe_name(item_id)}_{idx}.jpg'
        card(frames[idx - 1], cap, sub, out, badge=badge, dark=(badge == 'DARK'))
        posts.append({
            'id': f'{today}-{item_id}-{idx}',
            'date': today,
            'category': badge.lower(),
            'image': str(out.relative_to(ROOT)),
            'caption': cap + '\n\n' + sub,
            'source_item': item_id,
            'status': 'ready',
            'created_at': int(time.time()),
        })

    state.setdefault('image_posts', []).extend(posts)
    # Store source so future runs can reuse processed state safely.
    if item_id in state.get('processed', {}):
        state['processed'][item_id]['source'] = str(video.relative_to(ROOT))
    save(STATE, state)
    print(f'Generated {len(posts)} image posts for {today}')
    for p in posts:
        print(p['image'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--daily', action='store_true', help='Generate exactly two daily image cards')
    args = ap.parse_args()
    if args.daily:
        generate_two()
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
