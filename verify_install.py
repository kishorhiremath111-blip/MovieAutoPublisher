#!/usr/bin/env python3
"""verify_install.py - checks that every Luxury file in your repo is EXACTLY the shipped version.
Run from the repo root:  python verify_install.py     (stdlib only, changes nothing)
OK = identical | MISSING = not uploaded | DIFFERENT = old, edited, or cut short while uploading
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    ".github/workflows/daily.yml": "e2dcb7674195dc88edb504e278429473c69c70915e7634e0517717882546435e",
    ".github/workflows/luxury-editor.yml": "6be61e1ad02b20f82253d0e58847abfb964ad4c9b1c8194f1b4e59969d7c8c60",
    ".github/workflows/gemini-check.yml": "76dd67372c4685a2022b18d064bfa4ae6956a8c573d6183dd236096122e4274c",
    "gemini_check.py": "a444eaaad4e442e9f3dec292a855f5c48537ad94f11601191d21dd5eee66a68c",
    "luxury_pipeline/youtube_device_auth.py": "198a513421d2d4d65abde04f5d5561f9ffc0da0b3f441265de7cbc54d1848671",
    "luxury_pipeline/requirements.txt": "a005489757bfc93583ebacfc2ae311bd8122e230814a5ba8941298d1b1d2d2dc",
    "luxury_pipeline/README.md": "40403657c1a078f2502e4de46059be09a59ce29bfdae047f54f91904fbb4ef37",
    "luxury_pipeline/music/README.txt": "e85fa6781d73fd7c979c266a62aad45b470d9a548f492a70cd71062afb0f1023"
}


def sha(b):
    return hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest()


bad = 0
for rel, want in EXPECTED.items():
    f = ROOT / rel
    if not f.exists():
        print(f"MISSING    {rel}")
        bad += 1
    elif sha(f.read_bytes()) != want:
        print(f"DIFFERENT  {rel}  ({f.stat().st_size} bytes)")
        bad += 1
    else:
        print(f"OK         {rel}")
print("\nALL MANIFEST FILES OK (custom stock-only runtime files are syntax-checked by workflow)" if not bad else f"\n{bad} file(s) need fixing: upload the shipped version again.")
sys.exit(1 if bad else 0)
