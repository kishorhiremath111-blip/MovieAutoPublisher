"""Motivator Shorts: tumhari script (ChatGPT se) -> HD sketch images -> mard ki gehri awaaz -> video (BINA subtitle).
Subtitle tum khud lagaoge. Export folder me images, voice aur timings milte hain editing ke liye.
Gemini key ki zaroorat nahi."""
import os, sys, re, json, time, glob, shutil, random, asyncio, textwrap, subprocess, urllib.parse
import requests
import edge_tts

W, H, FPS = 1080, 1920, 30
WORK, OUT = "work", "final.mp4"
DEFAULT_LANG = os.environ.get("VIDEO_LANGUAGE", "hi").lower()
CANDIDATES = int(os.environ.get("IMG_CANDIDATES", "2"))
CINEMATIC = os.environ.get("CINEMATIC", "1") == "1"
CATEGORY = os.environ.get("YT_CATEGORY", "22")
RATE = os.environ.get("TTS_RATE", "-6%")
PITCH = os.environ.get("TTS_PITCH", "-4Hz")

VOICES = {
    "hi": ["hi-IN-MadhurNeural"],
    "en": ["en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural",
           "en-US-GuyNeural", "en-US-ChristopherNeural"],
}
STYLE = ("masterpiece black and white charcoal and graphite pencil sketch on textured paper, "
         "hand-drawn, highly detailed linework, dramatic high-contrast chiaroscuro lighting, "
         "cinematic composition, strong depth, faceless silhouette character, moody atmosphere, "
         "8k, sharp focus, "
         "no text, no letters, no watermark, no logo, no deformed hands, no extra fingers, no blur")
GENERIC = [
    "lone hooded figure walking on an empty road at dawn, wide shot",
    "close up of clenched fist, dramatic shadows",
    "man standing on a mountain peak looking at the sunrise, low angle",
    "crowd of faceless silhouettes, one man standing alone, high angle",
    "broken chains falling apart, dramatic light",
    "man climbing a steep staircase into bright light",
    "storm clouds clearing above a lonely figure, wide shot",
    "silhouette man running through rain, motion lines",
]
EXPORT = "export"
os.makedirs(WORK, exist_ok=True)
os.makedirs(f"{EXPORT}/images", exist_ok=True)

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed:\n{p.stderr[-1500:]}")
    return p.stdout

def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", path]).strip())

def pick_script():
    f = os.environ.get("SCRIPT_FILE", "").strip()
    if f:
        return f
    files = sorted(glob.glob("scripts/*.txt"))
    return files[0] if files else None

def parse_script(path):
    text = open(path, encoding="utf-8-sig").read().replace("\r\n", "\n")
    meta = {"TITLE": "", "DESCRIPTION": "", "TAGS": "", "CHARACTER": "", "LANG": ""}
    scenes, cur, mode = [], None, None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(TITLE|DESCRIPTION|TAGS|CHARACTER|LANG|SCENE|IMG)\s*:\s*(.*)$", line, re.I)
        if m:
            k, v = m.group(1).upper(), m.group(2).strip()
            mode = k
            if k == "SCENE":
                cur = {"narration": v, "image_prompt": ""}
                scenes.append(cur)
            elif k == "IMG":
                if cur is not None:
                    cur["image_prompt"] = v
            else:
                meta[k] = v
        elif mode == "SCENE" and cur is not None:
            cur["narration"] += " " + line
        elif mode == "IMG" and cur is not None:
            cur["image_prompt"] += " " + line
        elif mode in meta:
            meta[mode] += " " + line
    if not scenes:
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        scenes = [{"narration": re.sub(r"\s+", " ", p), "image_prompt": ""} for p in paras]
    scenes = [s for s in scenes if s["narration"].strip()]
    if not scenes:
        raise RuntimeError("Script khali hai ya format galat hai")
    for i, s in enumerate(scenes):
        if not s["image_prompt"]:
            s["image_prompt"] = GENERIC[i % len(GENERIC)]
    meta["LANG"] = (meta["LANG"] or DEFAULT_LANG).lower()[:2]
    if not meta["TITLE"]:
        meta["TITLE"] = scenes[0]["narration"][:60]
    return meta, scenes

def fetch_image(full_prompt, seed):
    q = urllib.parse.quote(full_prompt)
    urls = [
        f"https://image.pollinations.ai/prompt/{q}?width={W}&height={H}&model=flux&seed={seed}&nologo=true&enhance=false",
        f"https://image.pollinations.ai/prompt/{q}?width={W}&height={H}&seed={seed+100}&nologo=true",
    ]
    for u in urls:
        for _ in range(3):
            try:
                r = requests.get(u, timeout=180)
                if r.ok and r.headers.get("content-type", "").startswith("image") and len(r.content) > 15000:
                    return r.content
            except Exception as e:
                print(f"[image] retry: {e}")
            time.sleep(5)
    return None

def get_image(prompt, character, path, seed):
    """Har scene ki CANDIDATES images banata hai, sabse zyada detail wali (badi file) chunta hai."""
    full = f"{STYLE}. {character}. Scene: {prompt}"[:900]
    best = None
    for k in range(max(1, CANDIDATES)):
        data = fetch_image(full, seed + k * 7)
        if data and (best is None or len(data) > len(best)):
            best = data
        time.sleep(2)
    if best:
        open(path, "wb").write(best)
        return
    print("[image] FAIL -> fallback dark frame")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x1a1a1a:s={W}x{H}", "-frames:v", "1", path])

async def _tts(text, voice, rate, pitch, path):
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)

def make_voice(text, lang, path):
    voices = VOICES.get(lang, VOICES["hi"])
    if os.environ.get("TTS_VOICE"):
        voices = [os.environ["TTS_VOICE"]] + voices
    for v in voices:
        for pitch in (PITCH, "+0Hz"):
            try:
                asyncio.run(_tts(text, v, RATE, pitch, path))
                if os.path.getsize(path) > 1000:
                    print(f"voice ok: {v}")
                    return
            except Exception as e:
                print(f"[tts {v} pitch {pitch}] {str(e)[:150]}")
                time.sleep(2)
    raise RuntimeError("Koi bhi voice nahi bani")

def make_clip(i, img, aud, out):
    speech = duration(aud)
    dur = speech + 0.5
    frames = int(dur * FPS) + 1
    hook = (i == 0)
    amount = 0.22 if hook else 0.14
    step = amount / frames
    z = (f"min(zoom+{step:.7f},{1+amount})" if i % 2 == 0
         else f"if(eq(on,0),{1+amount},max(zoom-{step:.7f},1.0))")
    vf = (f"scale={W*2}:{H*2}:flags=lanczos,"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}")
    if CINEMATIC:
        vf += ",noise=alls=7:allf=t,vignette=PI/6"
    vf += f",fade=t=in:st=0:d={0.12 if hook else 0.25},fade=t=out:st={dur-0.2:.2f}:d=0.2"
    run(["ffmpeg", "-y", "-i", img, "-i", aud, "-vf", vf,
         "-af", "apad=pad_dur=0.5", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "medium",
         "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k",
         "-ar", "44100", "-ac", "2", "-movflags", "+faststart", out])
    return dur

def build_video(meta, scenes):
    lang = meta["LANG"]
    character = meta["CHARACTER"] or "a faceless silhouette man in a hooded jacket"
    base_seed = random.randint(1, 90000)
    clips, timings, t = [], [], 0.0
    for i, s in enumerate(scenes):
        print(f"--- scene {i+1}/{len(scenes)}")
        img, aud, clip = f"{WORK}/{i}.jpg", f"{WORK}/{i}.mp3", f"{WORK}/{i}.mp4"
        get_image(s["image_prompt"], character, img, seed=base_seed + i * 13)
        shutil.copy(img, f"{EXPORT}/images/{i+1:02}.jpg")
        make_voice(s["narration"], lang, aud)
        d = make_clip(i, img, aud, clip)
        timings.append({"scene": i + 1, "start": round(t, 2), "end": round(t + d, 2),
                        "text": s["narration"]})
        t += d
        clips.append(clip)
    json.dump(timings, open(f"{EXPORT}/timings.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    with open(f"{WORK}/list.txt", "w") as f:
        for c in clips:
            f.write(f"file '{os.path.basename(c)}'\n")
    joined = f"{WORK}/joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{WORK}/list.txt", "-c", "copy", joined])
    run(["ffmpeg", "-y", "-i", joined, "-vn", "-c:a", "libmp3lame", "-b:a", "192k", f"{EXPORT}/voice_full.mp3"])
    music = glob.glob("music/*.mp3") + glob.glob("music/*.m4a") + glob.glob("music/*.wav")
    if music:
        track = random.choice(music)
        print("background music:", track)
        run(["ffmpeg", "-y", "-i", joined, "-stream_loop", "-1", "-i", track, "-filter_complex",
             "[1:a]volume=0.13[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", OUT])
    else:
        os.replace(joined, OUT)
    print(f"Video ready: {OUT} ({duration(OUT):.1f}s)")

def upload(meta, scenes):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=creds)
    tags = [t.strip()[:30] for t in re.split(r"[,#]", meta["TAGS"]) if t.strip()][:12]
    desc = (meta["DESCRIPTION"] or scenes[0]["narration"]) + "\n\n#Shorts #Motivation #Mindset"
    body = {"snippet": {"title": meta["TITLE"][:85].strip() + " #Shorts", "description": desc,
                    "tags": tags, "categoryId": CATEGORY},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(OUT, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"upload {int(status.progress()*100)}%")
    print("Uploaded: https://youtube.com/shorts/" + resp["id"])

if __name__ == "__main__":
    path = pick_script()
    if not path or not os.path.exists(path):
        print("scripts/ folder me koi .txt script nahi mili. Nayi script daalo (queue khali hai).")
        sys.exit(0)
    left = len(glob.glob("scripts/*.txt"))
    print(f"Script: {path}  (queue me total {left})")
    meta, scenes = parse_script(path)
    print(f"Title: {meta['TITLE']} | lang={meta['LANG']} | scenes={len(scenes)}")
    json.dump({"meta": meta, "scenes": scenes}, open("meta.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    build_video(meta, scenes)
    if os.environ.get("DRY_RUN") == "1":
        print("DRY RUN: upload skip. Artifacts se final.mp4 download karo.")
    else:
        upload(meta, scenes)
        if os.path.dirname(path) == "scripts":
            os.makedirs("scripts/done", exist_ok=True)
            shutil.move(path, os.path.join("scripts/done", os.path.basename(path)))
            print("Script done folder me chali gayi.")
        if left <= 3:
            print(f"WARNING: sirf {left-1} script bachi hai, nayi scripts daalo!")
