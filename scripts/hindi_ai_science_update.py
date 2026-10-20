#!/usr/bin/env python3
"""Render a Hindi AI/science explainer Short in GitHub Actions with a male Hindi voice."""
import math, os, subprocess, asyncio
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import edge_tts

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "hindi_ai_science"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1080, 1920
FPS = 25
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
def font(size, bold=True):
    for p in FONT_CANDIDATES:
        if os.path.exists(p) and (not bold or "Bold" in p):
            return ImageFont.truetype(p, size)
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

SCENES = [
    ("AI UPDATE 2026", "AI अब सिर्फ़ सवालों के जवाब नहीं दे रहा…", "ये कई स्टेप वाले काम भी प्लान कर सकता है।"),
    ("HOW IT WORKS", "तुम लक्ष्य बताते हो, AI काम को छोटे हिस्सों में बाँटता है।", "फिर टूल्स की मदद से एक-एक स्टेप पूरा करता है।"),
    ("SCIENCE MODE", "रिसर्च में AI पेपर पढ़ने और डेटा समझने में मदद करता है।", "लेकिन नतीजे इंसान को जाँचने ही पड़ते हैं।"),
    ("REALITY CHECK", "AI आत्मविश्वास से गलत जवाब भी दे सकता है।", "इसलिए सोर्स और तारीख हमेशा चेक करो।"),
    ("WHAT'S NEXT", "अगला बड़ा बदलाव होगा AI + रोबोटिक्स का मेल।", "सॉफ्टवेयर की प्लानिंग, असली दुनिया के कामों तक।"),
    ("TAKEAWAY", "AI तेज़ है, पर जादू नहीं।", "सवाल पूछो, सोर्स जाँचो, फिर भरोसा करो।"),
]
