#!/usr/bin/env python3
"""Isolated Luxury Shorts renderer for MovieAutoPublisher.

Reads ONLY files under this tool's own project directory. It never scans the
existing MovieAutoPublisher video folders or downloads legacy video sources.
Set GEMINI_API_KEY in GitHub Actions secrets to enable prompt-based image creation.
"""
import argparse, base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
except ImportError:
    print("Install Pillow first: pip install pillow", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent
FPS = 30

def require(cmd):
    if not shutil.which(cmd):
        raise SystemExit(f"Required executable not found: {cmd}")

def fit_image(src, dst, size):
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im = ImageOps.fit(im, size, method=Image.Resampling.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=45, threshold=3))
    im.save(dst, "JPEG", quality=94)

def hook_png(text, path, size):
    w, h = size
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    font = None
    for fp in font_paths:
        if Path(fp).exists():
            font = ImageFont.truetype(fp, max(42, int(w * .075)))
            break
    if font is None:
        font = ImageFont.load_default()
    words, lines, line = text.upper().split(), [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) <= w * .84:
            line = trial
        else:
            if line: lines.append(line)
            line = word
    if line: lines.append(line)
    if len(lines) > 5:
        raise SystemExit("Hook too long; use 12 words or fewer.")
    line_h = int(font.size * 1.22)
    y = int(h * .35) - (len(lines) * line_h)//2
    for s in lines:
        x = (w - draw.textlength(s, font=font)) / 2
        draw.text((x, y), s, font=font, fill=(232,194,90,255),
                  stroke_width=max(3, font.size//28), stroke_fill=(0,0,0,255))
        y += line_h
    im.save(path)

def generate_image(prompt, destination, ratio):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise SystemExit("Scene prompt needs GEMINI_API_KEY configured in GitHub repository Actions secrets.")
    model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt + ". Photorealistic, premium luxury editorial photography, cinematic natural lighting, sharp details, vertical social video image, no text, no watermark, no logos, no identifiable real person's face."}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": ratio}}
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json","x-goog-api-key":key})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as response:
                result = json.loads(response.read().decode("utf-8"))
            for part in result.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in part:
                    destination.write_bytes(base64.b64decode(part["inlineData"]["data"]))
                    return
            raise SystemExit(f"Gemini returned no image for prompt: {prompt[:80]}")
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403, 404):
                raise SystemExit(f"Gemini image API rejected request (HTTP {exc.code}); check GEMINI_IMAGE_MODEL and GEMINI_API_KEY.")
            if attempt == 2: raise
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2: raise
            time.sleep(2 ** attempt)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=str(ROOT / "project.json"))
    ap.add_argument("--output", default=str(ROOT / "output" / "luxury-short.mp4"))
    ap.add_argument("--resolution", choices=["1080", "4k"], default="1080")
    args = ap.parse_args()
    require("ffmpeg"); require("ffprobe")
    project_path = Path(args.project).resolve()
    # Hard boundary: project and all local image assets must live in this isolated folder.
    if ROOT not in project_path.parents:
        raise SystemExit("Project must be inside luxury_editor/; outside sources are blocked.")
    project = json.loads(project_path.read_text(encoding="utf-8"))
    scenes = project.get("scenes", [])
    if not 3 <= len(scenes) <= 14:
        raise SystemExit("project.json must contain 3 to 14 scenes.")
    hook = str(project.get("hook", "")).strip()
    if not hook: raise SystemExit("project.json needs a hook.")
    w, h = (2160,3840) if args.resolution == "4k" else (1080,1920)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="luxury-editor-") as td:
        td = Path(td)
        inputs, filters, durations = [], [], []
        for i, scene in enumerate(scenes):
            image = scene.get("image")
            prompt = scene.get("prompt")
            if image:
                src = (ROOT / image).resolve()
                if ROOT not in src.parents or not src.is_file():
                    raise SystemExit(f"Scene {i+1}: image must exist inside luxury_editor/: {image}")
            elif prompt:
                src = td / f"generated-scene{i}.png"
                print(f"Generating original scene {i+1} with Gemini...")
                generate_image(str(prompt), src, "9:16")
            else:
                raise SystemExit(f"Scene {i+1} needs either 'image' or 'prompt'.")
            tile = td / f"scene{i}.jpg"
            fit_image(src, tile, (w,h))
            inputs += ["-loop","1","-framerate",str(FPS),"-t",str(float(scene.get("seconds",4.5))),"-i",str(tile)]
            n = max(1, round(float(scene.get("seconds",4.5))*FPS))
            filters.append(f"[{i}:v]zoompan=z='min(zoom+0.0007,1.08)':d={n}:s={w}x{h}:fps={FPS},setsar=1,format=yuv420p[v{i}]")
            durations.append(float(scene.get("seconds",4.5)))
        hk = td / "hook.png"; hook_png(hook, hk, (w,h))
        inputs += ["-loop","1","-framerate",str(FPS),"-t",str(durations[0]),"-i",str(hk)]
        idx = len(scenes)
        filters.append(f"[v0][{idx}:v]overlay=0:0:format=auto[v0h]")
        prev = "v0h"
        offset = durations[0]
        for i in range(1,len(scenes)):
            off = max(0.1, offset - i*0.5)
            filters.append(f"[{prev}][v{i}]xfade=transition=fade:duration=0.5:offset={off:.3f}[x{i}]")
            prev = f"x{i}"
            offset += durations[i]
        total = sum(durations) - .5*(len(scenes)-1)
        music = project.get("music")
        if music and music != "auto":
            m = (ROOT / music).resolve()
            if ROOT not in m.parents or not m.is_file():
                raise SystemExit("Music must be a file inside luxury_editor/.")
            inputs += ["-stream_loop","-1","-i",str(m)]
            filters.append(f"[{len(scenes)+1}:a]atrim=0:{total:.3f},afade=t=in:d=0.4,afade=t=out:st={max(0,total-2):.3f}:d=2,loudnorm=I=-16:TP=-1.5[aout]")
            audio = ["-map","[aout]","-c:a","aac","-b:a","192k"]
        else:
            audio = ["-an"]
        cmd = ["ffmpeg","-y","-hide_banner","-loglevel","error",*inputs,
               "-filter_complex",";".join(filters),"-map",f"[{prev}]",
               *audio,"-t",f"{total:.3f}","-c:v","libx264","-preset","veryfast",
               "-crf","19","-pix_fmt","yuv420p","-r",str(FPS),"-movflags","+faststart",str(output)]
        subprocess.run(cmd, check=True)
    probe = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(output)],capture_output=True,text=True,check=True)
    print(f"SUCCESS: {output} ({probe.stdout.strip()} seconds)")

if __name__ == "__main__":
    main()
