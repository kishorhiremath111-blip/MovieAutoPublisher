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


def card(frame, title, subtitle, out, badge=None, dark=False, question=None, source=None):
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
    accent = (47, 202, 236)
    white = 'white'
    black = 'black'

    meta_f = font(27, True)
    title_f = font(64, True)
    sub_f = font(31, True)
    q_f = font(30, True)
    tiny_f = font(21, False)

    # Editorial header: not a fake quotation or fake attribution.
    d.text((margin, 42), 'TASK EARN • TRENDING', font=meta_f, fill=accent)
    if badge:
        badge_w = d.textbbox((0, 0), badge, font=meta_f)[2] + 28
        d.rounded_rectangle(
            (1080 - margin - badge_w, 32, 1080 - margin, 94),
            radius=18, fill=(0, 0, 0, 180), outline=white, width=2
        )
        d.text((1080 - margin - badge_w + 14, 46), badge, font=meta_f, fill=white)

    # Quote marks are purely a visual device; do not imply a quotation.
    d.text((margin, 685), '“', font=font(92, True), fill=accent)

    y = 770
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
    state = load(STATE, {'processed': {}, 'queue': [], 'image_posts': []})
    today = time.strftime('%Y-%m-%d')
    target_count = int(load(CONFIG, {}).get('daily_image_posts', 9))
    target_count = max(1, min(9, target_count))
    if any(x.get('date') == today for x in state.get('image_posts', [])):
        print(f'Images already generated for {today}')
        return

    item_id, video, info = choose_source(
        state,
        recent_days=int(load(CONFIG, {}).get('viral_no_repeat_days', 30))
    )
    if not video:
        print('Daily images: no fresh unused authorized source; skipping.')
        return

    dur = duration(video)
    work = OUT / today
    cfg = load(CONFIG, {})
    scenes = detect_scene_times(video, float(cfg.get('scene_threshold', 0.35)))
    silence = detect_silence_ranges(video, float(cfg.get('silence_db', -34)))
    ranked = rank_highlight_windows(
        dur, scenes, count=max(12, target_count * 2),
        clip_seconds=float(cfg.get('highlight_clip_seconds', 42)),
        silence_ranges=silence,
        min_gap_seconds=float(cfg.get('min_highlight_gap_seconds', 12)),
    )
    ranked = sorted(ranked, key=lambda x: x[2], reverse=True)
    points = []
    for s0, e0, score in ranked:
        point = min(dur - 0.2, max(0.2, (s0 + e0) / 2.0))
        if all(abs(point - old) >= 8 for old in points):
            points.append(point)
        if len(points) >= target_count:
            break
    if not points:
        points = [dur * (i + 1) / (target_count + 1) for i in range(target_count)]

    frames = []
    for i, point in enumerate(points, 1):
        frame = work / f'frame_{i:02d}.jpg'
        extract_frame(video, point, frame)
        frames.append(frame)

    title = info.get('detected_title') or info.get('title') or item_id
    typ = str(info.get('type', '')).lower() or 'movie'
    adult = bool(info.get('adult', False))
    caption_sets = {
        'anime': [
            ('POWER FRAME', 'Peak anime energy.'), ('BATTLE MOOD', 'This frame goes hard.'),
            ('CHARACTER MOMENT', 'One frame, full aura.'), ('WAIT FOR IT', 'The setup is everything.'),
            ('PEAK MOMENT', 'That timing though.'), ('DARK MOOD', 'The mood just changed.'),
            ('FAN FAVOURITE', 'Instant replay material.'), ('STORY DROP', 'There is more behind this scene.'),
            ('FINAL LOOK', 'Worth the pause.')
        ],
        'series': [
            ('SCENE OF THE DAY', 'One scene. Full mood.'), ('PLOT MOOD', 'When the episode takes a turn.'),
            ('BEST FRAME', 'The frame says enough.'), ('WAIT FOR IT', 'The setup matters.'),
            ('DARK MOOD', 'The atmosphere is different here.'), ('CHARACTER MOMENT', 'A small moment, big impact.'),
            ('THAT LOOK', 'You know the scene.'), ('EPISODE ENERGY', 'This is the vibe.'),
            ('REPLAY THIS', 'Worth another look.')
        ],
        'movie': [
            ('BEST FRAME', 'Cinema in one frame.'), ('SCENE MOOD', 'The atmosphere says it all.'),
            ('WAIT FOR IT', 'The setup is everything.'), ('ICONIC MOMENT', 'A frame worth stopping for.'),
            ('DARK MOOD', 'When the tone shifts.'), ('CHARACTER MOMENT', 'The look says enough.'),
            ('CINEMATIC', 'Shot. Mood. Moment.'), ('STORY BEAT', 'A small detail can change everything.'),
            ('REPLAY THIS', 'One more look.')
        ]
    }
    captions = caption_sets.get(typ, caption_sets['movie'])
    posts = []
    for idx, frame in enumerate(frames, 1):
        cap, sub = captions[(idx - 1) % len(captions)]
        out = work / f'{safe_name(item_id)}_{idx:02d}.jpg'
        q = 'Would you share this with a friend?' if cap != 'DARK MOOD' else 'Too dark, or exactly your kind of humour?'
        card(frame, f'{title} • {cap}', sub, out, badge=('18+' if adult else None), dark=(cap == 'DARK MOOD'), question=q, source='Authorized source video')
        posts.append({
            'id': f'{today}-{item_id}-{idx}',
            'date': today,
            'category': cap.lower(),
            'image': str(out.relative_to(ROOT)),
            'caption': f'{title} • {cap}

{sub}',
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
    ap.add_argument('--daily', action='store_true', help='Generate up to 9 professional daily image cards')
    args = ap.parse_args()
    if args.daily:
        generate_daily_images()
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
