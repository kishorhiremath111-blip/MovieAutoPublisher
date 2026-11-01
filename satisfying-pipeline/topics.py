#!/usr/bin/env python3
"""Procedural 3D Shorts topic engine with distinct, high-energy visual recipes."""
import argparse
import sys
from math import gcd

# Every scene below has its own geometry and motion system in renderer/scenes.js.
SCENES = [
    "ripple", "domino", "jar", "tunnel", "bubbles", "helix",
    "orbit", "crystal", "vortex", "wave", "spiral",
]
SCENE_NAMES = {
    "ripple": "Liquid Ripple", "domino": "Domino Chain Reaction",
    "jar": "Perfect Sphere Cascade", "tunnel": "Infinite Prism Tunnel",
    "bubbles": "Bubble Pop Symphony", "helix": "Helix Orbit",
    "orbit": "Orbital Ring Machine", "crystal": "Crystal Core Assembly",
    "vortex": "Neon Particle Vortex", "wave": "Sculpted Wave Field",
    "spiral": "Golden Spiral Stack",
}
TITLE_TEMPLATES = {
    scene: "{pal} {name}"
    for scene, name in SCENE_NAMES.items()
}

# High-saturation palettes. The renderer cycles the hues through each recipe.
PALETTES = [
    ("Prism Pop", 0.00, 1.00, 1.00, 0.60),
    ("Laser Magenta", 0.88, 0.16, 1.00, 0.62),
    ("Electric Cyan", 0.50, 0.12, 1.00, 0.64),
    ("Toxic Lime", 0.24, 0.13, 1.00, 0.58),
    ("Solar Flare", 0.08, 0.13, 1.00, 0.61),
    ("Ultraviolet", 0.72, 0.18, 1.00, 0.62),
    ("Hot Coral", 0.98, 0.12, 1.00, 0.65),
    ("Arctic Glow", 0.53, 0.09, 0.95, 0.73),
    ("Aurora Pulse", 0.35, 0.42, 1.00, 0.62),
    ("Cyber Rainbow", 0.00, 1.00, 1.00, 0.56),
    ("Tangerine Pop", 0.06, 0.11, 1.00, 0.62),
    ("Electric Orchid", 0.79, 0.15, 1.00, 0.67),
    ("Aqua Flame", 0.46, 0.20, 1.00, 0.63),
    ("Lava Chrome", 0.01, 0.18, 1.00, 0.57),
    ("Blue Voltage", 0.59, 0.16, 1.00, 0.60),
    ("Candy Burst", 0.91, 0.28, 1.00, 0.72),
    ("Emerald Laser", 0.31, 0.16, 1.00, 0.57),
    ("Rose Gold Pop", 0.96, 0.10, 0.95, 0.67),
    ("Amethyst Ice", 0.70, 0.13, 0.92, 0.72),
    ("Lemon Shock", 0.16, 0.13, 1.00, 0.68),
    ("Deep Sea Neon", 0.48, 0.24, 1.00, 0.55),
    ("Firework Mix", 0.02, 0.95, 1.00, 0.64),
    ("Cotton Candy Glow", 0.84, 0.33, 0.98, 0.75),
    ("Tropical Laser", 0.39, 0.57, 1.00, 0.61),
    ("Peacock Prism", 0.43, 0.46, 1.00, 0.58),
    ("Ruby Radiance", 0.97, 0.08, 1.00, 0.58),
    ("Icebreaker", 0.55, 0.10, 0.95, 0.78),
    ("Galaxy Spectrum", 0.63, 0.37, 1.00, 0.59),
    ("Hyper Neon", 0.00, 1.00, 1.00, 0.65),
    ("Golden Pulse", 0.12, 0.10, 1.00, 0.64),
    ("Mint Voltage", 0.40, 0.10, 0.98, 0.70),
    ("Rainbow Glass", 0.00, 1.00, 0.90, 0.72),
]
SHAPES = ["cube", "sphere", "cylinder", "cone", "torus", "octahedron", "icosahedron", "dodecahedron"]
SHAPE_PLURAL = {
    "cube": "Cubes", "sphere": "Spheres", "cylinder": "Cylinders", "cone": "Cones",
    "torus": "Rings", "octahedron": "Diamonds", "icosahedron": "Gems", "dodecahedron": "Crystals",
}
MATERIALS = ["candy", "chrome", "prism", "pearl", "neon", "glass", "ceramic", "liquid-metal"]
MATERIAL_ADJ = {
    "candy": "Glossy Candy", "chrome": "Mirror Chrome", "prism": "Prismatic",
    "pearl": "Iridescent Pearl", "neon": "Neon", "glass": "Crystal Glass",
    "ceramic": "Polished Ceramic", "liquid-metal": "Liquid Metal",
}
BPMS = [88, 96, 104, 112, 120]
CAMERAS = ["orbit", "low", "top", "dolly", "sweep"]
DENSITIES = [0, 1, 2, 3]
# All episodes use a true black background; color comes from the 3D objects and lights.
BACKGROUNDS = [("#000000", "#000000")]
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
    core = TITLE_TEMPLATES[scene].format(pal=palette, name=SCENE_NAMES[scene])
    suffix = " | %s %s #%08d #Shorts" % (
        MATERIAL_ADJ[material], SHAPE_PLURAL[shape], index
    )
    title = core[:max(0, 100 - len(suffix))] + suffix
    description = (
        "%s — an original procedural 3D animation, designed on a true-black stage "
        "with vivid color, polished materials, rhythmic motion and a visual payoff. "
        "Original soundscape made for this episode.\n\n"
        "#satisfying #oddlysatisfying #3danimation #3dshorts #asmr #shorts" % core
    )
    tags = [
        "satisfying", "oddly satisfying", "high quality 3d", "3d animation",
        "procedural 3d", "original sound design", "asmr", "shorts",
        palette.lower(), scene, shape, material, CAMERAS[camera_i],
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
        print("Total unique upgraded 3D topic recipes:", TOTAL)
    for counter in range(args.start, args.start + args.preview):
        topic = build_topic(counter)
        p = topic["params"]
        print("%7d  %s  %s | scene=%s palette=%s shape=%s material=%s" % (
            counter, topic["topic_id"], topic["title"],
            p["scene"], p["palette"], p["shape"], p["material"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
