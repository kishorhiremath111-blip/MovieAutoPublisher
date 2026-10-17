#!/usr/bin/env python3
"""Demo-style vertical edit renderer (matches the reference "moongod" edit).

Two layouts:
  style="bar"  - square video with a white caption bar on top (the "moongod" demo)
  style="reel" - big white caption on a black area above the video (relatable/"clips" look)

Bar layout copied from the reference clip:
  * 9:16 canvas (1080x1920), black background
  * square (1:1) video centered vertically
  * white caption bar across the top of the square, bold black text
  * fast cuts (a new scene roughly every 2-3 s)
  * audio normalised to -14 LUFS, true peak -1.5 dB, with tiny fades at cuts

Only use this on source media you own or are licensed to use.
Requires: ffmpeg/ffprobe on PATH and Pillow.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
SQUARE = 1080                       # square video size (full width)
SQUARE_Y = (H - SQUARE) // 2        # 420
BAR_H = 130                         # caption bar height
FPS = 30
TOP_H = 560                         # black caption area height in "reel" style
REEL_Y = TOP_H                      # video starts right under the caption area
DEFAULT_STYLE = "reel"

FONT_CANDIDATES = [
    "assets/fonts/Anton-Regular.ttf",                       # drop a bold font here for the exact look
    "assets/fonts/Impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]


def run(cmd):
    print(">", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        print(p.stdout[-3000:])
        raise RuntimeError("ffmpeg command failed")
    return p.stdout


def _find_font(root: Path):
    for cand in FONT_CANDIDATES:
        path = Path(cand) if cand.startswith("/") else root / cand
        if path.is_file():
            return str(path)
    return None


def render_caption_bar(text, out_png, root=Path(".")):
    """White bar with bold black text, auto-shrunk to fit one line."""
    text = re.sub(r"\s+", " ", str(text or "")).strip().upper()
    img = Image.new("RGB", (W, BAR_H), "white")
    draw = ImageDraw.Draw(img)
    font_path = _find_font(Path(root))
    size = 78
    while True:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = box[2] - box[0], box[3] - box[1]
        if text_w <= W - 80 or size <= 30 or not font_path:
            break
        size -= 2
    x = (W - text_w) // 2 - box[0]
    y = (BAR_H - text_h) // 2 - box[1]
    draw.text((x, y), text, font=font, fill="black")
    img.save(out_png)
    return out_png


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def render_reel_caption(text, out_png, root=Path(".")):
    """Big white multi-line caption on black (top area of the 9:16 canvas)."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    img = Image.new("RGB", (W, TOP_H), "black")
    draw = ImageDraw.Draw(img)
    font_path = _find_font(Path(root))
    max_w, max_h = W - 140, TOP_H - 120
    size = 76
    while True:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        lines = _wrap(draw, text, font, max_w)
        line_h = int(size * 1.22)
        if (len(lines) * line_h <= max_h and len(lines) <= 5) or size <= 34 or not font_path:
            break
        size -= 2
    block_h = len(lines) * line_h
    y = TOP_H - 40 - block_h            # sit near the video, like the reference reel
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((W - w) / 2, y), line, font=font, fill="white")
        y += line_h
    img.save(out_png)
    return out_png


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def choose_caption(given, source, root=Path(".")):
    """Pick a human-written caption from captions_bank.json (never repeats until the bank is used up).

    Turn it off with  "caption_bank": false  in config/config.json.
    """
    root = Path(root)
    cfg = _load_json(root / "config" / "config.json", {})
    if cfg.get("caption_bank", True) is False:
        return given
    bank = _load_json(root / "captions_bank.json", {})
    pool = [c for group in bank.values() if isinstance(group, list) for c in group if str(c).strip()]
    if not pool:
        return given
    state_path = root / "state" / "used_captions.json"
    used = _load_json(state_path, [])
    fresh = [c for c in pool if c not in used] or pool
    if fresh is pool:
        used = []
    seed = int(hashlib.sha1(f"{Path(source).stem}{time.strftime('%Y-%m-%d')}".encode()).hexdigest(), 16)
    pick = fresh[seed % len(fresh)]
    used.append(pick)
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(used[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return pick


def _has_audio(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    return "audio" in out


def render_watermark(text, out_png, root=Path(".")):
    """Small semi-transparent brand tag (RGBA)."""
    font_path = _find_font(Path(root))
    font = ImageFont.truetype(font_path, 30) if font_path else ImageFont.load_default()
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    tw = int(probe.textlength(text, font=font))
    img = Image.new("RGBA", (tw + 36, 58), (0, 0, 0, 125))
    ImageDraw.Draw(img).text((18, 12), text, font=font, fill=(255, 255, 255, 235))
    img.save(out_png)
    return img.size


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip().splitlines()[-1])


def build_edit(source, out, segments, caption, root=Path("."), fade=0.04, style=None):
    """Render one demo-style vertical edit.

    segments: list of (start_seconds, end_seconds) windows cut from `source`,
              played in the given order (fast-cut montage).
    """
    source, out, root = Path(source), Path(out), Path(root)
    if not segments:
        raise ValueError("at least one segment is required")
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = _load_json(root / "config" / "config.json", {})
    style = (style or cfg.get("edit_style") or DEFAULT_STYLE).lower()
    caption = choose_caption(caption, source, root)
    bar_png = out.with_suffix(".bar.png")
    if style == "reel":
        render_reel_caption(caption, bar_png, root)
        video_y, cap_y = REEL_Y, 0
    else:
        render_caption_bar(caption, bar_png, root)
        video_y = cap_y = SQUARE_Y

    cmd = ["ffmpeg", "-y"]
    for start, end in segments:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(source)]
    cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(bar_png)]
    bar_idx = len(segments)
    has_audio = _has_audio(source)
    wm_text = str(cfg.get("brand_watermark_text", "")).strip()
    wm_png, wm_idx, wm_size = None, None, (0, 0)
    if cfg.get("brand_watermark_enabled", True) and wm_text:
        wm_png = out.with_suffix(".wm.png")
        wm_size = render_watermark(wm_text, wm_png, root)
        cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(wm_png)]
        wm_idx = bar_idx + 1

    parts, vlabels, alabels = [], [], []
    for i, (start, end) in enumerate(segments):
        length = end - start
        parts.append(
            f"[{i}:v]scale={SQUARE}:{SQUARE}:force_original_aspect_ratio=increase,"
            f"crop={SQUARE}:{SQUARE},setsar=1,fps={FPS},setpts=PTS-STARTPTS[v{i}]"
        )
        fmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
        if has_audio:
            parts.append(
                f"[{i}:a]aresample=44100,asetpts=PTS-STARTPTS,{fmt},"
                f"afade=t=in:d={fade},afade=t=out:st={max(0.0, length - fade):.3f}:d={fade}[a{i}]"
            )
        else:  # silent source (e.g. stock footage): generate silence of the same length
            parts.append(f"anullsrc=r=44100:cl=stereo:d={length:.3f},{fmt},asetpts=PTS-STARTPTS[a{i}]")
        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}]")
    n = len(segments)
    parts.append("".join(f"{v}{a}" for v, a in zip(vlabels, alabels)) +
                 f"concat=n={n}:v=1:a=1[vc][ac]")
    parts.append(f"color=c=black:s={W}x{H}:r={FPS}[bg]")
    parts.append(f"[bg][vc]overlay=0:{video_y}:shortest=1[base]")
    if wm_idx is None:
        parts.append(f"[base][{bar_idx}:v]overlay=0:{cap_y}:shortest=1,format=yuv420p[vout]")
    else:
        parts.append(f"[base][{bar_idx}:v]overlay=0:{cap_y}:shortest=1[capd]")
        wx = W - wm_size[0] - 34
        wy = video_y + SQUARE - wm_size[1] - 34
        parts.append(f"[capd][{wm_idx}:v]overlay={wx}:{wy}:shortest=1,format=yuv420p[vout]")
    parts.append("[ac]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-movflags", "+faststart", "-shortest", str(out),
    ]
    run(cmd)
    bar_png.unlink(missing_ok=True)
    if wm_png:
        wm_png.unlink(missing_ok=True)
    return out


def main():
    ap = argparse.ArgumentParser(description="Demo-style vertical edit")
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--caption", required=True)
    ap.add_argument("--style", choices=["bar", "reel"], default=None)
    ap.add_argument("--seg", action="append", required=True,
                    help="start:end in seconds, repeat for each cut (e.g. --seg 5:8 --seg 20:23)")
    args = ap.parse_args()
    segs = []
    for s in args.seg:
        a, b = s.split(":")
        segs.append((float(a), float(b)))
    build_edit(args.source, args.out, segs, args.caption, style=args.style)
    print("OK", args.out)


if __name__ == "__main__":
    sys.exit(main())