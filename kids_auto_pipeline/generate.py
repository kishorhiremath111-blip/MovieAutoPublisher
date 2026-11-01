"""Roz ek kids Short: script (Gemini) -> images (Pollinations) -> voice (edge-tts) -> video (FFmpeg) -> YouTube."""
import os, sys, json, re, time, glob, random, asyncio, textwrap, datetime, subprocess, urllib.parse
import requests
import edge_tts

LANG = os.environ.get("VIDEO_LANGUAGE", "hi").lower()
VOICES = {"hi": "hi-IN-SwaraNeural", "en": "en-US-AnaNeural"}
VOICE = os.environ.get("TTS_VOICE") or VOICES.get(LANG, VOICES["hi"])
LANG_NAME = {"hi": "simple Hindi (Devanagari script)", "en": "simple English"}.get(LANG, "simple Hindi (Devanagari script)")
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-2.0-flash"] if m]
SUBTITLES = os.environ.get("SUBTITLES", "1") == "1"
W, H, FPS = 1080, 1920, 30
WORK, OUT = "work", "final.mp4"
STYLE = ("3D Pixar-style animated illustration, highly detailed, vibrant colors, soft cinematic lighting, "
         "cute friendly characters with big expressive eyes, depth of field, 4k, sharp focus, "
         "child-friendly, no text, no watermark")

os.makedirs(WORK, exist_ok=True)

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed:\n{p.stderr[-1500:]}")
    return p.stdout

def pick_topic():
    if os.environ.get("TOPIC"):
        return os.environ["TOPIC"]
    topics = json.load(open("topics.json", encoding="utf-8"))
    days = (datetime.date.today() - datetime.date(2024, 1, 1)).days
    return topics[days % len(topics)]

def get_script(topic):
    prompt = f"""You write short moral stories for kids aged 3-8 for a YouTube Shorts channel.
Topic: {topic}
Write in {LANG_NAME}. Exactly 7 scenes. Each narration is 1-2 short, sweet sentences (max 18 words).
The whole story should take about 50 seconds to read aloud. The last scene states a clear, gentle moral.
Return ONLY valid JSON in this shape:
{{"title": "catchy title in {LANG_NAME}, max 60 chars",
 "description": "2-3 lines in {LANG_NAME}",
 "tags": ["8 short tags"],
 "characters": "English: detailed visual description of the main characters (species, colors, clothes), reused in every image",
 "scenes": [{{"narration": "...", "image_prompt": "English: what happens, camera angle, setting, mood"}}]}}"""
    last = None
    for model in MODELS:
        for attempt in range(3):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                r = requests.post(url, params={"key": os.environ["GEMINI_API_KEY"]}, timeout=120,
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}})
                r.raise_for_status()
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                text = re.sub(r"^\`\`\`(?:json)?|\`\`\`$", "", text.strip(), flags=re.M).strip()
                data = json.loads(text)
                assert len(data["scenes"]) >= 4
                return data
            except Exception as e:
                last = e
                print(f"[gemini:{model}] attempt {attempt+1} failed: {e}")
                time.sleep(4)
    raise RuntimeError(f"Gemini script nahi bani: {last}")

def get_image(scene_prompt, characters, path, seed):
    full = f"{STYLE}. Characters: {characters}. Scene: {scene_prompt}"[:900]
    q = urllib.parse.quote(full)
    urls = [
        f"https://image.pollinations.ai/prompt/{q}?width={W}&height={H}&model=flux&seed={seed}&nologo=true&enhance=false",
        f"https://image.pollinations.ai/prompt/{q}?width={W}&height={H}&seed={seed+100}&nologo=true",
    ]
    for u in urls:
        for attempt in range(3):
            try:
                r = requests.get(u, timeout=180)
                if r.ok and r.headers.get("content-type", "").startswith("image") and len(r.content) > 10000:
                    open(path, "wb").write(r.content)
                    return True
            except Exception as e:
                print(f"[image] retry: {e}")
            time.sleep(5)
    print("[image] FAIL -> fallback colour frame")
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x4aa8ff:s={W}x{H}", "-frames:v", "1", path])
    return False

async def _tts(text, path):
    await edge_tts.Communicate(text, VOICE, rate="-8%").save(path)

def make_voice(text, path):
    for attempt in range(3):
        try:
            asyncio.run(_tts(text, path))
            if os.path.getsize(path) > 1000:
                return
        except Exception as e:
            print(f"[tts] retry: {e}")
            time.sleep(3)
    raise RuntimeError("Voice nahi bani")

def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", path]).strip())

def write_srt(text, dur, path):
    def t(x):
        return f"{int(x//3600):02}:{int(x%3600//60):02}:{int(x%60):02},{int(x%1*1000):03}"
    wrapped = "\n".join(textwrap.wrap(text, width=22))
    open(path, "w", encoding="utf-8").write(f"1\n{t(0.1)} --> {t(dur-0.1)}\n{wrapped}\n")

def make_clip(i, img, aud, text, out):
    dur = duration(aud) + 0.6
    frames = int(dur * FPS) + 1
    step = 0.15 / frames
    if i % 2 == 0:
        z = f"min(zoom+{step:.7f},1.15)"
    else:
        z = f"if(eq(on,0),1.15,max(zoom-{step:.7f},1.0))"
    vf = (f"scale={W*2}:{H*2}:flags=lanczos,"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
          f"fade=t=in:st=0:d=0.25,fade=t=out:st={dur-0.25:.2f}:d=0.25")
    base = ["ffmpeg", "-y", "-i", img, "-i", aud]
    enc = ["-af", "apad=pad_dur=0.6", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "medium",
           "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k",
           "-ar", "44100", "-ac", "2", "-movflags", "+faststart", out]
    if SUBTITLES:
        srt = f"{WORK}/{i}.srt"
        write_srt(text, dur, srt)
        style = ("FontName=Noto Sans Devanagari,FontSize=16,Bold=1,PrimaryColour=&H00FFFFFF,"
                 "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=110")
        try:
            run(base + ["-vf", f"{vf},subtitles={srt}:force_style='{style}'"] + enc)
            return
        except Exception as e:
            print(f"[clip {i}] subtitles fail, bina subtitle: {str(e)[:300]}")
    run(base + ["-vf", vf] + enc)

def build_video(data):
    chars = data.get("characters", "cute friendly cartoon animals")
    clips = []
    for i, s in enumerate(data["scenes"]):
        img, aud, clip = f"{WORK}/{i}.jpg", f"{WORK}/{i}.mp3", f"{WORK}/{i}.mp4"
        print(f"--- scene {i+1}/{len(data['scenes'])}")
        get_image(s["image_prompt"], chars, img, seed=random.randint(1, 99999))
        make_voice(s["narration"], aud)
        make_clip(i, img, aud, s["narration"], clip)
        clips.append(clip)
    with open(f"{WORK}/list.txt", "w") as f:
        for c in clips:
            f.write(f"file '{os.path.basename(c)}'\n")
    joined = f"{WORK}/joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{WORK}/list.txt", "-c", "copy", joined])

    music = glob.glob("music/*.mp3") + glob.glob("music/*.m4a") + glob.glob("music/*.wav")
    if music:
        track = random.choice(music)
        print("background music:", track)
        run(["ffmpeg", "-y", "-i", joined, "-stream_loop", "-1", "-i", track, "-filter_complex",
             "[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-shortest", OUT])
    else:
        os.replace(joined, OUT)
    print(f"Video ready: {OUT} ({duration(OUT):.1f}s)")

def upload(data):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=creds)
    tags = [str(t)[:30] for t in data.get("tags", [])][:10]
    body = {
        "snippet": {
            "title": data["title"][:85].strip() + " #Shorts",
            "description": data.get("description", "") + "\n\n#Shorts #KidsStories #MoralStories",
            "tags": tags, "categoryId": "27",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": True},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(OUT, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"upload {int(status.progress()*100)}%")
    print("Uploaded: https://youtube.com/shorts/" + resp["id"])

if __name__ == "__main__":
    topic = pick_topic()
    print("Topic:", topic)
    data = get_script(topic)
    json.dump(data, open("meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    build_video(data)
    if os.environ.get("DRY_RUN") == "1":
        print("DRY RUN: upload skip. Artifacts me final.mp4 download karo.")
    else:
        upload(data)
