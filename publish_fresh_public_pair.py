#!/usr/bin/env python3
"""Publish two distinct, attribution-compliant Blender Foundation open movies:
a new vertical Short excerpt from Sintel and the full Big Buck Bunny film."""
import base64, json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "fresh_public_pair"
OUT.mkdir(parents=True, exist_ok=True)
SINTEL = OUT / "sintel_full_source.mp4"
BBB = OUT / "big_buck_bunny_full_source.mp4"
SHORT = OUT / "sintel_fresh_short.mp4"
SHORT_THUMB = OUT / "sintel_short_thumbnail.jpg"
LONG_THUMB = OUT / "big_buck_bunny_thumbnail.jpg"
REPORT = OUT / "publish_report.json"
CREDS = ROOT / "credentials"
SOURCES = {
    "sintel": "https://download.blender.org/durian/movies/sintel-2048-surround.mp4",
    "bbb": "https://download.blender.org/peach/bigbuckbunny_movies/BigBuckBunny_320x180.mp4",
}
LICENSE = "https://creativecommons.org/licenses/by/3.0/"

def run(cmd):
    print("+", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        print(p.stdout[-10000:], file=sys.stderr)
        raise RuntimeError(f"Command failed ({p.returncode}): {cmd[0]}")
    return p.stdout.strip()

def download(url, path, min_bytes=5_000_000):
    if path.exists() and path.stat().st_size >= min_bytes:
        return
    tmp = path.with_suffix(path.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent":"MovieAutoPublisher/1.0"})
    print("Downloading licensed source:", url, flush=True)
    with urllib.request.urlopen(req, timeout=90) as src, tmp.open("wb") as dst:
        ct = (src.headers.get("Content-Type") or "").lower()
        if "text/html" in ct:
            raise RuntimeError("Source returned HTML instead of media: " + url)
        while True:
            b = src.read(1024 * 1024)
            if not b: break
            dst.write(b)
    if tmp.stat().st_size < min_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Source file too small to be a full film: " + url)
    tmp.replace(path)
    dur = float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)]))
    expected = 800 if "sintel" in path.name else 500
    if dur < expected:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"Refusing sample/trailer instead of full film: duration={dur:.1f}s expected >= {expected}s")
    print(f"FULL FILM SOURCE QA PASS: {path.name} {dur:.1f}s {path.stat().st_size} bytes")

def restore_secret(name, target):
    value = os.getenv(name, "").strip()
    if not value: return
    raw = base64.b64decode(value, validate=True)
    json.loads(raw.decode("utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    target.chmod(0o600)

def main():
    download(SOURCES["sintel"], SINTEL)
    download(SOURCES["bbb"], BBB)
    # A new 28-second excerpt from Sintel; the source itself is a separate full film.
    run(["ffmpeg","-hide_banner","-y","-ss","95","-i",str(SINTEL),"-t","28",
         "-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=contrast=1.05:saturation=1.12,format=yuv420p",
         "-c:v","libx264","-preset","fast","-crf","20","-r","30","-c:a","aac","-b:a","160k",
         "-movflags","+faststart",str(SHORT)])
    run(["ffmpeg","-hide_banner","-y","-ss","104","-i",str(SHORT),"-frames:v","1","-q:v","2",str(SHORT_THUMB)])
    run(["ffmpeg","-hide_banner","-y","-ss","300","-i",str(BBB),"-frames:v","1","-q:v","2",str(LONG_THUMB)])
    dur=float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(SHORT)]))
    if not 8 <= dur <= 60: raise RuntimeError(f"Short QA failed: {dur:.1f}s")
    restore_secret("YOUTUBE_CLIENT_SECRET_B64", CREDS/"client_secret.json")
    restore_secret("YOUTUBE_TOKEN_B64", CREDS/"token.json")
    if not (CREDS/"client_secret.json").exists() or not (CREDS/"token.json").exists():
        raise RuntimeError("Missing YouTube OAuth secrets YOUTUBE_CLIENT_SECRET_B64 / YOUTUBE_TOKEN_B64")
    sys.path.insert(0,str(ROOT))
    from uploaders.youtube import upload_video
    # Upload the new short from Sintel, not the earlier Big Buck Bunny 30-second sample.
    short_id=upload_video(
        SHORT, "Sintel 🐉 | A Dragon's Journey #Shorts",
        "A short vertical excerpt from Sintel (Blender Foundation's Durian open movie).\n"
        "Original film and project: https://durian.blender.org/\n"
        "License: Creative Commons Attribution 3.0: "+LICENSE+"\n"
        "Credit: © copyright Blender Foundation | durian.blender.org",
        ["Sintel","Blender Open Movie","Creative Commons","Animation","Shorts"],
        privacy="public", thumbnail=SHORT_THUMB)
    print("NEW PUBLIC SHORT SUCCESS: https://youtube.com/shorts/"+short_id, flush=True)
    # Upload the complete Big Buck Bunny source unchanged so its original ending credits remain intact.
    long_id=upload_video(
        BBB, "Big Buck Bunny 🐰 | Full Animated Open Movie",
        "Big Buck Bunny (2008), the complete open animated film from the Blender Foundation.\n"
        "Original project/source: https://peach.blender.org/\n"
        "License: Creative Commons Attribution 3.0: "+LICENSE+"\n"
        "Credit: (c) copyright 2008, Blender Foundation / www.bigbuckbunny.org\n"
        "The complete film and original ending credits are preserved. No affiliation or endorsement is implied.",
        ["Big Buck Bunny","Blender Foundation","Open Movie","Creative Commons","Animation"],
        privacy="public", thumbnail=LONG_THUMB)
    print("NEW PUBLIC FULL VIDEO SUCCESS: https://youtube.com/watch?v="+long_id, flush=True)
    report={
        "status":"success","short":{"video_id":short_id,"url":"https://youtube.com/shorts/"+short_id,"source":SOURCES["sintel"],"privacy":"public","thumbnail":str(SHORT_THUMB.relative_to(ROOT))},
        "long":{"video_id":long_id,"url":"https://youtube.com/watch?v="+long_id,"source":SOURCES["bbb"],"privacy":"public","thumbnail":str(LONG_THUMB.relative_to(ROOT))},
        "license":LICENSE,"created_at":int(time.time()),"note":"Two distinct full licensed Blender Foundation sources; long film is not the 30-second sample."
    }
    REPORT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        REPORT.write_text(json.dumps({"status":"failed","error":str(exc)},indent=2)+"\n",encoding="utf-8")
        raise
