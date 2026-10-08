#!/usr/bin/env python3
import argparse, json, math, os, shutil, subprocess, sys, time
from scene_tools import detect_scene_times, choose_highlight_windows
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config' / 'config.json'
STATE = ROOT / 'state' / 'state.json'


def load_json(path, default):
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def run(cmd):
    print('>', ' '.join(map(str, cmd)))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        print(p.stdout)
        raise RuntimeError('Command failed')
    return p.stdout


def ffprobe_duration(path):
    out = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)])
    return float(out.strip())


def check_ffmpeg():
    for x in ('ffmpeg', 'ffprobe'):
        if shutil.which(x) is None:
            raise RuntimeError(f'{x} not found. Install FFmpeg in Termux first.')


def safe_name(s):
    return ''.join(c if c.isalnum() or c in ' ._-()' else '_' for c in s).strip() or 'video'


def validate_item(item):
    if not item.get('licensed'):
        raise RuntimeError(f"{item.get('id','unknown')}: licensed=true is required")
    source = ROOT / item['source']
    thumb = ROOT / item['thumbnail']
    if not source.exists():
        raise FileNotFoundError(source)
    if not thumb.exists():
        raise FileNotFoundError(thumb)
    if item.get('type') not in ('movie', 'series', 'anime'):
        raise RuntimeError('type must be movie, series or anime')
    return source, thumb


def make_title(item, part=None):
    title = item['title'].strip()
    typ = item['type']
    if typ in ('series', 'anime'):
        season = int(item.get('season', 1))
        episode = int(item.get('episode', 1))
        base = f'{title} • S{season:02d} • E{episode:02d}'
    else:
        base = title
    if part is not None:
        base += f' • PART {part}'
    return base


def make_overlay_text(item, part=None):
    lines = []
    if item.get('adult'):
        lines.append('18+')
    typ = item['type']
    if typ in ('series', 'anime'):
        lines.append(f"S{int(item.get('season',1)):02d} • E{int(item.get('episode',1)):02d}")
    if part is not None:
        lines.append(f'PART {part}')
    return ' • '.join(lines)


def style_filters(style, item, part, cfg):
    """Return optional presentation filters. These are cosmetic edits only."""
    filters = []
    if style == 'funny':
        filters += [
            'eq=saturation=1.08:contrast=1.04',
            'unsharp=5:5:0.35:5:5:0.0'
        ]
    elif style == 'dark':
        filters += [
            'eq=brightness=-0.04:contrast=1.10:saturation=0.82',
            'vignette=PI/5'
        ]
    return filters


def apply_manual_censors(vf, item):
    """Apply user-specified blur rectangles. No automatic sexual-content classifier is assumed.

    Each box: {start,end,x,y,w,h}. Coordinates are percentages 0..100."""
    for box in item.get('censor_boxes', []):
        start=float(box.get('start', 0)); end=float(box.get('end', 999999))
        x=float(box.get('x', 0)); y=float(box.get('y', 0)); w=float(box.get('w', 20)); h=float(box.get('h', 20))
        enable=f'between(t,{start},{end})'
        vf.append(f"boxblur=luma_radius=12:luma_power=2:enable='{enable}'")
        vf.append(f"drawbox=x=iw*{x/100:.5f}:y=ih*{y/100:.5f}:w=iw*{w/100:.5f}:h=ih*{h/100:.5f}:color=black@0.08:t=fill:enable='{enable}'")
    return vf


def split_video(source, out_dir, item, duration, cfg):
    out_dir.mkdir(parents=True, exist_ok=True)
    max_seconds = cfg['max_single_video_hours'] * 3600
    if duration <= max_seconds:
        return [(1, source)]
    parts = int(cfg.get('split_parts', 2))
    segment = duration / parts
    results = []
    for i in range(parts):
        start = i * segment
        length = segment if i < parts - 1 else duration - start
        out = out_dir / f'{safe_name(item["title"])}_part{i+1}.mp4'
        cmd = [
            'ffmpeg','-y','-ss',f'{start:.3f}','-i',str(source),'-t',f'{length:.3f}',
            '-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','veryfast','-b:v',cfg['video_bitrate'],
            '-c:a','aac','-b:a',cfg['audio_bitrate'],'-movflags','+faststart',str(out)
        ]
        run(cmd)
        results.append((i+1, out))
    return results


def create_banner(thumbnail, item, part, out_dir):
    # Uses the supplied/original thumbnail as the base. No external thumbnail is fetched.
    out = out_dir / f'{safe_name(item["title"])}_part{part}_thumbnail.jpg'
    text = make_overlay_text(item, part)
    title = make_title(item, part)
    vf = (
        "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
        "drawbox=x=0:y=0:w=iw:h=120:color=black@0.62:t=fill,"
        f"drawtext=text='{title.replace(chr(39), chr(92)+chr(39))}':x=40:y=25:fontsize=42:fontcolor=white:enable='between(t,0,1)',"
        f"drawtext=text='{text.replace(chr(39), chr(92)+chr(39))}':x=40:y=78:fontsize=28:fontcolor=white:enable='between(t,0,1)'"
    )
    run(['ffmpeg','-y','-i',str(thumbnail),'-vf',vf,'-frames:v','1','-q:v','2',str(out)])
    return out


def process_part(video, thumbnail, item, part, out_dir, cfg):
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = ffprobe_duration(video)
    title = make_title(item, part if part > 1 or duration > cfg['max_single_video_hours']*3600 else None)
    overlay = make_overlay_text(item, part if part > 1 else None)
    out = out_dir / f'{safe_name(title)}.mp4'
    style = item.get('edit_style', 'clean')
    filters = [
        'scale=1920:1080:force_original_aspect_ratio=decrease',
        'pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
    ]
    filters.extend(style_filters(style, item, part, cfg))
    if overlay:
        filters.append("drawbox=x=20:y=20:w=520:h=68:color=black@0.55:t=fill")
        filters.append(f"drawtext=text='{overlay.replace(chr(39), chr(92)+chr(39))}':x=35:y=39:fontsize=30:fontcolor=white")
    filters = apply_manual_censors(filters, item)
    run(['ffmpeg','-y','-i',str(video),'-vf',','.join(filters),'-c:v','libx264','-preset','veryfast','-b:v',cfg['video_bitrate'],'-c:a','aac','-b:a',cfg['audio_bitrate'],'-movflags','+faststart',str(out)])
    thumb = create_banner(thumbnail, item, part, out_dir)
    return out, thumb, title


def make_short(video, item, part, out_dir, cfg):
    out_dir.mkdir(parents=True, exist_ok=True)
    base_title = make_title(item, part)
    out = out_dir / f'{safe_name(base_title)}_SHORT.mp4'
    duration = ffprobe_duration(video)
    length = min(float(cfg['short_duration_seconds']), duration)
    # Prefer scene-change highlights. If analysis fails, use the middle of the source.
    windows = []
    if cfg.get('auto_highlight', True):
        try:
            scenes = detect_scene_times(video, float(cfg.get('scene_threshold', 0.40)))
            windows = choose_highlight_windows(duration, scenes, count=1, clip_seconds=length)
        except Exception as exc:
            print('Highlight analysis unavailable:', exc)
    start = windows[0][0] if windows else max(0.0, (duration - length) / 2.0)
    vf = 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920'
    style = item.get('edit_style', 'clean')
    extra = style_filters(style, item, part, cfg)
    if extra:
        vf += ',' + ','.join(extra)
    overlay = make_overlay_text(item, part)
    if overlay:
        vf += ',drawbox=x=25:y=25:w=420:h=65:color=black@0.55:t=fill'
        vf += f",drawtext=text='{overlay.replace(chr(39), chr(92)+chr(39))}':x=40:y=42:fontsize=30:fontcolor=white"
    censor_filters=[]
    apply_manual_censors(censor_filters, item)
    if censor_filters:
        vf += ',' + ','.join(censor_filters)
    run(['ffmpeg','-y','-ss',f'{start:.3f}','-i',str(video),'-t',f'{length:.3f}','-vf',vf,'-c:v','libx264','-preset','veryfast','-b:v',cfg['video_bitrate'],'-c:a','aac','-b:a',cfg['audio_bitrate'],'-movflags','+faststart',str(out)])
    return out

def main():
    ap = argparse.ArgumentParser(description='Licensed MovieAutoPublisher processor')
    ap.add_argument('--metadata', default='metadata.example.json')
    ap.add_argument('--id', help='process one metadata item')
    args = ap.parse_args()
    check_ffmpeg()
    cfg = load_json(CONFIG, {})
    meta = load_json(ROOT / args.metadata, {'items': []})
    state = load_json(STATE, {'processed': {}, 'queue': []})
    items = meta.get('items', [])
    if args.id:
        items = [x for x in items if x.get('id') == args.id]
        if not items:
            raise SystemExit(f'No item found: {args.id}')

    for item in items:
        source, thumb = validate_item(item)
        item_id = item['id']
        if item_id in state['processed']:
            print(f'SKIP already processed: {item_id}')
            continue
        duration = ffprobe_duration(source)
        work = ROOT / 'output' / safe_name(item_id)
        raw_parts = split_video(source, work / 'parts', item, duration, cfg)
        produced = []
        for part, raw in raw_parts:
            video, banner, title = process_part(raw, thumb, item, part, work / 'final', cfg)
            short = make_short(video, item, part, work / 'final', cfg)
            produced.append({'part': part, 'video': str(video.relative_to(ROOT)), 'short': str(short.relative_to(ROOT)), 'thumbnail': str(banner.relative_to(ROOT)), 'title': title, 'edit_style': item.get('edit_style','clean'), 'adult_badge': bool(item.get('adult', False)), 'description': item.get('description',''), 'tags': item.get('tags',[]), 'privacy_status': item.get('privacy_status','private')})
        state['processed'][item_id] = {'duration_seconds': duration, 'created_at': int(time.time()), 'outputs': produced}
        state['queue'].extend([{**x, 'item_id': item_id, 'status': 'ready'} for x in produced])
        save_json(STATE, state)
        print(f'DONE: {item_id}')

if __name__ == '__main__':
    main()
