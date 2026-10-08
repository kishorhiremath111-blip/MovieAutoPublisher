#!/usr/bin/env python3
"""Adaptive professional editing decisions for MovieAutoPublisher.

Chooses restrained, content-aware edits instead of applying every effect to
every video. Trend metadata can influence the profile, but never authorizes
copying third-party media.
"""
import re

def _tokens(text):
    return set(re.findall(r"[a-z0-9+#'-]{3,}", str(text or "").lower()))

def choose_profile(item, duration=0.0, scene_count=0, short=False):
    text = " ".join([
        str(item.get("title", "")), str(item.get("description", "")),
        str(item.get("category", "")), str(item.get("edit_style", "")),
        " ".join(item.get("tags", []) or []),
    ]).lower()
    t = _tokens(text)
    style = str(item.get("edit_style", "clean")).lower()

    if any(x in t for x in ("roast", "funny", "comedy", "meme", "reaction")):
        mode = "funny"
    elif any(x in t for x in ("dark", "crime", "thriller", "mystery", "horror")):
        mode = "dark"
    elif any(x in t for x in ("nature", "travel", "cinematic", "landscape", "wildlife")):
        mode = "cinematic"
    elif any(x in t for x in ("sports", "cricket", "football", "f1", "action", "anime", "gaming")):
        mode = "energy"
    elif any(x in t for x in ("news", "business", "health", "interview", "podcast", "explainer")):
        mode = "editorial"
    else:
        mode = style if style in {"funny", "dark", "cinematic", "energy", "editorial"} else "clean"

    intensity = 0.28
    if short:
        intensity += 0.12
    if scene_count >= 12:
        intensity += 0.10
    if duration and duration < 25:
        intensity += 0.08
    if mode in {"energy", "funny"}:
        intensity += 0.08
    if mode == "editorial":
        intensity -= 0.06
    if mode == "cinematic":
        intensity -= 0.03
    intensity = max(0.15, min(0.58, intensity))

    return {
        "mode": mode,
        "intensity": round(intensity, 2),
        "sharpen": intensity >= 0.38 and mode in {"energy", "funny"},
        "vignette": mode == "dark" and intensity <= 0.50,
        "audio_loudnorm": True,
        "audio_highpass": mode in {"editorial", "energy", "funny"},
        "fade": True,
    }

def filters(profile, width, height):
    mode = profile["mode"]
    intensity = profile["intensity"]
    vf = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}", "setsar=1",
    ]
    if mode == "dark":
        vf.append(f"eq=brightness={-0.018*intensity/0.3:.4f}:contrast={1.0+0.18*intensity:.3f}:saturation={1.0-0.16*intensity:.3f}")
        if profile["vignette"]:
            vf.append("vignette=PI/7")
    elif mode == "cinematic":
        vf.append(f"eq=contrast={1.0+0.10*intensity:.3f}:saturation={1.0+0.02*intensity:.3f}")
    elif mode == "energy":
        vf.append(f"eq=contrast={1.0+0.12*intensity:.3f}:saturation={1.0+0.07*intensity:.3f}")
    elif mode == "funny":
        vf.append(f"eq=contrast={1.0+0.08*intensity:.3f}:saturation={1.0+0.08*intensity:.3f}")
    elif mode == "editorial":
        vf.append(f"eq=contrast={1.0+0.05*intensity:.3f}:saturation={1.0-0.02*intensity:.3f}")
    if profile["sharpen"]:
        vf.append("unsharp=5:5:0.18:5:5:0.0")
    vf.append("format=yuv420p")
    return vf

def audio_filters(profile):
    af = []
    if profile.get("audio_highpass"):
        af.append("highpass=f=55")
    af.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    return ",".join(af)
