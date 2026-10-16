#!/usr/bin/env python3
"""Demo-style vertical edit renderer (matches the reference "moongod" edit).

Layout copied from the reference clip:
    * 9:16 canvas (1080x1920), black background
    * square (1:1) video centered vertically
    * white caption bar across the top of the square, bold black text
    * fast cuts (a new scene roughly every 2-3 s)
    * audio normalised to -14 LUFS, true peak -1.5 dB, with tiny fades at cuts

Only use this on source media you own or are licensed to use.
Requires: ffmpeg/ffprobe on PATH and Pillow.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


W, H = 1080, 1920
SQUARE = 1080                          # square video size (full width)
SQUARE_Y = (H - SQUARE) // 2           # 420
BAR_H = 130                            # caption bar height
FPS = 30

FONT_CANDIDATES = [
    "assets/fonts/Anton-Regular.ttf",  # drop a bold font here for the exact look
    "assets/fonts/Impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]


def run(cmd):
    print(">", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True)
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


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip().splitlines()[-1])


def build_edit(source, out, segments, caption, root=Path("."), fade=0.04):
    """Render one demo-style vertical edit.

    segments: list of (start_seconds, end_seconds) windows cut from `source`,
              played in the given order (fast-cut montage).
    """
    source, out, root = Path(source), Path(out), Path(root)
    if not segments:
        raise ValueError("at least one segment is required")
    out.parent.mkdir(parents=True, exist_ok=True)
    bar_png = out.with_suffix(".bar.png")
    render_caption_bar(caption, bar_png, root)

    cmd = ["ffmpeg", "-y"]
    for start, end in segments:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(source)]
    cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(bar_png)]
    bar_idx = len(segments)

    parts, vlabels, alabels = [], [], []
    for i, (start, end) in enumerate(segments):
        length = end - start
        parts.append(
            f"[{i}:v]scale={SQUARE}:{SQUARE}:force_original_aspect_ratio=increase,"
            f"crop={SQUARE}:{SQUARE},setsar=1,fps={FPS},setpts=PTS-STARTPTS[v{i}]"
        )
        parts.append(
            f"[{i}:a]aresample=44100,asetpts=PTS-STARTPTS,"
            f"afade=t=in:d={fade},afade=t=out:st={max(0.0, length - fade):.3f}:d={fade}[a{i}]"
        )
        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}]")
    n = len(segments)
    parts.append("".join(f"{v}{a}" for v, a in zip(vlabels, alabels)) +
                 f"concat=n={n}:v=1:a=1[vc][ac]")
    parts.append(f"color=c=black:s={W}x{H}:r={FPS}[bg]")
    parts.append(f"[bg][vc]overlay=0:{SQUARE_Y}:shortest=1[base]")
    parts.append(f"[base][{bar_idx}:v]overlay=0:{SQUARE_Y}:shortest=1,format=yuv420p[vout]")
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
    return out


def main():
    ap = argparse.ArgumentParser(description="Demo-style vertical edit")
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--caption", required=True)
    ap.add_argument("--seg", action="append", required=True,
                    help="start:end in seconds, repeat for each cut (e.g. --seg 5:8 --seg 20:23)")
    args = ap.parse_args()
    segs = []
    for s in args.seg:
        a, b = s.split(":")
        segs.append((float(a), float(b)))
    build_edit(args.source, args.out, segs, args.caption)
    print("OK", args.out)


if __name__ == "__main__":
    sys.exit(main())
