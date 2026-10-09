#!/usr/bin/env python3
"""Generate professional Shorts/Reels from authorized short-form sources.

Candidates are ranked against current YouTube/Instagram trend metadata before
editing. Only the best fresh licensed candidate is rendered each day.
"""
import json
import re
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from scene_tools import detect_scene_times, detect_silence_ranges, rank_highlight_windows
from viral_tracker import trend_index, score_candidate, make_pack
from pro_editor import choose_profile, filters as pro_filters, audio_filters as pro_audio_filters
from caption_design import caption_line, palette

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "config.json"
MANIFEST = ROOT / "social_sources.json"
STATE = ROOT / "state" / "state.json"
TRACKER = ROOT / "state" / "viral_tracker.json"
SRC_DIR = ROOT / "input" / "social_sources"
OUT_DIR = ROOT / "output" / "social"


def load(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def run(cmd):
    print(">", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        print(p.stdout)
        raise RuntimeError("FFmpeg command failed")
    return p.stdout


def duration(path):
    return float(run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ]).strip())


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_") or "social_clip"


def best_window(path, cfg, previous_windows=None):
    d = duration(path)
    scenes = detect_scene_times(path, float(cfg.get("scene_threshold", 0.35)))
    silence = detect_silence_ranges(path, float(cfg.get("silence_db", -34)))
    ranked = rank_highlight_windows(
        d,
        scenes,
        count=max(60, int(cfg.get("social_candidate_count", 10)) * 10),
        clip_seconds=float(cfg.get("social_clip_seconds", 45)),
        silence_ranges=silence,
        min_gap_seconds=float(cfg.get("social_min_gap_seconds", 8)),
    )
    previous_windows = previous_windows or []
    fresh = []
    for start, end, score in ranked:
        repeats = False
        for old_start, old_end in previous_windows:
            overlap = max(0.0, min(end, old_end) - max(start, old_start))
            if overlap >= min(8.0, (end - start) * 0.20):
                repeats = True
                break
        if not repeats:
            fresh.append((start, end, score))
    if not fresh:
        return None
    return max(fresh, key=lambda x: x[2])


def previous_scene_windows(state, source_rel, today, lookback_days=30):
    from datetime import date, timedelta
    current = date.fromisoformat(today)
    cutoff = current - timedelta(days=max(1, int(lookback_days)))
    target = str(Path(source_rel))
    windows = []
    for row in state.get("social", []):
        try:
            row_day = date.fromisoformat(str(row.get("date") or "")[:10])
        except ValueError:
            continue
        if not (cutoff <= row_day < current) or str(row.get("source") or "") != target:
            continue
        window = row.get("selected_highlight") or {}
        try:
            windows.append((float(window["start"]), float(window["end"])))
        except (KeyError, TypeError, ValueError):
            continue
    return windows


def _escape_drawtext(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")


def render(src, out, start, end, cfg, style, item):
    width, height = 1080, 1920
    edit_item = dict(item)
    edit_item["edit_style"] = style
    profile = choose_profile(edit_item, duration=max(0.5, end-start), short=True)
    vf = pro_filters(profile, width, height)
    af = pro_audio_filters(profile)
    line = caption_line(edit_item, "social")
    line = re.sub(r"[\\U0001F300-\\U0001FAFF\\U00002600-\\U000027BF]", "", str(line)).strip()[:54]
    # Same VIBEFRAME design on every Short/Reel: fixed white strip at top, black text, no emoji.
    vf.extend([
        "drawbox=x=0:y=72:w=iw:h=100:color=white@1.0:t=fill",
        f"drawtext=text='{_escape_drawtext(line)}':x=(w-text_w)/2:y=101:fontsize=36:fontcolor=black:fix_bounds=true",
    ])
    run([
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(src),
        "-t", f"{max(0.5, end-start):.3f}",
        "-vf", ",".join(vf),
        "-af", af,
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", cfg.get("video_bitrate", "3500k"),
        "-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "160k"),
        "-movflags", "+faststart", str(out)
    ])
    return line


def thumb_font(size, bold=True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def make_thumbnail(src, out, text):
    im = Image.open(src).convert("RGB")
    im = ImageOps.fit(im, (1280, 720), method=Image.Resampling.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.12)
    im = ImageEnhance.Color(im).enhance(1.05)
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for y in range(390, 720):
        alpha = int(205 * ((y - 390) / 330))
        d.line((0, y, 1280, y), fill=(0, 0, 0, alpha))
    im = Image.alpha_composite(im.convert("RGBA"), overlay)

    d = ImageDraw.Draw(im)
    text = str(text or "WATCH THIS").upper()[:34]
    f = thumb_font(74, True)
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if d.textbbox((0, 0), test, font=f)[2] <= 1120:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)

    y = 470
    for line in lines[:2]:
        d.text((70, y), line, font=f, fill="white", stroke_width=3, stroke_fill="black")
        y += 88

    out.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(out, quality=94, optimize=True)
    return out


def main():
    cfg = load(CONFIG, {})
    manifest = load(MANIFEST, {"items": []})
    state = load(STATE, {"social": []})
    tracker = load(TRACKER, {})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = manifest.get("items", [])
    if not items:
        print("Social clips: no authorized sources configured; skipping.")
        return

    today = time.strftime("%Y-%m-%d")
    limit = int(cfg.get("daily_social_clips", 1))
    threshold = float(cfg.get("viral_pre_publish_min_score", 75))
    trends = trend_index()
    seen_sources = set()
    already_generated_today = {
        str(x.get("source_item_id") or x.get("id"))
        for x in state.get("social", []) if x.get("date") == today
    }
    cooldown_days = int(cfg.get("viral_no_repeat_days", 30))

    candidates = []
    for item in items:
        if item.get("licensed") is not True:
            continue
        source_id = str(item.get("id") or safe_name(Path(str(item.get("source", ""))).stem))
        if source_id in already_generated_today:
            continue

        source = ROOT / str(item.get("source", ""))
        if not source.exists():
            source = SRC_DIR / Path(str(item.get("source", ""))).name
        if not source.exists() or not source.is_file():
            continue
        source_path = str(source.relative_to(ROOT))
        if source_path in seen_sources:
            continue
        seen_sources.add(source_path)
        topic_id = str(item.get("topic_id") or source_id)
        score, breakdown = score_candidate(item, trends, tracker)
        candidates.append((score, breakdown, item, source, source_id, topic_id, source_path))

    candidates.sort(key=lambda x: x[0], reverse=True)
    if not candidates:
        print("Social clips: no fresh authorized candidate available.")
        return

    created = 0
    for base_score, base_breakdown, item, source, source_id, topic_id, source_path in candidates:
        if created >= limit:
            break

        if base_score < threshold:
            print(
                f"Social top candidate below viral gate: {base_score:.2f} < {threshold:.2f}; "
                "no upload candidate created."
            )
            break

        previous = previous_scene_windows(state, source_path, today, cooldown_days)
        window = best_window(source, cfg, previous)
        if not window:
            print(f"Social source exhausted for {cooldown_days} days; no new scene window: {source_path}")
            continue
        start, end, scene_score = window
        item_id = f"{source_id}-{today}"
        style = str(item.get("edit_style", "clean")).lower()
        out = OUT_DIR / f"{safe_name(source_id)}_{today}_SHORT.mp4"
        caption_text = render(source, out, start, end, cfg, style, item)

        enriched = dict(item)
        enriched["selected_highlight"] = {"score": scene_score}
        final_score, final_breakdown = score_candidate(enriched, trends, tracker)
        if final_score < threshold:
            print(
                f"Candidate fell below viral gate after edit: {final_score:.2f} < {threshold:.2f}; holding."
            )
            continue

        pack = make_pack(enriched, trends, final_score)
        thumb = OUT_DIR / f"{safe_name(item_id)}_{today}_THUMB.jpg"
        make_thumbnail(source, thumb, pack["thumbnail_text"])

        brand_line = "Follow VIBEFRAME for fresh relatable edits, anime moments and daily scene picks."
        source_credit = str(item.get("source_credit") or item.get("creator") or "").strip()
        credit_line = f"Source/creator: {source_credit}" if source_credit else ""
        description = "\n\n".join(part for part in [str(item.get("description", "")).strip(), caption_text, credit_line, " ".join(pack["hashtags"]), brand_line] if part).strip()
        row = {
            "id": item_id,
            "date": today,
            "status": "ready",
            "video": str(out.relative_to(ROOT)),
            "thumbnail": str(thumb.relative_to(ROOT)),
            "title": pack["title"],
            "description": description[:5000],
            "tags": pack["tags"],
            "hashtags": pack["hashtags"],
            "category": item.get("category", "viral"),
            "source": source_path,
            "licensed": True,
            "topic_id": topic_id,
            "source_item_id": source_id,
            "creator": item.get("creator", ""),
            "edit_style": style,
            "caption_text": caption_text,
            "viral_score": final_score,
            "viral_breakdown": final_breakdown,
            "viral_pack": pack,
            "selected_highlight": {
                "start": round(start, 2),
                "end": round(end, 2),
                "score": round(scene_score, 4),
            },
        }
        state.setdefault("social", []).append(row)
        save(STATE, state)
        created += 1
        print(f"READY social clip: {out} score={final_score:.2f}")
        print(f"Thumbnail: {thumb}")

    print(f"Social clips created: {created}/{limit}; candidates checked={len(candidates)}")


if __name__ == "__main__":
    main()
