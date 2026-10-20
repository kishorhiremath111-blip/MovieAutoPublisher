# Series Clip Maker (rights-cleared workflow)

A small, standalone first step toward a professional web-series/movie Shorts editor. It detects visual scene changes in a **local video you own or are authorized to edit**, proposes candidate ranges, and can render one candidate as a 9:16 vertical MP4 draft.

## What it does
- Uses FFmpeg scene-change detection to propose timestamps (not a claim that a scene is popular).
- Writes a reviewable `scene_candidates.json` manifest.
- Optional vertical 1080×1920 render, H.264/AAC, loudness normalization, optional supplied SRT subtitles.
- Does not upload or publish anything; review the draft first.

## What it does not do
- Does not search streaming services for episodes, bypass DRM, or download/rip protected streams.
- Does not automatically determine real-world popularity. That needs reliable, authorized metadata or human review.
- A short clip is not automatically fair use or copyright-safe. Use only your own, licensed, public-domain, or otherwise authorized media.

## Requirements
Python 3.10+, FFmpeg and ffprobe on PATH. No extra Python packages are needed.

## Example
```bash
python series_clip_maker.py input/my_authorized_video.mp4 --i-have-rights
python series_clip_maker.py input/my_authorized_video.mp4 --i-have-rights --clip-seconds 35 --render 1
python series_clip_maker.py input/my_authorized_video.mp4 --i-have-rights --render 2 --subtitles input/captions.srt
```

Outputs are written to `output/series_clips/`. Open `scene_candidates.json`, inspect the timestamps, and watch the MP4 before using it. The script deliberately stops at a draft: public YouTube publishing must remain a separate, explicit action using an authorized account and content.
