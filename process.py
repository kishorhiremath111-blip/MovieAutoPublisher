#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from scene_tools import detect_scene_times, detect_silence_ranges, rank_highlight_windows

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
    out = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
               '-of', 'default=noprint_wrappers=1:nokey=1', str(path)])
    return float(out.strip())


def ffprobe_media_title(path):
    try:
        out = run(['ffprobe', '-v', 'error', '-show_entries', 'format_tags=title',
                   '-of', 'default=noprint_wrappers=1:nokey=1', str(path)])
        title = out.strip()
        return title if title and title.lower() not in ('unknown', 'untitled') else ''
    except Exception:
        return ''


def check_ffmpeg():
    for x in ('ffmpeg', 'ffprobe'):
        if shutil.which(x) is None:
            raise RuntimeError(f'{x} not found. Install FFmpeg in Termux first.')


def safe_name(s):
    return ''.join(c if c.isalnum() or c in ' ._-()' else '_' for c in s).strip() or 'video'


def infer_title(source, item):
    configured = str(item.get('title', '')).strip()
    if configured and configured.lower() not in ('auto', 'detect', 'unknown'):
        return configured
    media_title = ffprobe_media_title(source)
    if media_title:
        return media_title
    stem = source.stem
    stem = re.sub(r'(?i)[._ -]*s\d{1,2}[._ -]*e\d{1,3}', '', stem)
    stem = re.sub(r'(?i)[._ -]*part\s*\d+', '', stem)
    stem = re.sub(r'[_\.]+', ' ', stem)
    return re.sub(r'\s+', ' ', stem).strip() or 'Untitled Video'


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


def make_title(item, part=None, title_override=None):
    title = (title_override or item.get('_detected_title') or item.get('title', '')).strip()
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


def style_filters(style):
    filters = []
    if style == 'funny':
        filters += ['eq=saturation=1.08:contrast=1.04', 'unsharp=5:5:0.28:5:5:0.0']
    elif style == 'dark':
        filters += ['eq=brightness=-0.04:contrast=1.10:saturation=0.82', 'vignette=PI/5']
    return filters


def apply_manual_censors(vf, item):
    for box in item.get('censor_boxes', []):
        start = float(box.get('start', 0))
        end = float(box.get('end', 999999))
        x = float(box.get('x', 0)); y = float(box.get('y', 0))
        w = float(box.get('w', 20)); h = float(box.get('h', 20))
        enable = f'between(t,{start},{end})'
        vf.append(f"boxblur=luma_radius=12:luma_power=2:enable='{enable}'")
        vf.append(
            f"drawbox=x=iw*{x/100:.5f}:y=ih*{y/100:.5f}:w=iw*{w/100:.5f}:h=ih*{h/100:.5f}:"
            f"color=black@0.08:t=fill:enable='{enable}'"
        )
    return vf


def split_video(source, out_dir, item, duration, cfg):
    out_dir.mkdir(parents=True, exist_ok=True)
    max_seconds = float(cfg['max_single_video_hours']) * 3600
    if duration <= max_seconds:
        return [(1, source)]
    parts = int(cfg.get('split_parts', 2))
    if parts != 2:
        parts = 2
    segment = duration / 2.0
    results = []
    for i in range(2):
        start = i * segment
        length = segment if i == 0 else duration - start
        out = out_dir / f'{safe_name(item["_detected_title"])}_part{i+1}.mp4'
        run([
            'ffmpeg','-y','-ss',f'{start:.3f}','-i',str(source),'-t',f'{length:.3f}',
            '-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','veryfast','-b:v',cfg['video_bitrate'],
            '-c:a','aac','-b:a',cfg['audio_bitrate'],'-movflags','+faststart',str(out)
        ])
        results.append((i+1, out))
    return results


def escape_drawtext(text):
    return (str(text).replace('\\', '\\\\').replace("'", "\\'").replace(':', '\\:'))


def create_banner(thumbnail, item, part, out_dir):
    out = out_dir / f'{safe_name(item["_detected_title"])}_part{part}_thumbnail.jpg'
    text = escape_drawtext(make_overlay_text(item, part))
    title = escape_drawtext(make_title(item, part))
    vf = (
        "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
        "drawbox=x=0:y=0:w=iw:h=130:color=black@0.62:t=fill,"
        f"drawtext=text='{title}':x=40:y=24:fontsize=42:fontcolor=white,"
        f"drawtext=text='{text}':x=40:y=82:fontsize=28:fontcolor=white"
    )
    run(['ffmpeg','-y','-i',str(thumbnail),'-vf',vf,'-frames:v','1','-q:v','2',str(out)])
    return out


def analyze_highlights(video, duration, cfg):
    threshold = float(cfg.get('scene_threshold', 0.35))
    clip_seconds = float(cfg.get('highlight_clip_seconds', 42))
    max_candidates = int(cfg.get('max_highlight_clips', 12))
    gap = float(cfg.get('min_highlight_gap_seconds', 12))
    silence_db = float(cfg.get('silence_db', -34))
    scenes = detect_scene_times(video, threshold)
    silence = detect_silence_ranges(video, silence_db)
    ranked = rank_highlight_windows(
        duration, scenes, count=max_candidates, clip_seconds=clip_seconds,
        silence_ranges=silence, min_gap_seconds=gap,
    )
    if not ranked:
        start = max(0.0, (duration - min(clip_seconds, duration)) / 2.0)
        ranked = [(start, min(duration, start + clip_seconds), 0.25)]
    return ranked


def extract_clip(video, start, end, out, width, height, item, style='clean'):
    out.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, end - start)
    vf = [f'scale={width}:{height}:force_original_aspect_ratio=increase', f'crop={width}:{height}']
    vf.extend(style_filters(style))
    apply_manual_censors(vf, item)
    run([
        'ffmpeg','-y','-ss',f'{start:.3f}','-i',str(video),'-t',f'{duration:.3f}',
        '-vf',','.join(vf),'-c:v','libx264','-preset','veryfast','-b:v',item['_cfg']['video_bitrate'],
        '-c:a','aac','-b:a',item['_cfg']['audio_bitrate'],'-movflags','+faststart',str(out)
    ])
    return out


def concat_clips(clips, out, cfg, music=None):
    concat_file = out.parent / 'concat.txt'
    with concat_file.open('w', encoding='utf-8') as f:
        for clip in clips:
            safe = str(clip).replace("'", "'\\''")
            f.write(f"file '{safe}'\n")
    temp = out.parent / 'concat_video.mp4'
    run([
        'ffmpeg','-y','-f','concat','-safe','0','-i',str(concat_file),
        '-c','copy','-movflags','+faststart',str(temp)
    ])
    if music and music.exists():
        run([
            'ffmpeg','-y','-i',str(temp),'-stream_loop','-1','-i',str(music),
            '-filter_complex',
            '[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]',
            '-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a',cfg['audio_bitrate'],
            '-shortest','-movflags','+faststart',str(out)
        ])
        temp.unlink(missing_ok=True)
    else:
        temp.replace(out)
    concat_file.unlink(missing_ok=True)
    return out


def make_highlight_compilation(video, item, part, out_dir, cfg):
    duration = ffprobe_duration(video)
    ranked = analyze_highlights(video, duration, cfg)
    target = float(cfg.get('long_highlight_target_seconds', 480))
    min_clip = float(cfg.get('highlight_min_clip_seconds', 20))
    max_clips = int(cfg.get('max_highlight_clips', 12))
    selected = []
    total = 0.0
    # Ranked list is strongest-first. Keep strongest non-overlapping clips until target is reached.
    for start, end, score in sorted(ranked, key=lambda x: x[2], reverse=True):
        length = end - start
        if length < min_clip:
            continue
        if selected and total + length > target * 1.12:
            continue
        selected.append((start, end, score))
        total += length
        if len(selected) >= max_clips or total >= target:
            break
    if not selected:
        selected = ranked[:1]

    work = out_dir / 'clips'
    work.mkdir(parents=True, exist_ok=True)
    clips = []
    for idx, (start, end, score) in enumerate(selected, 1):
        clip = work / f'clip_{idx:02d}.mp4'
        extract_clip(video, start, end, clip, int(cfg['output_width']), int(cfg['output_height']), item, item.get('edit_style','clean'))
        clips.append(clip)

    title = make_title(item, part if part > 1 else None)
    out = out_dir / f'{safe_name(title)}_HIGHLIGHTS.mp4'
    music = None
    music_rel = item.get('background_music') or cfg.get('background_music_file')
    if music_rel:
        candidate = ROOT / music_rel
        if candidate.exists():
            music = candidate
    concat_clips(clips, out, cfg, music=music)
    return out, selected


def make_short(video, item, part, out_dir, cfg):
    out_dir.mkdir(parents=True, exist_ok=True)
    base_title = make_title(item, part if part > 1 else None)
    out = out_dir / f'{safe_name(base_title)}_SHORT.mp4'
    duration = ffprobe_duration(video)
    target_len = min(float(cfg['short_duration_seconds']), duration)
    ranked = analyze_highlights(video, duration, cfg)
    start, end, score = max(ranked, key=lambda x: x[2])
    if end - start > target_len:
        center = (start + end) / 2.0
        start = max(0.0, center - target_len / 2.0)
        end = min(duration, start + target_len)
    else:
        target_len = end - start
    vf = [
        'scale=1080:1920:force_original_aspect_ratio=increase',
        'crop=1080:1920',
    ]
    vf.extend(style_filters(item.get('edit_style','clean')))
    overlay = make_overlay_text(item, part if part > 1 else None)
    if overlay:
        vf.append('drawbox=x=25:y=25:w=430:h=68:color=black@0.55:t=fill')
        vf.append(f"drawtext=text='{escape_drawtext(overlay)}':x=42:y=44:fontsize=30:fontcolor=white")
    apply_manual_censors(vf, item)
    run([
        'ffmpeg','-y','-ss',f'{start:.3f}','-i',str(video),'-t',f'{target_len:.3f}',
        '-vf',','.join(vf),'-c:v','libx264','-preset','veryfast','-b:v',cfg['video_bitrate'],
        '-c:a','aac','-b:a',cfg['audio_bitrate'],'-movflags','+faststart',str(out)
    ])
    return out, {'start': start, 'end': end, 'score': score}


def process_part(video, thumbnail, item, part, out_dir, cfg):
    out_dir.mkdir(parents=True, exist_ok=True)
    highlight, selected = make_highlight_compilation(video, item, part, out_dir, cfg)
    thumb = create_banner(thumbnail, item, part, out_dir)
    short, short_info = make_short(video, item, part, out_dir, cfg)
    title = make_title(item, part if part > 1 else None)
    return highlight, short, thumb, title, selected, short_info


def main():
    ap = argparse.ArgumentParser(description='Licensed MovieAutoPublisher processor')
    ap.add_argument('--metadata', default='metadata.json')
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
        if item_id in state.get('processed', {}):
            print(f'SKIP already processed: {item_id}')
            continue
        item['_detected_title'] = infer_title(source, item)
        item['_cfg'] = cfg
        duration = ffprobe_duration(source)
        work = ROOT / 'output' / safe_name(item_id)
        raw_parts = split_video(source, work / 'parts', item, duration, cfg)
        produced = []
        for part, raw in raw_parts:
            video, short, banner, title, selected, short_info = process_part(raw, thumb, item, part, work / 'final', cfg)
            produced.append({
                'part': part,
                'video': str(video.relative_to(ROOT)),
                'short': str(short.relative_to(ROOT)),
                'thumbnail': str(banner.relative_to(ROOT)),
                'title': title,
                'edit_style': item.get('edit_style','clean'),
                'adult_badge': bool(item.get('adult', False)),
                'description': item.get('description',''),
                'tags': item.get('tags',[]),
                'privacy_status': item.get('privacy_status','private'),
                'selected_highlights': [
                    {'start': round(s, 2), 'end': round(e, 2), 'score': round(score, 4)}
                    for s, e, score in selected
                ],
                'short_highlight': {k: round(v, 2) for k, v in short_info.items()},
            })
        state.setdefault('processed', {})[item_id] = {
            'duration_seconds': duration,
            'detected_title': item['_detected_title'],
            'source': str(source.relative_to(ROOT)),
            'type': item.get('type', 'content'),
            'created_at': int(time.time()),
            'outputs': produced,
        }
        state.setdefault('queue', []).extend([{**x, 'item_id': item_id, 'status': 'ready'} for x in produced])
        save_json(STATE, state)
        print(f'DONE: {item_id} -> {len(produced)} daily upload item(s) queued')


if __name__ == '__main__':
    main()
