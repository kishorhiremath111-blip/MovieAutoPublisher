#!/usr/bin/env python3
"""Lightweight FFmpeg scene-change/highlight helpers.

This module only analyzes supplied/licensed media. It does not download or bypass protected streams.
"""
import re
import subprocess
from pathlib import Path


def detect_scene_times(video: Path, threshold: float = 0.40):
    cmd = [
        'ffmpeg', '-hide_banner', '-i', str(video),
        '-vf', f"select='gt(scene,{threshold})',showinfo",
        '-an', '-f', 'null', '-'
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    times = []
    for line in p.stdout.splitlines():
        m = re.search(r'pts_time:([0-9.]+)', line)
        if m:
            try:
                times.append(float(m.group(1)))
            except ValueError:
                pass
    return sorted(set(times))


def choose_highlight_windows(duration, scene_times, count=1, clip_seconds=45):
    """Choose evenly distributed scene-change windows when semantic labels are unavailable."""
    if duration <= 0:
        return []
    candidates = []
    half = clip_seconds / 2.0
    for t in scene_times:
        start = max(0.0, t - half)
        end = min(duration, start + clip_seconds)
        if end - start >= 5:
            candidates.append((start, end))
    if not candidates:
        start = max(0.0, (duration - clip_seconds) / 2.0)
        return [(start, min(duration, start + clip_seconds))]
    # Spread picks through the video instead of taking adjacent cuts.
    candidates.sort(key=lambda x: x[0])
    if count >= len(candidates):
        return candidates[:count]
    step = max(1, len(candidates) // count)
    picks = [candidates[i] for i in range(0, len(candidates), step)][:count]
    return picks
