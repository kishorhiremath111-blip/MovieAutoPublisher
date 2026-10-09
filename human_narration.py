#!/usr/bin/env python3
"""Human-style, source-grounded narration for MovieAutoPublisher news videos.

Gemini is optional: when GEMINI_API_KEY is configured it drafts a short, natural
Hinglish script grounded only in the supplied RSS metadata. Without it, a
conservative template is used. Edge TTS generates spoken audio; no silent track
is treated as a successful narration.
"""
import asyncio
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

VOICE = os.getenv("TTS_VOICE", "en-IN-NeerjaNeural")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def fallback_script(story):
    category = str(story.get("category", "news")).replace("_", " ")
    title = re.sub(r"\s+", " ", str(story.get("title", "")).strip())
    source = str(story.get("source") or "the original report").strip()
    take = str(story.get("take") or "").strip()
    question = str(story.get("question") or "").strip()
    parts = [
        f"Chalo, {category} ki aaj ki important update samajhte hain.",
        f"{title}.",
        f"Report {source} se hai. Details badal sakti hain, isliye official update aur original source check karna zaroori hai."
    ]
    if take:
        parts.append(take.replace("OUR TAKE:", "").replace("Our take:", "").strip())
    if question:
        parts.append(question)
    return " ".join(parts)


def make_script(story):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        print("GEMINI_API_KEY not set; using grounded human-style narration template.")
        return fallback_script(story)
    prompt = {
        "story": {
            "category": story.get("category"),
            "headline": story.get("title"),
            "publisher": story.get("source"),
            "published": story.get("published"),
            "description": story.get("description", "")[:700],
            "source_url": story.get("link"),
            "editorial_take": story.get("take"),
            "audience_question": story.get("question")
        },
        "instructions": (
            "Write 55-85 words of natural conversational Hinglish narration for an Indian audience. "
            "Sound like a real friendly presenter, not a robot or a formal newsreader. "
            "Use simple Roman-script Hindi mixed with common English. Start with a human hook; "
            "explain what is known and why it matters; finish naturally. Do not invent facts, "
            "quotes, dates, numbers, motives, or outcomes. If details are uncertain, say so. "
            "Never read the URL aloud. Return only the spoken script, no labels or markdown."
        )
    }
    body = json.dumps({
        "contents": [{"parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": 220}
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "MovieAutoPublisher/1.0"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = " ".join(
            part.get("text", "")
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        ).strip()
        if len(text) >= 30:
            return text
        print("Gemini returned no usable narration; using safe template.")
    except Exception as exc:
        print(f"Gemini narration unavailable ({type(exc).__name__}); using safe template.")
    return fallback_script(story)


def generate_voice(text, output):
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("edge-tts dependency missing; refusing to publish a silent video.") from exc

    async def save_audio():
        communicate = edge_tts.Communicate(text, VOICE, rate="-4%", volume="+0%")
        await communicate.save(str(output))

    output.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(save_audio())
    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError("Voice narration file was not generated.")
    return output


def create_narration(story, output):
    script = make_script(story)
    (output.with_suffix(".txt")).write_text(script, encoding="utf-8")
    return generate_voice(script, output)


def mix_voice_music(video, voice, music, output):
    """Mix voice clearly over optional licensed music; fail rather than make silence."""
    if not voice or not Path(voice).exists() or Path(voice).stat().st_size < 1000:
        raise RuntimeError("Narration audio missing; refusing silent news upload.")
    cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(voice)]
    if music and Path(music).exists():
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        filter_complex = (
            "[1:a]highpass=f=90,acompressor=threshold=0.10:ratio=3:attack=15:release=180,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[voice];"
            "[2:a]volume=0.12,lowpass=f=12000[music];"
            "[voice][music]amix=inputs=2:duration=first:dropout_transition=2,"
            "loudnorm=I=-14:TP=-1.0:LRA=11[a]"
        )
        audio_map = "[a]"
    else:
        filter_complex = (
            "[1:a]highpass=f=90,acompressor=threshold=0.10:ratio=3:attack=15:release=180,"
            "loudnorm=I=-14:TP=-1.0:LRA=11[a]"
        )
        audio_map = "[a]"
    cmd += [
        "-filter_complex", filter_complex, "-map", "0:v:0", "-map", audio_map,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        "-shortest", "-movflags", "+faststart", str(output)
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode:
        raise RuntimeError("Narration/music mix failed: " + proc.stdout[-2500:])
    return output
