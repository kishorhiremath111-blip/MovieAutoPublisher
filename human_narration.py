#!/usr/bin/env python3
"""Human-style, source-grounded narration for MovieAutoPublisher news videos."""
import asyncio
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

VOICE = os.getenv("TTS_VOICE", "en-IN-NeerjaNeural")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def fallback_script(story, short=False):
    category = str(story.get("category", "news")).replace("_", " ")
    title = re.sub(r"\s+", " ", str(story.get("title", "")).strip())
    source = str(story.get("source") or "the original report").strip()
    if short:
        return f"Quick update, {category} se. {title}. Full details ke liye original source {source} check karo—aur unconfirmed claims ko fact mat samjho."
    take = str(story.get("take") or "").replace("OUR TAKE:", "").replace("Our take:", "").strip()
    question = str(story.get("question") or "").strip()
    parts = [f"Chalo, {category} ki aaj ki important update samajhte hain.", f"{title}.",
             f"Report {source} se hai. Details badal sakti hain, isliye official update aur original source check karna zaroori hai."]
    if take:
        parts.append(take)
    if question:
        parts.append(question)
    return " ".join(parts)


def make_script(story, short=False):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY not set; using grounded human-style narration template.")
        return fallback_script(story, short)
    prompt = {
        "story": {"category": story.get("category"), "headline": story.get("title"),
                  "publisher": story.get("source"), "published": story.get("published"),
                  "description": story.get("description", "")[:700], "source_url": story.get("link"),
                  "editorial_take": story.get("take"), "audience_question": story.get("question")},
        "instructions": (
            ("Write 25-35 words" if short else "Write 55-75 words") +
            " of natural conversational Hinglish narration for an Indian audience. Sound like a real friendly presenter, not a robot. "
            "Use Roman-script Hindi mixed with common English. Explain only facts supported by supplied metadata; "
            "never invent facts, quotes, dates, numbers, motives or outcomes. If details are uncertain, say so. "
            "Never read the URL aloud. Return only spoken script, no labels or markdown."
        )
    }
    body = json.dumps({"contents": [{"parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
                       "generationConfig": {"temperature": 0.65, "maxOutputTokens": 180 if not short else 90}}).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
        data=body, headers={"Content-Type": "application/json", "User-Agent": "MovieAutoPublisher/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        spoken = " ".join(part.get("text", "") for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", [])).strip()
        if len(spoken) >= 30:
            return spoken
        print("Gemini returned no usable narration; using safe template.")
    except Exception as exc:
        print(f"Gemini narration unavailable ({type(exc).__name__}); using safe template.")
    return fallback_script(story, short)


def generate_voice(text, output):
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("edge-tts dependency missing; refusing to publish a silent video.") from exc
    async def save_audio():
        await edge_tts.Communicate(text, VOICE, rate="-4%", volume="+0%").save(str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(save_audio())
    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError("Voice narration file was not generated.")
    return output


def create_narration(story, output, short=False):
    script = make_script(story, short)
    output.with_suffix(".txt").write_text(script, encoding="utf-8")
    return generate_voice(script, output)


def mix_voice_music(video, voice, music, output):
    if not voice or not Path(voice).exists() or Path(voice).stat().st_size < 1000:
        raise RuntimeError("Narration audio missing; refusing silent news upload.")
    cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(voice)]
    if music and Path(music).exists():
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        filt = ("[1:a]highpass=f=90,acompressor=threshold=0.10:ratio=3:attack=15:release=180,loudnorm=I=-16:TP=-1.5:LRA=11[voice];"
                "[2:a]volume=0.12,lowpass=f=12000[music];"
                "[voice][music]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-14:TP=-1.0:LRA=11[a]")
    else:
        filt = "[1:a]highpass=f=90,acompressor=threshold=0.10:ratio=3:attack=15:release=180,loudnorm=I=-14:TP=-1.0:LRA=11[a]"
    cmd += ["-filter_complex", filt, "-map", "0:v:0", "-map", "[a]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-shortest", "-movflags", "+faststart", str(output)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode:
        raise RuntimeError("Narration/music mix failed: " + proc.stdout[-2500:])
    return output
