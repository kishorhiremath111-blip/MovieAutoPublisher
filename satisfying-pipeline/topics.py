#!/usr/bin/env python3
"""Topic engine.

Har topic = (scene, palette, shape, material, bpm, camera, density, background).
Total combinations ~6.9 million. Ek counter ko "bijective shuffle" se topic
index me badla jata hai, isliye:
  * koi topic dobara nahi aata (counter sirf aage badhta hai)
  * 1,000,000+ line ki file store karne ki zaroorat nahi
"""
import argparse
import json
import sys
from math import gcd

SCENES = ["ripple", "domino", "jar", "tunnel", "bubbles", "helix"]

TITLE_TEMPLATES = {
    "ripple": "{pal} {mat} {shape} Ripple Wave",
    "domino": "{pal} {mat} Domino Spiral",
    "jar": "{pal} {shape} Filling a Jar",
    "tunnel": "{pal} {shape} Endless Tunnel",
    "bubbles": "Popping {pal} {shape}",
    "helix": "{pal} {mat} {shape} Helix Dance",
}

# name, hue start (0-1), hue span (0-1), saturation, lightness
PALETTES = [
    ("Rainbow", 0.00, 1.00, 0.80, 0.58),
    ("Candy Pastel", 0.00, 1.00, 0.75, 0.74),
    ("Sunset", 0.92, 0.20, 0.85, 0.60),
    ("Ocean", 0.50, 0.15, 0.80, 0.55),
    ("Lagoon", 0.42, 0.18, 0.75, 0.58),
    ("Berry", 0.85, 0.12, 0.75, 0.55),
    ("Bubblegum", 0.90, 0.10, 0.85, 0.72),
    ("Mint", 0.38, 0.10, 0.65, 0.68),
    ("Lemon Lime", 0.15, 0.20, 0.90, 0.58),
    ("Orange Soda", 0.05, 0.08, 0.95, 0.58),
    ("Grape", 0.75, 0.10, 0.70, 0.60),
    ("Aurora", 0.35, 0.40, 0.80, 0.60),
    ("Galaxy", 0.65, 0.25, 0.75, 0.58),
    ("Ice", 0.55, 0.08, 0.60, 0.78),
    ("Fire", 0.00, 0.12, 0.95, 0.55),
    ("Forest", 0.30, 0.10, 0.55, 0.48),
    ("Peach", 0.04, 0.06, 0.85, 0.78),
    ("Cotton Candy", 0.55, 0.35, 0.65, 0.80),
    ("Tropical", 0.08, 0.45, 0.85, 0.58),
    ("Neon", 0.00, 1.00, 1.00, 0.55),
    ("Gold", 0.12, 0.04, 0.90, 0.58),
    ("Rose", 0.97, 0.05, 0.70, 0.68),
    ("Sky", 0.58, 0.06, 0.80, 0.72),
    ("Spring", 0.20, 0.30, 0.70, 0.66),
]

SHAPES = ["cube", "sphere", "cylinder", "cone", "torus", "octahedron", "icosahedron", "dodecahedron"]
SHAPE_PLURAL = {
    "cube": "Cubes", "sphere": "Balls", "cylinder": "Cylinders", "cone": "Cones",
    "torus": "Rings", "octahedron": "Diamonds", "icosahedron": "Gems", "dodecahedron": "Crystals",
}

MATERIALS = ["candy", "clay", "metal", "pearl", "neon", "glass"]
MATERIAL_ADJ = {
    "candy": "Glossy", "clay": "Clay", "metal": "Metallic",
    "pearl": "Pearl", "neon": "Neon", "glass": "Glass",
}

BPMS = [84, 92, 100, 108, 116]
CAMERAS = ["orbit", "low", "top", "dolly", "sway"]
DENSITIES = [0, 1, 2, 3]
BACKGROUNDS = [
    ("#1b1035", "#3a1c71"), ("#0f2027", "#2c5364"), ("#2b1055", "#7597de"),
    ("#141e30", "#243b55"), ("#42275a", "#734b6d"), ("#0b3d5c", "#1d8a99"),
    ("#3a0f2e", "#c04a7a"), ("#10261e", "#2f7f62"), ("#2a1a05", "#a8601b"),
    ("#16103a", "#0f6a7a"),
]

DIMS = [SCENES, PALETTES, SHAPES, MATERIALS, BPMS, CAMERAS, DENSITIES, BACKGROUNDS]
SIZES = [len(d) for d in DIMS]
TOTAL = 1
for _s in SIZES:
    TOTAL *= _s


def _step(n):
    a = 2654435761 % n
    if a < 2:
        a = 7919
    while gcd(a, n) != 1:
        a += 1
    return a


STEP = _step(TOTAL)
OFFSET = 987654321 % TOTAL


def index_for(counter):
    """counter (0,1,2,...) -> unique topic index. Bijection, so no repeats."""
    if counter < 0 or counter >= TOTAL:
        raise RuntimeError("Saare %d topics use ho chuke hain." % TOTAL)
    return (STEP * counter + OFFSET) % TOTAL


def decode(idx):
    vals = []
    for size in SIZES:
        idx, r = divmod(idx, size)
        vals.append(r)
    return vals


def build_topic(counter, target_seconds=28):
    idx = index_for(counter)
    sc, pa, sh, ma, bp, ca, de, bg = decode(idx)
    scene = SCENES[sc]
    pname, hue0, span, sat, light = PALETTES[pa]
    shape = SHAPES[sh]
    if scene == "domino":
        shape = "cube"  # dominoes hamesha ek hi shape
    material = MATERIALS[ma]
    bpm = BPMS[bp]
    n_beats = max(16, int(target_seconds * bpm / 60) // 4 * 4)
    duration = round(n_beats * 60.0 / bpm, 3)
    seed = (idx * 2654435761 + 12345) & 0xFFFFFFFF

    params = {
        "scene": scene, "palette": pname, "hue0": hue0, "span": span, "sat": sat, "light": light,
        "shape": shape, "material": material, "bpm": bpm, "beat": 60.0 / bpm,
        "camera": CAMERAS[ca], "density": DENSITIES[de], "bg": list(BACKGROUNDS[bg]),
        "seed": seed, "duration": duration,
    }
    core = TITLE_TEMPLATES[scene].format(
        pal=pname, mat=MATERIAL_ADJ[material], shape=SHAPE_PLURAL[shape])
    title = (core + " | Satisfying 3D #Shorts")[:100]
    description = (
        "%s\n\nRelax and enjoy this oddly satisfying 3D animation. "
        "Soft sounds, smooth colors, perfect loops for your eyes.\n\n"
        "New satisfying video every day. Subscribe!\n\n"
        "#satisfying #oddlysatisfying #3d #asmr #relaxing #shorts #kids" % core
    )
    tags = ["satisfying", "oddly satisfying", "3d animation", "asmr", "relaxing", "shorts",
            "kids", pname.lower(), scene, shape, material]
    return {
        "counter": counter, "index": idx, "topic_id": "SAT-%08d" % idx,
        "title": title, "description": description, "tags": tags, "params": params,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", action="store_true")
    ap.add_argument("--preview", type=int, default=0, help="pehle N topics dikhao")
    ap.add_argument("--start", type=int, default=0)
    a = ap.parse_args()
    if a.total or not a.preview:
        print("Total unique topics:", TOTAL)
    for c in range(a.start, a.start + a.preview):
        t = build_topic(c)
        print("%7d  %s  %s" % (c, t["topic_id"], t["title"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
