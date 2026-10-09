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
from pro_editor import choose_profile, filters as pro_filters, audio_filters as pro_audio_filters
from caption_design import caption_line, palette

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
    if item.get('licensed') is not True:
        raise RuntimeError(f"{item.get('id','unknown')}: licensed=true is required")
    cfg = load_json(CONFIG, {})
    language = str(item.get('audio_language') or '').strip().lower()
    if language not in set(cfg.get('allowed_audio_languages', ['hi', 'en'])):
        raise RuntimeError(
            f"{item.get('id','unknown')}: audio_language must be explicitly set to 'hi' or 'en'; "
            "language is never guessed from the title."
        )
    if cfg.get('require_verified_audio_language', True) and item.get('audio_language_verified') is not True:
        raise RuntimeError(
            f"{item.get('id','unknown')}: set audio_language_verified=true only after checking "
            "the actual dialogue/audio track."
        )
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


def analyze_highlights(video, duration, cfg, item=None):
    threshold = float(cfg.get('scene_threshold', 0.35))
    clip_seconds = float(cfg.get('highlight_clip_seconds', 42))
    max_candidates = max(60, int(cfg.get('max_highlight_clips', 12)) * 12)
    gap = float(cfg.get('min_highlight_gap_seconds', 12))
    silence_db = float(cfg.get('silence_db', -34))
    scenes = detect_scene_times(video, threshold)
    silence = detect_silence_ranges(video, silence_db)
    ranked = rank_highlight_windows(
        duration, scenes, count=max_candidates, clip_seconds=clip_seconds,
        silence_ranges=silence, min_gap_seconds=gap,
    )
    used = (item or {}).get('_used_windows', [])
    if used:
        fresh = []
        for start, end, score in ranked:
            length = max(0.1, end - start)
            repeat = False
            for ustart, uend in used:
                overlap = max(0.0, min(end, uend) - max(start, ustart))
                if overlap >= min(10.0, length * 0.25):
                    repeat = True
                    break
            if not repeat:
                fresh.append((start, end, score))
        ranked = fresh
    if not ranked and not used:
        start = max(0.0, (duration - min(clip_seconds, duration)) / 2.0)
        ranked = [(start, min(duration, start + clip_seconds), 0.25)]
    return ranked


def previously_published_windows(state, source_rel, today, lookback_days=30):
    """Read only scenes from prior uploads, not merely generated-but-unused exports."""
    from datetime import date, timedelta
    try:
        current = date.fromisoformat(today)
    except ValueError:
        current = date.today()
    cutoff = current - timedelta(days=max(1, int(lookback_days)))
    processed = state.get('processed', {})
    windows = []
    for stamp, daily in state.get('daily', {}).items():
        try:
            day = date.fromisoformat(str(stamp)[:10])
        except ValueError:
            continue
        if not (cutoff <= day < current):
            continue
        roles = (
            ('long', 'selected_highlights'),
            ('short', 'short_highlight'),
            ('reel', 'short_highlight'),
        )
        for role, field in roles:
            for variant_id in daily.get(role, []):
                rec = processed.get(str(variant_id), {})
                if str(rec.get('source') or '') != str(source_rel):
                    continue
                for output in rec.get('outputs', []):
                    if field == 'selected_highlights':
                        for w in output.get(field, []):
                            try:
                                windows.append((float(w['start']), float(w['end'])))
                            except (KeyError, TypeError, ValueError):
                                pass
                    else:
                        w = output.get(field) or {}
                        try:
                            windows.append((float(w['start']), float(w['end'])))
                        except (KeyError, TypeError, ValueError):
                            pass
    return windows


def extract_clip(video, start, end, out, width, height, item, style='clean', overlay_text=None):
    out.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, end - start)
    cfg = item.get('_cfg', {})
    if cfg.get('pro_edit_enabled', True):
        profile = choose_profile(item, duration=duration, short=False)
        vf = pro_filters(profile, width, height)
        af = pro_audio_filters(profile)
    else:
        vf = [f'scale={width}:{height}:force_original_aspect_ratio=increase', f'crop={width}:{height}']
        vf.extend(style_filters(style))
        af = None
    if cfg.get('brand_watermark_enabled', True):
        brand = escape_drawtext(cfg.get('brand_watermark_text', 'VYROX-2008'))
        vf.append(f"drawtext=text='{brand}':x=w-text_w-34:y=h-text_h-34:fontsize=28:fontcolor=white@0.92:box=1:boxcolor=black@0.48:boxborderw=10:borderw=1:bordercolor=black@0.55:fix_bounds=true")
    apply_manual_censors(vf, item)
    if overlay_text and cfg.get('show_scene_captions', False):
        # Optional VIBEFRAME banner; disabled by default when show_scene_captions=false.
        clean_text = re.sub(r"[\\U0001F300-\\U0001FAFF\\U00002600-\\U000027BF]", "", str(overlay_text)).strip()[:54]
        vf.append('drawbox=x=0:y=34:w=iw:h=88:color=white@1.0:t=fill')
        vf.append(f"drawtext=text='{escape_drawtext(clean_text)}':x=(w-text_w)/2:y=58:fontsize=32:fontcolor=black:fix_bounds=true")
    run([
        'ffmpeg','-y','-ss',f'{start:.3f}','-i',str(video),'-t',f'{duration:.3f}',
        '-vf',','.join(vf),'-c:v','libx264','-preset','veryfast','-b:v',item['_cfg']['video_bitrate'],
        '-af',af if af else 'loudnorm=I=-14:TP=-1.5:LRA=11',
        '-c:a','aac','-b:a',item['_cfg']['audio_bitrate'],'-movflags','+faststart',str(out)
    ])
    return out


def resolve_music(item, cfg):
    """Choose a local track from the configured licensed mood library."""
    mood = str(item.get('music_mood') or item.get('edit_style') or 'cinematic').lower()
    library = cfg.get('background_music_by_mood', {})
    options = [item.get('background_music'), library.get(mood), cfg.get('background_music_file')]
    seen = set()
    for music_rel in options:
        if not music_rel or str(music_rel) in seen:
            continue
        seen.add(str(music_rel))
        candidate = (ROOT / str(music_rel)).resolve()
        if ROOT.resolve() not in candidate.parents:
            continue
        if candidate.is_file():
            print(f'MUSIC: mood={mood}; track={candidate.relative_to(ROOT)}; dialogue-aware ducking enabled')
            return candidate
    print(f'MUSIC: no local licensed track for mood={mood}; original audio only')
    return None


def mix_short_music(short_path, item, cfg):
    music = resolve_music(item, cfg)
    if not music:
        return short_path
    temp = short_path.with_name(short_path.stem + '_music_tmp.mp4')
    run([
        'ffmpeg','-y','-i',str(short_path),'-stream_loop','-1','-i',str(music),
        '-filter_complex',
        '[1:a]volume=0.18[music];[music][0:a]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=280[ducked];'
        '[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=1.5[a]',
        '-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a',cfg['audio_bitrate'],
        '-shortest','-movflags','+faststart',str(temp)
    ])
    temp.replace(short_path)
    return short_path


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
        # Duck licensed music under the original scene dialogue.
        run([
            'ffmpeg','-y','-i',str(temp),'-stream_loop','-1','-i',str(music),
            '-filter_complex',
            '[1:a]volume=0.18[music];[music][0:a]sidechaincompress=threshold=0.025:ratio=8:attack=15:release=280[ducked];'
            '[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=1.5[a]',
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
    ranked = analyze_highlights(video, duration, cfg, item)
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
        raise RuntimeError('No fresh unused scene windows remain for this source.')

    work = out_dir / 'clips'
    work.mkdir(parents=True, exist_ok=True)
    clips = []
    ordered = sorted(selected, key=lambda x: x[2], reverse=True)
    if bool(cfg.get('hook_enabled', True)) and ordered:
        hs, he, _ = ordered[0]
        hook_seconds = max(1.0, min(6.0, float(cfg.get('hook_seconds', 5))))
        hook_end = min(he, hs + hook_seconds)
        hook = work / 'hook_01.mp4'
        hook_line = item.get('_daily_caption') or caption_line(item, 'long')
        extract_clip(video, hs, hook_end, hook, int(cfg['output_width']), int(cfg['output_height']), item, item.get('edit_style','clean'), overlay_text=hook_line)
        clips.append(hook)
    for idx, (start, end, score) in enumerate(ordered, 1):
        clip = work / f'clip_{idx:02d}.mp4'
        scene_caption = caption_line(item, f'clip-{idx}')
        extract_clip(
            video, start, end, clip, int(cfg['output_width']), int(cfg['output_height']),
            item, item.get('edit_style', 'clean'), overlay_text=scene_caption
        )
        clips.append(clip)

    title = make_title(item, part if part > 1 else None)
    out = out_dir / f'{safe_name(title)}_HIGHLIGHTS.mp4'
    music = resolve_music(item, cfg)
    concat_clips(clips, out, cfg, music=music)
    return out, selected


def make_short(video, item, part, out_dir, cfg):
    out_dir.mkdir(parents=True, exist_ok=True)
    base_title = make_title(item, part if part > 1 else None)
    out = out_dir / f'{safe_name(base_title)}_SHORT.mp4'
    duration = ffprobe_duration(video)
    target_len = min(float(cfg['short_duration_seconds']), duration)
    ranked = analyze_highlights(video, duration, cfg, item)
    if not ranked:
        raise RuntimeError('No fresh unused scene windows remain for this source.')
    start, end, score = max(ranked, key=lambda x: x[2])
    if end - start > target_len:
        center = (start + end) / 2.0
        start = max(0.0, center - target_len / 2.0)
        end = min(duration, start + target_len)
    else:
        target_len = end - start
    if cfg.get('pro_edit_enabled', True):
        profile = choose_profile(item, duration=target_len, short=True)
        vf = pro_filters(profile, 1080, 1920)
        af = pro_audio_filters(profile)
    else:
        vf = [
            'scale=1080:1920:force_original_aspect_ratio=increase',
            'crop=1080:1920',
        ]
        vf.extend(style_filters(item.get('edit_style','clean')))
        af = 'loudnorm=I=-14:TP=-1.5:LRA=11'
    # Scene captions are disabled by default; keep the source dialogue/audio clean.
    if cfg.get('show_scene_captions', False):
        hook_text = item.get('_daily_caption') or caption_line(item, 'short')
        hook_text = re.sub(r"[\\U0001F300-\\U0001FAFF\\U00002600-\\U000027BF]", "", str(hook_text)).strip()[:54]
        vf.append('drawbox=x=0:y=72:w=iw:h=100:color=white@1.0:t=fill')
        vf.append(f"drawtext=text='{escape_drawtext(hook_text)}':x=(w-text_w)/2:y=101:fontsize=36:fontcolor=black:fix_bounds=true")
    if cfg.get('brand_watermark_enabled', True):
        brand = escape_drawtext(cfg.get('brand_watermark_text', 'VYROX-2008'))
        vf.append(f"drawtext=text='{brand}':x=w-text_w-42:y=h-text_h-42:fontsize=34:fontcolor=white@0.94:box=1:boxcolor=black@0.48:boxborderw=12:borderw=1:bordercolor=black@0.55:fix_bounds=true")
    apply_manual_censors(vf, item)
    run([
        'ffmpeg','-y','-ss',f'{start:.3f}','-i',str(video),'-t',f'{target_len:.3f}',
        '-vf',','.join(vf),'-af',af,'-c:v','libx264','-preset','veryfast','-b:v',cfg['video_bitrate'],
        '-c:a','aac','-b:a',cfg['audio_bitrate'],'-movflags','+faststart',str(out)
    ])
    mix_short_music(out, item, cfg)
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
    ap.add_argument('--daily', action='store_true', help='create date-specific edits and avoid previously published scene windows')
    args = ap.parse_args()
    check_ffmpeg()
    cfg = load_json(CONFIG, {})
    meta = load_json(ROOT / args.metadata, {'items': []})
    state = load_json(STATE, {'processed': {}, 'queue': [], 'daily': {}})
    today = time.strftime('%Y-%m-%d')
    lookback = int(cfg.get('viral_no_repeat_days', 30))

    items = meta.get('items', [])
    if args.id:
        items = [x for x in items if x.get('id') == args.id]
        if not items:
            raise SystemExit(f'No item found: {args.id}')

    seen_sources = set()
    for raw_item in items:
        item = dict(raw_item)
        source_id = str(item.get('id') or '').strip()
        if not source_id:
            print('SKIP source with no id')
            continue
        source, thumb = validate_item(item)
        source_rel = str(source.relative_to(ROOT))
        if source_rel in seen_sources:
            print(f'SKIP duplicate source file in metadata: {source_rel}')
            continue
        seen_sources.add(source_rel)

        item['_source_item_id'] = source_id
        item_id = f'{source_id}-{today}' if args.daily else source_id
        item['id'] = item_id
        if item_id in state.get('processed', {}):
            print(f'SKIP already processed today: {item_id}')
            continue

        item['_used_windows'] = previously_published_windows(
            state, source_rel, today, lookback_days=lookback
        ) if args.daily else []
        item['_detected_title'] = infer_title(source, item)
        item.setdefault('music_mood', item.get('edit_style', 'cinematic'))
        item['_cfg'] = cfg
        item['_daily_caption'] = caption_line(item, 'daily')
        duration = ffprobe_duration(source)
        if args.daily:
            fresh_options = analyze_highlights(source, duration, cfg, item)
            if not fresh_options:
                print(f'SKIP no fresh unused scenes left within lookback: {source_rel}')
                continue

        work = ROOT / 'output' / safe_name(item_id)
        raw_parts = split_video(source, work / 'parts', item, duration, cfg)
        produced = []
        split_limit = float(cfg.get('max_single_video_hours', 2)) * 3600
        segment_seconds = duration / 2.0 if duration > split_limit and len(raw_parts) > 1 else duration
        prepared_parts = []
        for part, raw in raw_parts:
            part_offset = (part - 1) * segment_seconds if len(raw_parts) > 1 else 0.0
            part_item = dict(item)
            part_duration = ffprobe_duration(raw)
            if args.daily:
                part_item['_used_windows'] = []
                for used_start, used_end in item.get('_used_windows', []):
                    local_start = float(used_start) - part_offset
                    local_end = float(used_end) - part_offset
                    if local_end > 0 and local_start < part_duration:
                        part_item['_used_windows'].append((
                            max(0.0, local_start), min(part_duration, local_end)
                        ))
                fresh_windows = analyze_highlights(raw, part_duration, cfg, part_item)
                if not fresh_windows:
                    print(f'SKIP part {part}: no fresh scenes in {source_rel}')
                    continue
                best_scene_score = max(float(x[2]) for x in fresh_windows)
                prepared_parts.append((best_scene_score, len(fresh_windows), -part, part, raw, part_offset, part_item))
            else:
                prepared_parts.append((0.0, 0, -part, part, raw, part_offset, part_item))

        if args.daily:
            if not prepared_parts:
                print(f'SKIP source output with no fresh scene windows: {source_rel}')
                continue
            # For a long movie split into parts, process the part with the strongest
            # unused scene set. Only that selected part becomes a daily queue item.
            prepared_parts = [max(prepared_parts, key=lambda row: (row[0], row[1], row[2]))]

        for _, _, _, part, raw, part_offset, part_item in prepared_parts:
            try:
                video, short, banner, title, selected, short_info = process_part(
                    raw, thumb, part_item, part, work / 'final', cfg
                )
            except RuntimeError as exc:
                if args.daily and 'fresh unused scene windows' in str(exc):
                    print(f'SKIP source output with no fresh scene window: {source_rel}')
                    produced = []
                    break
                raise
            selected_global = [
                {'start': round(st + part_offset, 2), 'end': round(en + part_offset, 2), 'score': round(score, 4)}
                for st, en, score in selected
            ]
            short_global = dict(short_info)
            if 'start' in short_global:
                short_global['start'] = round(float(short_global['start']) + part_offset, 2)
            if 'end' in short_global:
                short_global['end'] = round(float(short_global['end']) + part_offset, 2)
            produced.append({
                'part': part,
                'date': today,
                'item_id': item_id,
                'source_item_id': source_id,
                'topic_id': str(item.get('topic_id') or source_id),
                'source': source_rel,
                'licensed': item.get('licensed') is True,
                'video': str(video.relative_to(ROOT)),
                'short': str(short.relative_to(ROOT)),
                'thumbnail': str(banner.relative_to(ROOT)),
                'original_thumbnail': str(thumb.relative_to(ROOT)),
                'title': title,
                'type': item.get('type', 'movie'),
                'category': item.get('category', item.get('type', 'movie')),
                'edit_style': item.get('edit_style', 'clean'),
                'adult_badge': bool(item.get('adult', False)),
                'description': (str(item.get('description', '')).strip() + '\n\n' + str(item.get('_daily_caption') or caption_line(item, 'description'))).strip(),
                'caption_text': item.get('_daily_caption') or caption_line(item, 'description'),
                'tags': item.get('tags', []),
                'privacy_status': item.get('privacy_status', 'public'),
                'selected_highlights': selected_global,
                'short_highlight': short_global,
            })
        if not produced:
            continue
        state.setdefault('processed', {})[item_id] = {
            'source_item_id': source_id,
            'duration_seconds': duration,
            'detected_title': item['_detected_title'],
            'source': source_rel,
            'type': item.get('type', 'content'),
            'created_at': int(time.time()),
            'outputs': produced,
        }
        state.setdefault('queue', []).extend([{**x, 'item_id': item_id, 'source_item_id': source_id, 'status': 'ready'} for x in produced])
        save_json(STATE, state)
        print(f'DONE: {item_id} -> {len(produced)} daily upload item(s) queued')




if __name__ == '__main__':
    main()
