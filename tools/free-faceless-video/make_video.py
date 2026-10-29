#!/usr/bin/env python3
"""Separate free faceless-video pipeline adapted from the supplied PDF.

Requires Ollama locally, edge-tts, FFmpeg and optionally PEXELS_API_KEY.
"""
import os, sys, json, math, random, asyncio, subprocess, re, shutil, time
from pathlib import Path
import requests
import edge_tts

MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
LANGUAGE = os.environ.get("VIDEO_LANGUAGE", "Hindi (Devanagari script)")
VOICE = os.environ.get("VIDEO_VOICE", "hi-IN-MadhurNeural")
NUM_SECTIONS = int(os.environ.get("NUM_SECTIONS", "10"))
WORDS_PER_SECTION = int(os.environ.get("WORDS_PER_SECTION", "230"))
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
CLIP_LEN = int(os.environ.get("CLIP_LEN", "10"))

def run(cmd):
    subprocess.run(cmd, check=True)

def llm(prompt, json_mode=False):
    body = {"model": MODEL, "prompt": prompt, "stream": False}
    if json_mode:
        body["format"] = "json"
    r = requests.post(OLLAMA_URL, json=body, timeout=1800)
    r.raise_for_status()
    return r.json()["response"].strip()

def make_outline(topic):
    prompt = (
        f'Create a YouTube video outline about: "{topic}". Return ONLY JSON: '
        '{"title":"catchy title","description":"short description",'
        '"sections":[{"heading":"...","keyword":"2-3 English words for stock footage"}]} '
        f'with exactly {NUM_SECTIONS} sections. Title and headings in {LANGUAGE}; '
        'stock footage keywords must be English.'
    )
    data = json.loads(llm(prompt, json_mode=True))
    if not isinstance(data.get("sections"), list) or not data["sections"]:
        raise ValueError("Ollama returned an invalid outline")
    return data

def make_narration(topic, heading, i, total):
    prompt = (
        f'You are writing voiceover for a YouTube video about "{topic}". '
        f'Section {i+1} of {total}: "{heading}". Write about {WORDS_PER_SECTION} words '
        f'in {LANGUAGE}. Engaging storytelling, start with a strong hook, no markdown, '
        'no headings, no emojis, no stage directions. Return only spoken text.'
    )
    return re.sub(r"[*#_`]", "", llm(prompt))

async def tts(text, path):
    await edge_tts.Communicate(text, VOICE).save(path)

def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True, check=True
    )
    return float(out.stdout.strip())

def pexels_clips(keyword, n, used):
    if not PEXELS_KEY:
        return []
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": PEXELS_KEY},
        params={"query": keyword, "per_page": 15, "orientation": "landscape",
                "page": random.randint(1, 2)}, timeout=60
    )
    r.raise_for_status()
    urls = []
    for video in r.json().get("videos", []):
        if video["id"] in used:
            continue
        files = [f for f in video.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("width", 0) >= 1280]
        if files:
            urls.append((video["id"], min(files, key=lambda f: f["width"])["link"]))
        if len(urls) >= n:
            break
    return urls

def normalize(src, dst):
    run(["ffmpeg", "-y", "-i", src, "-t", str(CLIP_LEN), "-an",
         "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,setsar=1",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", dst])

def fallback_clip(dst):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"color=c=0x101828:s=1920x1080:d={CLIP_LEN}:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", dst])

def build_section(i, keyword, audio, work, used):
    dur = duration(audio)
    need = math.ceil(dur / CLIP_LEN)
    clips = []
    for j, (vid, url) in enumerate(pexels_clips(keyword, need, used)):
        raw = work / f"raw_{i}_{j}.mp4"
        with requests.get(url, timeout=300, stream=True) as response:
            response.raise_for_status()
            with raw.open("wb") as out:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        out.write(chunk)
        out = work / f"clip_{i}_{j}.mp4"
        normalize(str(raw), str(out))
        clips.append(out)
        used.add(vid)
    if not clips:
        fb = work / f"clip_{i}_fallback.mp4"
        fallback_clip(str(fb))
        clips = [fb]
    lst = work / f"list_{i}.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    seg = work / f"seg_{i}.mp4"
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-i", str(audio), "-map", "0:v", "-map", "1:a",
         "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-b:a", "128k", str(seg)])
    return seg

def main():
    if len(sys.argv) < 2:
        sys.exit('Usage: python make_video.py "your topic"')
    topic = " ".join(sys.argv[1:]).strip()
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", topic).strip("_")[:40] or "video"
    work = Path(f"work_{slug}")
    work.mkdir(parents=True, exist_ok=True)
    print("1/4 Outline bana raha hoon...", flush=True)
    outline = make_outline(topic)
    sections = outline["sections"][:NUM_SECTIONS]
    if len(sections) < NUM_SECTIONS:
        print(f"Note: model returned {len(sections)} sections.", flush=True)
    print("2/4 Script + voiceover...", flush=True)
    full_script, audios = [], []
    for i, section in enumerate(sections):
        print(f"  section {i+1}/{len(sections)}", flush=True)
        text = make_narration(topic, section["heading"], i, len(sections))
        full_script.append(f'## {section["heading"]}\n{text}\n')
        audio = work / f"audio_{i}.mp3"
        asyncio.run(tts(text, str(audio)))
        audios.append(audio)
    print("3/4 Visuals + editing...", flush=True)
    used, segments = set(), []
    for i, section in enumerate(sections):
        segments.append(build_section(i, section.get("keyword", topic), audios[i], work, used))
    print("4/4 Final video jod raha hoon...", flush=True)
    concat_list = work / "final_list.txt"
    concat_list.write_text("".join(f"file '{s.resolve()}'\n" for s in segments), encoding="utf-8")
    output = Path(f"{slug}.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(output)])
    (Path(f"{slug}_info.txt")).write_text(
        f'TITLE: {outline.get("title", topic)}\n\nDESCRIPTION: {outline.get("description", "")}\n\n'
        + "\n".join(full_script), encoding="utf-8")
    print(f"Done! Video: {output} | Title/script: {slug}_info.txt", flush=True)

if __name__ == "__main__":
    main()
