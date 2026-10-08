#!/usr/bin/env python3
"""Scene/highlight analysis for supplied licensed/owned media.

This module ranks candidate moments using scene-change density and audio activity.
It does not attempt to identify copyright ownership or bypass Content ID.
"""
import re
import subprocess
from pathlib import Path


def _run_capture(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False).stdout


def detect_scene_times(video: Path, threshold: float = 0.35):
    cmd = [
        'ffmpeg', '-hide_banner', '-i', str(video),
        '-vf', f"select='gt(scene,{threshold})',showinfo",
        '-an', '-f', 'null', '-'
    ]
    out = _run_capture(cmd)
    times = []
    for line in out.splitlines():
        m = re.search(r'pts_time:([0-9.]+)', line)
        if m:
            try:
                times.append(float(m.group(1)))
            except ValueError:
                pass
    return sorted(set(times))


def detect_silence_ranges(video: Path, noise_db: float = -34.0):
    """Return (start, end) silence intervals detected in the first audio stream."""
    cmd = [
        'ffmpeg', '-hide_banner', '-i', str(video),
        '-af', f'silencedetect=noise={noise_db}dB:d=0.35',
        '-vn', '-f', 'null', '-'
    ]
    out = _run_capture(cmd)
    starts = []
    ranges = []
    for line in out.splitlines():
        m1 = re.search(r'silence_start:\s*([0-9.]+)', line)
        if m1:
            starts.append(float(m1.group(1)))
        m2 = re.search(r'silence_end:\s*([0-9.]+)', line)
        if m2 and starts:
            st = starts.pop(0)
            ranges.append((st, float(m2.group(1))))
    return ranges


def _overlap(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _active_ratio(start, end, silence_ranges):
    length = max(0.001, end - start)
    silent = sum(_overlap(start, end, s, e) for s, e in silence_ranges)
    return max(0.0, min(1.0, 1.0 - silent / length))


def rank_highlight_windows(duration, scene_times, count=12, clip_seconds=42,
                           silence_ranges=None, min_gap_seconds=12):
    """Return ranked non-overlapping windows as (start, end, score).

    Score is intentionally explainable:
    - scene density: more nearby cuts usually means a visually active moment
    - audio activity: less silence usually means dialogue/action/music is present
    - small center-position bonus: avoids over-selecting the first/last few seconds

    This is an editing heuristic, not a guarantee that a scene is 'viral'.
    """
    if duration <= 0:
        return []
    clip_seconds = min(float(clip_seconds), float(duration))
    if clip_seconds < 5:
        return []

    half = clip_seconds / 2.0
    candidates = []
    all_times = [t for t in scene_times if 0.0 < t < duration]
    if not all_times:
        start = max(0.0, (duration - clip_seconds) / 2.0)
        return [(start, min(duration, start + clip_seconds), 0.25)]

    for t in all_times:
        start = max(0.0, t - half)
        end = min(duration, start + clip_seconds)
        if end - start < 5:
            continue
        nearby = sum(1 for x in all_times if start <= x <= end)
        density = min(1.0, nearby / 8.0)
        active = _active_ratio(start, end, silence_ranges or [])
        mid = (start + end) / 2.0
        edge_distance = min(mid, duration - mid) / max(1.0, duration / 2.0)
        position_bonus = min(1.0, edge_distance) * 0.12
        score = 0.62 * density + 0.26 * active + position_bonus
        candidates.append((start, end, score))

    # Deduplicate highly overlapping candidates, keeping the strongest one.
    candidates.sort(key=lambda x: x[2], reverse=True)
    chosen = []
    for cand in candidates:
        cs, ce, score = cand
        too_close = False
        for s, e, _ in chosen:
            overlap = _overlap(cs, ce, s, e)
            if overlap > 0.35 * min(ce - cs, e - s):
                too_close = True
                break
            if min(abs(cs - e), abs(s - ce)) < min_gap_seconds:
                too_close = True
                break
        if not too_close:
            chosen.append(cand)
            if len(chosen) >= count:
                break
    return sorted(chosen, key=lambda x: x[0])


def choose_highlight_windows(duration, scene_times, count=1, clip_seconds=45,
                             silence_ranges=None, min_gap_seconds=12):
    ranked = rank_highlight_windows(
        duration, scene_times, count=count, clip_seconds=clip_seconds,
        silence_ranges=silence_ranges, min_gap_seconds=min_gap_seconds,
    )
    return [(s, e) for s, e, _ in ranked]
