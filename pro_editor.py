#!/usr/bin/env python3
"""Scene-aware edit profiles for authorized source footage."""
import re

def _tokens(text):
    return set(re.findall(r"[a-z0-9+#'-]{3,}", str(text or "").lower()))

def choose_profile(item, duration=0.0, scene_count=0, short=False):
    text = " ".join([str(item.get("title", "")), str(item.get("description", "")),
        str(item.get("category", "")), str(item.get("edit_style", "")),
        " ".join(item.get("tags", []) or [])]).lower()
    tokens = _tokens(text)
    style = str(item.get("edit_style", "clean")).lower()
    if tokens & {"roast", "funny", "comedy", "meme", "reaction"}:
        mode = "funny"
    elif tokens & {"dark", "crime", "thriller", "mystery", "horror", "suspense"}:
        mode = "dark"
    elif tokens & {"nature", "travel", "cinematic", "landscape", "wildlife", "romance"}:
        mode = "cinematic"
    elif tokens & {"sports", "cricket", "football", "f1", "action", "anime", "gaming", "fight"}:
        mode = "energy"
    elif tokens & {"news", "business", "health", "interview", "podcast", "explainer"}:
        mode = "editorial"
    else:
        mode = style if style in {"funny", "dark", "cinematic", "energy", "editorial"} else "clean"
    intensity = 0.30 + (0.10 if short else 0.0)
    intensity += min(0.10, max(0, int(scene_count)) * 0.008)
    if duration and duration < 25:
        intensity += 0.04
    if mode in {"energy", "funny"}:
        intensity += 0.08
    elif mode == "editorial":
        intensity -= 0.08
    elif mode == "cinematic":
        intensity -= 0.04
    intensity = max(0.18, min(0.58, intensity))
    return {"mode": mode, "intensity": round(intensity, 2),
        "sharpen": mode in {"energy", "funny"} and intensity >= 0.38,
        "vignette": mode == "dark",
        "audio_highpass": mode in {"editorial", "energy", "funny"},
        "fade": True}

def filters(profile, width, height):
    mode, intensity = profile["mode"], profile["intensity"]
    vf = [f"scale={width}:{height}:force_original_aspect_ratio=increase",
          f"crop={width}:{height}", "setsar=1"]
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
        vf.append("unsharp=5:5:0.22:5:5:0.0")
    vf += ["fade=t=in:st=0:d=0.12", "format=yuv420p"]
    return vf

def audio_filters(profile):
    af = []
    if profile.get("audio_highpass"):
        af.append("highpass=f=55")
    af.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    return ",".join(af)
