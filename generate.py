"""Motivator Shorts: script -> HD sketch images -> mard ki gehri awaaz -> pro edit (sound effects + music + ducking), BINA subtitle.
Subtitle tum khud lagaoge. Export folder me images, voice aur timings milte hain editing ke liye.
Gemini key ki zaroorat nahi."""
import os, sys, re, json, time, glob, shutil, random, asyncio, textwrap, subprocess, urllib.parse
import requests
import edge_tts
import audio_fx

W, H, FPS = 1080, 1920, 30
WORK, OUT = "work", "final.mp4"
DEFAULT_LANG = os.environ.get("VIDEO_LANGUAGE", "hi").lower()
CANDIDATES = int(os.environ.get("IMG_CANDIDATES", "2"))
CINEMATIC = os.environ.get("CINEMATIC", "1") == "1"
CATEGORY = os.environ.get("YT_CATEGORY", "22")
# Natural conversational delivery: normal speed, slightly deeper male tone.
RATE = os.environ.get("TTS_RATE", "+0%")
PITCH = os.environ.get("TTS_PITCH", "-8Hz")
VOICE_STYLE = os.environ.get("VOICE_STYLE", "natural")

VOICES = {
    "hi": ["en-IN-PrabhatNeural", "hi-IN-MadhurNeural"],
    "en": ["en-US-AndrewMultilingualNeural", "en-US-BrianMultilingualNeural",
           "en-US-GuyNeural", "en-US-ChristopherNeural"],
}
VISUAL_STYLE = os.environ.get("VISUAL_STYLE", "stickman").lower()

STICKMAN_STYLE = (
    "clean expressive 2D stickman cartoon illustration, ONE full-body stick figure clearly visible, "
    "round white head, simple black line body, thin black line arms and legs, clear hands and feet, "
    "large expressive cartoon eyes and eyebrows, simple expressive mouth, readable emotion, "
    "simple colorful cinematic background, smooth vector-like cartoon art, YouTube Shorts style, "
    "full body composition, strong storytelling pose, consistent main stickman character, "
    "no realistic human, no realistic face, no portrait, no charcoal, no graphite, no sketch, "
    "no photorealism, no text, no letters, no watermark, no logo"
)

GENERIC = [
    "stickman walking alone on an empty road at dawn, sad posture, wide shot",
    "stickman looking at his empty hands, worried expression, close medium shot",
    "stickman standing alone while a group of stickman friends walk away in the background, emotional scene",
    "stickman sitting quietly at a desk at night, then opening a notebook with determined expression",
    "stickman waking up early and working hard at a desk, determined focused expression",
    "confident stickman walking forward while people who ignored him now look surprised",
    "stickman honestly talking to another stickman friend, emotional conversational gesture",
    "stickman walking alone toward a bright sunrise on a long road, hopeful wide shot",
]

def build_visual_prompt(scene_prompt, character):
    if VISUAL_STYLE == "stickman":
        # User ke realistic CHARACTER field ko ignore karke guaranteed stickman prompt force karo.
        return f"{STICKMAN_STYLE}. Scene action: {scene_prompt}. The character must remain a stickman in this exact cartoon style."
    return f"{character}. Scene: {scene_prompt}"

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
        m = re.match(r"^(TITLE|DESCRIPTION|TAGS|CHARACTER|LANG|SCENE|IMG|SFX)\s*:\s*(.*)$", line, re.I)
        if m:
            k, v = m.group(1).upper(), m.group(2).strip()
            mode = k
            if k == "SCENE":
                cur = {"narration": v, "image_prompt": "", "sfx": ""}
                scenes.append(cur)
            elif k == "IMG":
                if cur is not None: cur["image_prompt"] = v
            elif k == "SFX":
                if cur is not None: cur["sfx"] = v
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
        scenes = [{"narration": re.sub(r"\s+", " ", p), "image_prompt": "", "sfx": ""} for p in paras]
    scenes = [s for s in scenes if s["narration"].strip()]
    if not scenes:
        raise RuntimeError("Script khali hai ya format galat hai")
    for i, s in enumerate(scenes):
        if not s["image_prompt"]: s["image_prompt"] = GENERIC[i % len(GENERIC)]
    meta["LANG"] = (meta["LANG"] or DEFAULT_LANG).lower()[:2]
    if not meta["TITLE"]: meta["TITLE"] = scenes[0]["narration"][:60]
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
    full = build_visual_prompt(prompt, character)[:1100]
    best = None
    for k in range(max(1, CANDIDATES)):
        data = fetch_image(full, seed + k * 7)
        if data and (best is None or len(data) > len(best)): best = data
        time.sleep(2)
    if best:
        open(path, "wb").write(best); return
    print("[image] FAIL -> fallback dark frame")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x1a1a1a:s={W}x{H}", "-frames:v", "1", path])

def naturalize_speech(text, lang):
    """Script ko audiobook/reading jaisa nahi, normal insaan ki baat jaisa banata hai."""
    text = re.sub(r"\\s+", " ", text).strip()
    # Ellipsis ko Edge TTS ke liye natural thought-pause me convert karo.
    text = re.sub(r"\\.{2,}", " ... ", text)
    # Comma ke baad breathing space aur long punctuation normalize.
    text = re.sub(r"([,;:!?])(?=\\S)", r"\\1 ", text)
    # Hindi narration me over-punctuation reading ko robotic bana sakti hai.
    if lang == "hi":
        text = text.replace("—", ", ")
    return text

async def _tts(text, voice, rate, pitch, path):
    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=rate,
        pitch=pitch,
        volume="+0%"
    )
    await communicate.save(path)

def make_voice(text, lang, path):
    voices = VOICES.get(lang, VOICES["hi"])
    text = naturalize_speech(text, lang)
    if os.environ.get("TTS_VOICE"):
        voices = [os.environ["TTS_VOICE"]] + [v for v in voices if v != os.environ["TTS_VOICE"]]
    for v in voices:
        for pitch in (PITCH, "+0Hz"):
            try:
                asyncio.run(_tts(text, v, RATE, pitch, path))
                if os.path.getsize(path) > 1000:
                    # Light mastering: clearer voice, controlled volume, smooth natural presence.
                    mastered = path + ".master.mp3"
                    run([
                        "ffmpeg", "-y", "-i", path,
                        "-af",
                        "highpass=f=70,"
                        "equalizer=f=180:t=h:w=120:g=1.5,"
                        "equalizer=f=3200:t=q:w=1.2:g=1.2,"
                        "acompressor=threshold=0.09:ratio=2.2:attack=15:release=140,"
                        "loudnorm=I=-16:TP=-1.5:LRA=9",
                        "-codec:a", "libmp3lame", "-b:a", "192k", mastered
                    ])
                    os.replace(mastered, path)
                    print(f"voice ok (natural smooth male): {v} | rate={RATE} pitch={pitch}"); return
            except Exception as e:
                print(f"[tts {v} pitch {pitch}] {str(e)[:150]}")
                time.sleep(2)
    raise RuntimeError("Koi bhi voice nahi bani")

def make_clip(i, n, img, aud, flash, pad, out):
    speech = duration(aud); dur = speech + pad
    frames = int(dur * FPS) + 1; hook = (i == 0)
    amount = 0.22 if hook else 0.14; step = amount / frames
    z = (f"min(zoom+{step:.7f},{1+amount})" if i % 2 == 0 else f"if(eq(on,0),{1+amount},max(zoom-{step:.7f},1.0))")
    vf = (f"scale={W*2}:{H*2}:flags=lanczos,"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}")
    if CINEMATIC: vf += ",noise=alls=4:allf=t,vignette=PI/6"
    if flash: vf += ",fade=t=in:st=0:d=0.12:color=white"
    elif hook: vf += ",fade=t=in:st=0:d=0.12"
    if i == n - 1: vf += f",fade=t=out:st={dur-0.8:.2f}:d=0.8"
    run(["ffmpeg", "-y", "-i", img, "-i", aud, "-vf", vf,
         "-af", f"apad=pad_dur={pad}", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k",
         "-ar", "44100", "-ac", "2", "-movflags", "+faststart", out])
    return dur

def build_video(meta, scenes):
    lang = meta["LANG"]; n = len(scenes)
    character = meta["CHARACTER"] or "a simple expressive stickman cartoon character"
    base_seed = random.randint(1, 90000); clips, timings, t = [], [], 0.0
    for i, s in enumerate(scenes):
        print(f"--- scene {i+1}/{n}")
        img, aud, clip = f"{WORK}/{i}.jpg", f"{WORK}/{i}.mp3", f"{WORK}/{i}.mp4"
        get_image(s["image_prompt"], character, img, seed=base_seed + i * 13)
        shutil.copy(img, f"{EXPORT}/images/{i+1:02}.jpg")
        make_voice(s["narration"], lang, aud)
        tags = (s.get("sfx") or "").lower()
        flash = ("impact" in tags) or (i == 0 and not tags) or (i == n - 1 and not tags and n > 2)
        pad = 0.8 if i == 0 else (1.0 if i == n - 1 else 0.45)
        d = make_clip(i, n, img, aud, flash, pad, clip)
        timings.append({"scene": i + 1, "start": round(t, 2), "end": round(t + d, 2), "text": s["narration"]})
        t += d; clips.append(clip)
    json.dump(timings, open(f"{EXPORT}/timings.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(f"{WORK}/list.txt", "w") as f:
        for c in clips: f.write(f"file '{os.path.basename(c)}'\n")
    joined = f"{WORK}/joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{WORK}/list.txt", "-c", "copy", joined])
    run(["ffmpeg", "-y", "-i", joined, "-vn", "-c:a", "libmp3lame", "-b:a", "192k", f"{EXPORT}/voice_full.mp3"])
    total = duration(joined)
    if os.environ.get("SFX_ON", "1") == "1":
        events = audio_fx.plan_events(scenes, timings, total)
        print(f"sound effects: {len(events)} events")
        audio_fx.mix_final(joined, events, total, OUT)
    else:
        os.replace(joined, OUT)
    print(f"Video ready: {OUT} ({duration(OUT):.1f}s)")

def upload(meta, scenes):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"], client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=creds)
    tags = [t.strip()[:30] for t in re.split(r"[,#]", meta["TAGS"]) if t.strip()][:12]
    desc = (meta["DESCRIPTION"] or scenes[0]["narration"]) + "\n\n#Shorts #Motivation #Mindset"
    body = {"snippet": {"title": meta["TITLE"][:85].strip() + " #Shorts", "description": desc, "tags": tags, "categoryId": CATEGORY},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(OUT, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status: print(f"upload {int(status.progress()*100)}%")
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
    json.dump({"meta": meta, "scenes": scenes}, open("meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
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
