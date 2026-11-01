#!/usr/bin/env python3
"""Render a short real 4K60 MP4 and verify its encoded streams with ffprobe."""
import json
import subprocess
import tempfile
from pathlib import Path

import topics
from render_video import render_video


def main():
    params = dict(topics.build_topic(3, 28)["params"])
    params.update({
        "scene": "gaprun",
        "duration": 1.2,
        "beat": 0.5,
        "level": 1,
        "multiplier": 1,
    })
    with tempfile.TemporaryDirectory(prefix="shorts-4k-qa-") as temp:
        root = Path(temp)
        video = root / "sample-4k60.mp4"
        render_video(
            params, video, width=2160, height=3840, fps=60,
            workdir=root / "work",
        )
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
                "-of", "json", str(video),
            ],
            capture_output=True, text=True, check=True,
        )
        info = json.loads(result.stdout or "{}")
        streams = info.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        codec = video_stream.get("codec_name")
        fps = video_stream.get("avg_frame_rate", "")
        duration = float(info.get("format", {}).get("duration", 0) or 0)
        if (width, height) != (2160, 3840):
            raise AssertionError("Expected 2160x3840 MP4, got %dx%d." % (width, height))
        if codec != "h264":
            raise AssertionError("Expected H.264 video stream, got %s." % codec)
        if fps not in ("60/1", "60000/1001"):
            raise AssertionError("Expected 60fps output, got %s." % fps)
        if not audio_stream or audio_stream.get("codec_name") != "aac":
            raise AssertionError("Expected AAC audio stream.")
        if duration < 1.0:
            raise AssertionError("Encoded MP4 is unexpectedly short: %.3fs" % duration)
        print("PASS: encoded 4K60 MP4 %dx%d / %s fps / H.264 + AAC / %.2fs" %
              (width, height, fps, duration))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
