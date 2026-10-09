#!/usr/bin/env python3
"""Small, scene-safe on-screen caption helper for authorized movie/series/anime clips.

This selects short on-screen text, not a voice-over or an invented plot summary.
Creators can set caption_text/hook_text explicitly in metadata for scene-specific wording.
"""
import hashlib
import re
from datetime import date

BANKS = {
    "funny": [
        "BHAI, TIMING DEKHO", "PLAN TOH KUCH AUR THA", "THAT REACTION THOUGH",
        "BAS YEHI DEKHNA THA", "NO WORDS NEEDED", "THE LOOK SAYS IT ALL",
        "WAIT FOR THAT REACTION", "SCENE HI PALAT GAYA", "CAUGHT IN 4K",
        "THIS AGED BADLY"
    ],
    "anime": [
        "AURA ON ANOTHER LEVEL", "THAT ENTRY THOUGH", "ONE MOVE. FULL IMPACT.",
        "THE LOOK BEFORE THE STORM", "PEAK ANIME MOMENT", "POWER-UP ENERGY",
        "SILENCE BEFORE THE FIGHT", "THIS FRAME GOES HARD", "THE TURNING POINT",
        "WHEN THE MUSIC HITS"
    ],
    "energy": [
        "THAT ENTRY THOUGH", "THE MOMENT IT FLIPPED", "NO EASY WAY OUT",
        "WATCH THE TIMING", "THE COMEBACK STARTS HERE", "ONE MOVE CHANGES IT",
        "THE BUILD-UP WAS WORTH IT", "THIS MOMENT HITS DIFFERENT"
    ],
    "dark": [
        "SILENCE BEFORE THE STORM", "THE ROOM CHANGED IN A SECOND",
        "NOTHING ABOUT THIS FEELS RIGHT", "THE LOOK SAYS ENOUGH",
        "WAIT FOR THE REVEAL", "THE TENSION IS REAL", "THE TURNING POINT"
    ],
    "cinematic": [
        "A FRAME WORTH KEEPING", "THE MOMENT THAT STAYS", "LOOK AT THE DETAIL",
        "ONE SCENE. A WHOLE MOOD.", "THE PAUSE BEFORE THE TURN",
        "THIS SHOT HITS DIFFERENT", "THE STORY IS IN THE LOOK"
    ],
    "clean": [
        "THE LOOK SAYS IT ALL", "ONE SCENE. FULL MOOD.", "WAIT FOR THAT MOMENT",
        "THIS PART STAYS WITH YOU", "A MOMENT WORTH REPLAYING", "NO WORDS NEEDED",
        "THE DETAIL MAKES IT"
    ],
}

PALETTES = {
    "funny": ("0xFFE36E", "0xF2B300"),
    "anime": ("0xFF83D3", "0xA855F7"),
    "energy": ("0xFFC078", "0xFF6B35"),
    "dark": ("0xB9F3FF", "0x45D5E8"),
    "cinematic": ("0xFFE2A8", "0xD8A44A"),
    "clean": ("0xFFFFFF", "0x55DDEE"),
}


def style_for(item):
    kind = str(item.get("type", item.get("category", ""))).lower()
    style = str(item.get("edit_style", "")).lower()
    text = " ".join([
        str(item.get("title", "")),
        str(item.get("description", "")),
        str(item.get("category", "")),
        " ".join(str(x) for x in (item.get("tags") or [])),
        style,
    ]).lower()
    if kind == "anime" or "anime" in text:
        return "anime"
    if style == "funny" or any(w in text for w in ("comedy", "funny", "meme", "roast", "reaction")):
        return "funny"
    if style == "dark" or any(w in text for w in ("thriller", "mystery", "dark", "horror")):
        return "dark"
    if any(w in text for w in ("action", "fight", "battle", "power", "gaming", "sports")):
        return "energy"
    if style == "cinematic" or kind in ("movie", "series"):
        return "cinematic"
    return "clean"


def caption_line(item, role="short"):
    explicit = str(item.get("caption_text") or item.get("hook_text") or "").strip()
    if explicit:
        explicit = re.sub(r"\s+", " ", explicit)
        # Overlay text is intentionally short to remain readable and unobtrusive.
        return explicit[:46].rstrip()
    style = style_for(item)
    options = BANKS[style]
    item_id = str(item.get("id") or item.get("item_id") or item.get("_detected_title") or item.get("title") or "")
    day = date.today().isoformat()
    index = int(hashlib.sha256(f"{day}|{item_id}|{role}".encode()).hexdigest()[:8], 16) % len(options)
    return options[index]


def palette(item):
    return PALETTES[style_for(item)]


def description_line(item):
    return caption_line(item, "description")
