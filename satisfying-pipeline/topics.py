#!/usr/bin/env python3
"""Deterministic topic engine: every counter maps to a unique visual recipe."""
import argparse
import sys
from math import gcd

SCENES = ["ripple", "domino", "jar", "tunnel", "bubbles", "helix"]
TITLE_TEMPLATES = {
    "ripple": "{pal} {mat} {shape} Ripple Wave",
    "domino": "{pal} {mat} Domino Spiral",
    "jar": "{pal} {shape} Jar Fill",
    "tunnel": "{pal} {shape} Endless Tunnel",
    "bubbles": "{pal} {shape} Bubble Pop Wall",
    "helix": "{pal} {mat} {shape} Helix Dance",
}
PALETTES = [
    ("Rainbow", 0.00, 1.00, 0.80, 0.58), ("Candy Pastel", 0.00, 1.00, 0.75, 0.74),
    ("Sunset", 0.92, 0.20, 0.85, 0.60), ("Ocean", 0.50, 0.15, 0.80, 0.55),
    ("Lagoon", 0.42, 0.18, 0.75, 0.58), ("Berry", 0.85, 0.12, 0.75, 0.55),
    ("Bubblegum", 0.90, 0.10, 0.85, 0.72), ("Mint", 0.38, 0.10, 0.65, 0.68),
    ("Lemon Lime", 0.15, 0.20, 0.90, 0.58), ("Orange Soda", 0.05, 0.08, 0.95, 0.58),
    ("Grape", 0.75, 0.10, 0.70, 0.60), ("Aurora", 0.35, 0.40, 0.80, 0.60),
    ("Galaxy", 0.65, 0.25, 0.75, 0.58), ("Ice", 0.55, 0.08, 0.60, 0.78),
    ("Fire", 0.00, 0.12, 0.95, 0.55), ("Forest", 0.30, 0.10, 0.55, 0.48),
    ("Peach", 0.04, 0.06, 0.85, 0.78), ("Cotton Candy", 0.55, 0.35, 0.65, 0.80),
    ("Tropical", 0.08, 0.45, 0.85, 0.58), ("Neon", 0.00, 1.00, 1.00, 0.55),
    ("Gold", 0.12, 0.04, 0.90, 0.58), ("Rose", 0.97, 0.05, 0.70, 0.68),
    ("Sky", 0.58, 0.06, 0.80, 0.72), ("Spring", 0.20, 0.30, 0.70, 0.66),
]
SHAPES = ["cube", "sphere", "cylinder", "cone", "torus", "octahedron", "icosahedron", "dodecahedron"]
SHAPE_PLURAL = {
    "cube": "Cubes", "sphere": "Spheres", "cylinder": "Cylinders", "cone": "Cones",
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
SIZES = [len(x) for x in DIMS]
TOTAL = 1
for size in SIZES:
    TOTAL *= size


def _step(n):
    value = 2654435761 % n
    if value < 2:
        value = 7919
    while gcd(value, n) != 1:
        value += 1
    return value


STEP = _step(TOTAL)
OFFSET = 987654321 % TOTAL


def index_for(counter):
    if counter < 0 or counter >= TOTAL:
        raise RuntimeError("All %d unique topics have been used." % TOTAL)
    return (STEP * counter + OFFSET) % TOTAL


def decode(index):
    values = []
    for size in SIZES:
        index, remainder = divmod(index, size)
        values.append(remainder)
    return values


def build_topic(counter, target_seconds=28):
    index = index_for(counter)
    scene_i, palette_i, shape_i, material_i, bpm_i, camera_i, density_i, bg_i = decode(index)
    scene = SCENES[scene_i]
    palette, hue0, span, saturation, lightness = PALETTES[palette_i]
    shape = SHAPES[shape_i]
    if scene == "domino":
        shape = "cube"
    material = MATERIALS[material_i]
    bpm = BPMS[bpm_i]
    beats = max(16, int(target_seconds * bpm / 60) // 4 * 4)
    duration = round(beats * 60.0 / bpm, 3)
    seed = (index * 2654435761 + 12345) & 0xFFFFFFFF
    topic_id = "SAT-%08d" % index
    level = counter + 1

    params = {
        "scene": scene, "palette": palette, "hue0": hue0, "span": span,
        "sat": saturation, "light": lightness, "shape": shape, "material": material,
        "bpm": bpm, "beat": 60.0 / bpm, "camera": CAMERAS[camera_i],
        "density": DENSITIES[density_i], "bg": list(BACKGROUNDS[bg_i]),
        "seed": seed, "duration": duration,
    }
    core = TITLE_TEMPLATES[scene].format(
        pal=palette, mat=MATERIAL_ADJ[material], shape=SHAPE_PLURAL[shape])
    title = ("%s | %s L%05d #%08d #Shorts" % (
        core, CAMERAS[camera_i].title(), level, index))[:100]
    description = (
        "%s\n\nAn original, procedurally animated 3D pattern with a soundscape "
        "generated specifically for this episode. Watch the pattern build to its "
        "final level-up moment.\n\n"
        "#satisfying #oddlysatisfying #3danimation #asmr #shorts" % core
    )
    tags = [
        "satisfying", "oddly satisfying", "3d animation", "original sound design",
        "asmr", "shorts", palette.lower(), scene, shape, material, CAMERAS[camera_i],
    ]
    return {
        "counter": counter, "index": index, "topic_id": topic_id, "level": level,
        "title": title, "description": description, "tags": tags, "params": params,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", action="store_true")
    parser.add_argument("--preview", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    args = parser.parse_args()
    if args.total or not args.preview:
        print("Total unique topic recipes:", TOTAL)
    for counter in range(args.start, args.start + args.preview):
        topic = build_topic(counter)
        p = topic["params"]
        print("%7d  %s  %s | %s %s %s %s" % (
            counter, topic["topic_id"], topic["title"],
            p["scene"], p["palette"], p["shape"], p["material"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
