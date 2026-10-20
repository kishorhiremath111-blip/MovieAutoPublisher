#!/usr/bin/env python3
"""Rights-aware scene finder and vertical Shorts draft renderer.

This tool processes local media only. It does not scrape streaming services,
bypass DRM, or upload anything. Use only media you own or are authorized to edit.
Requires ffmpeg and ffprobe on PATH.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TIME_RE = re.compile(r"pts_time:([0-9]+(?:\\.[0-9]+)?)")


def run(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, check=True, text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )


def media_duration(source: Path) -> float:
    result = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(source)
    ])
    try:
        duration = float(result.stdout.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("Could not read video duration with ffprobe.") from exc
    if duration <= 0:
        raise ValueError("Source video has no usable duration.")
    return duration


def find_scene_changes(source: Path, threshold: float = 0.24) -> list[float]:
    # showinfo reports timestamps for frames selected by FFmpeg's scene detector.
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(source), "-vf",
         f"select='gt(scene,{threshold})',showinfo", "-vsync", "vfr",
         "-f", "null", "-"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError("FFmpeg scene detection failed: " + result.stderr[-1200:])
    values = [float(m.group(1)) for m in TIME_RE.finditer(result.stderr)]
    # Deduplicate neighboring selected frames and ignore the very beginning.
    unique: list[float] = []
    for value in values:
        if value > 1 and (not unique or value - unique[-1] >= 1.5):
            unique.append(value)
    return unique


def make_candidates(changes: list[float], duration: float, clip_len: float,
                    limit: int) -> list[dict]:
    if clip_len <= 0 or clip_len > 180:
        raise ValueError("Clip length must be between 1 and 180 seconds.")
    max_start = max(0.0, duration - clip_len)
    starts: list[float] = []
    for point in changes:
        start = min(max(0.0, point - clip_len * 0.35), max_start)
        if all(abs(start - old) >= clip_len * 0.55 for old in starts):
            starts.append(start)
        if len(starts) >= limit:
            break
    if not starts:
        starts = [max(0.0, min(max_start, duration * 0.25))]
    return [
        {"rank": i + 1, "start_seconds": round(start, 2),
         "end_seconds": round(min(duration, start + clip_len), 2),
         "duration_seconds": round(min(clip_len, duration - start), 2),
         "reason": "scene-change candidate; review manually before publishing"}
        for i, start in enumerate(starts)
    ]


def render_vertical(source: Path, start: float, length: float, output: Path,
                    subtitles: Path | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if subtitles:
        # Escape path characters for FFmpeg's subtitles filter.
        subtitle_path = str(subtitles.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf += f",subtitles='{subtitle_path}'"
    run([
        "ffmpeg", "-y", "-hide_banner", "-ss", f"{start:.3f}", "-i", str(source),
        "-t", f"{length:.3f}", "-vf", vf, "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm",
        "-movflags", "+faststart", str(output)
    ], capture=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find scene-change candidates and render a vertical Shorts draft."
    )
    parser.add_argument("video", type=Path, help="Local video file you are authorized to edit")
    parser.add_argument("--i-have-rights", action="store_true",
                        help="Confirm you own or have permission to edit this video")
    parser.add_argument("--clip-seconds", type=float, default=35,
                        help="Target clip duration (default: 35; maximum: 180)")
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--threshold", type=float, default=0.24,
                        help="FFmpeg scene-change threshold, 0.05–0.8")
    parser.add_argument("--render", type=int, default=0,
                        help="Render candidate rank N as a vertical MP4 draft")
    parser.add_argument("--subtitles", type=Path, default=None,
                        help="Optional .srt subtitle file you are authorized to use")
    parser.add_argument("--output-dir", type=Path, default=Path("output/series_clips"))
    args = parser.parse_args()

    if not args.i_have_rights:
        parser.error("For rights-cleared media only, pass --i-have-rights after confirming permission.")
    if not args.video.is_file():
        parser.error(f"Video file not found: {args.video}")
    if args.subtitles and not args.subtitles.is_file():
        parser.error(f"Subtitle file not found: {args.subtitles}")
    if not 0.05 <= args.threshold <= 0.8:
        parser.error("--threshold must be between 0.05 and 0.8")
    if not 1 <= args.max_candidates <= 30:
        parser.error("--max-candidates must be 1–30")
    if args.render < 0 or args.render > args.max_candidates:
        parser.error("--render must be 0 (no render) or a candidate rank within the limit")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        parser.error("Install FFmpeg and ffprobe first; both must be on PATH.")

    try:
        duration = media_duration(args.video)
        changes = find_scene_changes(args.video, args.threshold)
        candidates = make_candidates(changes, duration, args.clip_seconds, args.max_candidates)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "source": args.video.name,
            "rights_confirmation": True,
            "duration_seconds": round(duration, 2),
            "scene_changes_detected": len(changes),
            "candidate_count": len(candidates),
            "note": "Candidates are based on visual cuts, not guaranteed popularity. Review content, rights, audio and platform rules before publishing.",
            "candidates": candidates,
        }
        manifest_path = args.output_dir / "scene_candidates.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Detected {len(changes)} scene-change points.")
        for item in candidates:
            print(f"#{item['rank']}: {item['start_seconds']}s–{item['end_seconds']}s")
        print(f"Candidate list: {manifest_path}")
        if args.render:
            item = candidates[args.render - 1]
            target = args.output_dir / f"short_candidate_{args.render:02d}.mp4"
            render_vertical(args.video, item["start_seconds"], item["duration_seconds"],
                            target, args.subtitles)
            print(f"Draft MP4: {target}")
            print("Draft only: nothing was uploaded or published.")
    except (subprocess.CalledProcessError, RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
