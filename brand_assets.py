#!/usr/bin/env python3
"""Prepare authorized TaskEarn brand assets from an APK or supplied images."""
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
APK=ROOT/"input"/"taskearn.apk"
OUT=ROOT/"input"/"brand_assets"
EXTS={".png",".jpg",".jpeg",".webp"}

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    if APK.exists():
        with zipfile.ZipFile(APK) as z:
            names=[n for n in z.namelist()
                   if Path(n).suffix.lower() in EXTS
                   and ("/drawable" in n or "/mipmap" in n or n.startswith("assets/"))]
            names=sorted(names,key=lambda n:z.getinfo(n).file_size,reverse=True)[:30]
            for i,name in enumerate(names):
                try:
                    (OUT/f"apk_asset_{i}{Path(name).suffix.lower()}").write_bytes(z.read(name))
                except Exception:
                    pass
            print(f"TaskEarn APK assets prepared: {len(names)}")
    for p in OUT.iterdir():
        if p.is_file() and p.suffix.lower() in EXTS:
            print("Brand asset:",p.relative_to(ROOT))

if __name__=="__main__":
    prepare()
