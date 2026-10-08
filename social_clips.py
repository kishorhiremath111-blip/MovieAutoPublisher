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


def best_window(path, cfg):
    d = duration(path)
    scenes = detect_scene_times(path, float(cfg.get("scene_threshold", 0.35)))
    silence = detect_silence_ranges(path, float(cfg.get("silence_db", -34)))
    ranked = rank_highlight_windows(
        d,
        scenes,
        count=int(cfg.get("social_candidate_count", 10)),
        clip_seconds=float(cfg.get("social_clip_seconds", 45)),
        silence_ranges=silence,
        min_gap_seconds=float(cfg.get("social_min_gap_seconds", 8)),
    )
    if not ranked:
        length = min(float(cfg.get("social_clip_seconds", 45)), d)
        return 0.0, length, 0.0
    return max(ranked, key=lambda x: x[2])


def render(src, out, start, end, cfg, style):
    width, height = 1080, 1920
    item = {"edit_style": style, "category": style}
    profile = choose_profile(item, duration=max(0.5, end-start), short=True)
    vf = pro_filters(profile, width, height)
    af = pro_audio_filters(profile)
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
    used = {str(x.get("id")) for x in state.get("social", [])}
    trends = trend_index()

    candidates = []
    for item in items:
        if item.get("licensed") is not True:
            continue
        item_id = str(item.get("id") or safe_name(Path(str(item.get("source", ""))).stem))
        if item_id in used:
            continue

        source = ROOT / str(item.get("source", ""))
        if not source.exists():
            source = SRC_DIR / Path(str(item.get("source", ""))).name
        if not source.exists():
            continue

        score, breakdown = score_candidate(item, trends, tracker)
        candidates.append((score, breakdown, item, source, item_id))

    candidates.sort(key=lambda x: x[0], reverse=True)
    if not candidates:
        print("Social clips: no fresh authorized candidate available.")
        return

    created = 0
    for base_score, base_breakdown, item, source, item_id in candidates[:limit]:
        if created >= limit:
            break

        if base_score < threshold:
            print(
                f"Social top candidate below viral gate: {base_score:.2f} < {threshold:.2f}; "
                "no upload candidate created."
            )
            break

        start, end, scene_score = best_window(source, cfg)
        style = str(item.get("edit_style", "clean")).lower()
        out = OUT_DIR / f"{safe_name(item_id)}_{today}_SHORT.mp4"
        render(source, out, start, end, cfg, style)

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

        description = (str(item.get("description", "")).strip() + "\n\n" + " ".join(pack["hashtags"])).strip()
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
            "source": str(source.relative_to(ROOT)),
            "licensed": True,
            "creator": item.get("creator", ""),
            "edit_style": style,
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
