#!/usr/bin/env python3
"""Generate one fact-anchored Hinglish explainer and persist no-repeat topic history."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FACTS_PATH = ROOT / "topics" / "fact_seeds.json"
TEMPLATES_PATH = ROOT / "topics" / "template_library.json"


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_history(path: Path):
    used_semantic = set()
    used_ids = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"History file is corrupt at line {line_no}: {exc}") from exc
                if row.get("semantic_key"):
                    used_semantic.add(row["semantic_key"])
                if row.get("topic_id"):
                    used_ids.add(row["topic_id"])
    return used_semantic, used_ids


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def transliterate_hi(text: str) -> str:
    """Convert Roman Hinglish to Devanagari for Chatterbox; preserve technical acronyms."""
    try:
        from indic_transliteration.sanscript import transliterate, ITRANS, DEVANAGARI
    except ImportError as exc:
        raise RuntimeError(
            "Hindi transliteration dependency missing. Install indic-transliteration."
        ) from exc

    protected = {
        "AI", "GPS", "QR", "USB", "USB-C", "Wi-Fi", "NFC", "HTTPS", "DNA",
        "NASA", "LED", "UV", "URL", "HTTP", "CPU", "RAM", "PDF", "MRI",
        "UNO", "GST", "RBI", "TV", "AC", "CO2", "PTFE", "TRPV1",
    }
    token_re = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")

    def convert(match):
        word = match.group(0)
        if word.upper() in protected or any(ch.isdigit() for ch in word):
            return word
        try:
            return transliterate(word.lower(), ITRANS, DEVANAGARI)
        except Exception:
            return word

    return token_re.sub(convert, text)


ANGLE_LINES = {
    "why": "Chalo, iska seedha reason pakadte hain.",
    "myth": "Pehle common guess ko reality se compare karte hain.",
    "daily": "Iska connection tumhari daily life se bhi hai.",
    "mechanism": "Ab andar ka mechanism simple steps mein dekhte hain.",
    "contrast": "Ek comparison se ye baat aur clear hogi.",
    "what-changes": "Ab dekhte hain kaunsi condition is effect ko badalti hai.",
    "observation": "Isko tum aas-paas safely notice bhi kar sakte ho.",
    "history": "Is mystery ko samajhne ka ek historical angle bhi hai.",
    "scale": "Ab iski scale ko simple example se samajhte hain.",
    "sequence": "Is process ko sahi sequence mein dekhna zaroori hai.",
    "cause-vs-trigger": "Underlying reason aur immediate trigger alag ho sakte hain.",
    "material": "Yahan material ki property important role play karti hai.",
    "environment": "Surroundings bhi result ko affect kar sakte hain.",
    "human-angle": "Isko ek familiar daily example se connect karte hain.",
    "animal-angle": "Ab ek simple comparison se picture clear karte hain.",
    "space-angle": "Ab is sawal ko doosre perspective se dekhte hain.",
    "sound-angle": "Ek aur simple observation se concept samajhte hain.",
    "light-angle": "Chalo, isi fact ko ek nayi nazar se dekhte hain.",
    "energy-angle": "Ab explanation ko step-by-step break karte hain.",
    "time-angle": "Is process mein timing bhi important hai.",
    "structure-angle": "Shape aur structure iska result badal dete hain.",
    "signal-angle": "Yahan cause aur response ka relation samajhna useful hai.",
    "system-angle": "Ek part ke bajay complete process ko dekhte hain.",
    "misconception-angle": "Hamari intuition yahan thodi incomplete ho sakti hai.",
    "bonus-angle": "Is fact se ek unexpected connection bhi nikalta hai.",
}


def safe_title(text: str, limit: int = 58) -> str:
    value = re.sub(r"\s+", " ", text).strip().rstrip("?!.")
    return value[:limit].rstrip()


def make_scene(say: str, bg: str, pose: str, chip_small: str, chip_big: str,
               elements: list[dict] | None = None, show_char: bool = True):
    clean = re.sub(r"\s+", " ", say).strip()
    return {
        "say": clean,
        "tts_hi": transliterate_hi(clean),
        "bg": bg,
        "char": {"show": show_char, "pose": pose, "x": 185},
        "chip": {
            "small": chip_small[:32],
            "big": chip_big[:28].upper(),
            "style": {"gold": "gold", "red": "red", "blue": "blue", "green": "green"}.get(bg, "normal"),
        },
        "elements": elements or [],
    }


def build_script(fact: dict, angle: dict, hook: dict, analogy_frame: dict,
                 humour_frame: dict, pipeline_dir: Path):
    q = fact["question"].strip()
    hook_text = hook["text"].format(q=q)
    angle_line = ANGLE_LINES.get(angle["id"], "Chalo, iska science samajhte hain.")
    analogy = analogy_frame["text"].format(analogy=fact["analogy"])
    joke = humour_frame["text"].format(joke=fact["joke"])

    title = safe_title(q)
    title_words = title.split()
    title_lines = [" ".join(title_words[:3]).upper(), " ".join(title_words[3:7]).upper()]
    title_lines = [line for line in title_lines if line] or ["AISA KYUN?"]

    scenes = [
        make_scene(
            hook_text, "gold", "think", "Aaj ka mystery", "EK SAWAAL",
            [{"type": "title", "x": 360, "y": 95, "word": 0,
              "params": {"lines": title_lines, "size": 64}}],
            show_char=True,
        ),
        make_scene(
            f"Common guess: {fact['misconception']} {angle_line}",
            "red", "shrug", "Reality check", "GUESS VS FACT",
            [{"type": "badge", "x": 85, "y": 300, "word": 0, "params": {"text": "MYTH?"}}],
        ),
        make_scene(
            f"Asli jawab: {fact['answer']}",
            "blue", "point", "Science ka jawab", "ASLI WAJAH",
            [{"type": "card", "x": 360, "y": 610, "word": 2,
              "params": {"title": "Asli jawab", "lines": [
                  {"text": safe_title(fact["answer"], 34), "icon": "check"},
              ]}}],
        ),
        make_scene(
            fact["why"], "dark", "present", "Andar kya hota hai?", "SCIENCE BREAKDOWN",
            [{"type": "card", "x": 360, "y": 600, "word": 1,
              "params": {"title": "Kaise hota hai?", "lines": [
                  {"text": safe_title(fact["why"], 36), "icon": "check"},
              ]}}],
        ),
        make_scene(
            analogy, "green", "wave", "Easy example", "YAAD RAKHNA",
            [{"type": "stat", "x": 360, "y": 600, "word": 1,
              "params": {"text": "AHA!", "sub": "Ab concept clear"}}],
        ),
        make_scene(
            f"Bonus fact: {fact['bonus']} {joke}",
            "gold", "think", "Bonus + halka mazaak", "PLOT TWIST",
            [{"type": "card", "x": 360, "y": 600, "word": 1,
              "params": {"title": "Bonus fact", "lines": [
                  {"text": safe_title(fact["bonus"], 36), "icon": "check"},
              ]}}],
        ),
        make_scene(
            "Aise hi everyday mysteries ke simple jawab chahiye? Video us dost ko bhejo jo har baat par why poochta hai.",
            "dark", "point", "Agla mystery kal", "DOST KO BHEJO",
            [{"type": "phone_cta", "x": 360, "y": 560, "word": 6,
              "params": {"handle": "VYROX DAILY", "sub": "Roz ek naya why", "letter": "V",
                         "friend": "Woh curious dost"}}],
        ),
    ]

    topic_key = fact["id"]
    combo = "|".join([fact["id"], angle["id"], hook["id"],
                      analogy_frame["id"], humour_frame["id"]])
    topic_id = sha(combo)[:24]
    semantic_key = sha(topic_key)

    metadata = {
        "title": title + " #Shorts",
        "description": (
            f"{fact['question']}\n\n"
            f"Simple Hindi/Hinglish explainer. Source: {fact['source_url']}\n"
            "#Shorts #Science #EverydayMystery #HindiFacts"
        ),
        "tags": [
            "science", "everyday mysteries", "Hindi facts", fact["category"].lower(),
            fact["subcategory"].lower(), "why questions",
        ],
        "watermark": "@VYROX DAILY",
        "voice": "hi-IN-MadhurNeural",
        "rate": "+6%",
        "voice_reference": "voice/voice_reference.wav",
        "tts_language": "hi",
        "tts_model": "v3",
        "tts_exaggeration": 0.35,
        "tts_cfg_weight": 0.5,
        "tts_temperature": 0.65,
        "topic_id": topic_id,
        "semantic_key": semantic_key,
        "fact_id": fact["id"],
        "category": fact["category"],
        "subcategory": fact["subcategory"],
        "editorial_angle": angle["name"],
        "template_ids": {
            "hook": hook["id"],
            "angle": angle["id"],
            "analogy": analogy_frame["id"],
            "humour": humour_frame["id"],
        },
        "source_ref": fact["source_url"],
        "fact_note": "Curated starter claim; verify source_ref before expanding or altering the factual claim.",
        "tts_note": "Chatterbox V3 uses the bundled voice_reference.wav; no voice fallback is permitted.",
    }
    return {"meta": metadata, "scenes": scenes}, {
        "topic_id": topic_id,
        "semantic_key": semantic_key,
        "fact_id": fact["id"],
        "question": fact["question"],
        "category": fact["category"],
        "subcategory": fact["subcategory"],
        "angle": angle["name"],
        "source_ref": fact["source_url"],
        "selected_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "template_ids": metadata["template_ids"],
    }


def generate(pipeline_dir: Path, state_dir: Path):
    facts_doc = read_json(FACTS_PATH)
    templates = read_json(TEMPLATES_PATH)
    facts = facts_doc["facts"]
    hooks = templates["hooks"]
    angles = templates["angles"]
    analogy_frames = templates["analogy_frames"]
    humour_frames = templates["humour_frames"]

    expected = len(facts) * len(hooks) * len(angles) * len(analogy_frames) * len(humour_frames)
    print(f"[topics] curated fact cards: {len(facts)}")
    print(f"[topics] candidate prompt compositions: {expected:,}")

    history = state_dir / "used_topics.jsonl"
    state_dir.mkdir(parents=True, exist_ok=True)
    used_semantic, used_ids = read_history(history)

    candidates = [(fact, rng.choice(angles)) for fact in facts
                  if sha(fact["id"]) not in used_semantic]
    if not candidates:
        raise RuntimeError(
            "All curated fact-angle topics are consumed. Add new sourced fact cards to "
            "topics/fact_seeds.json; the generator will not repeat used topics."
        )

    rng = random.SystemRandom()
    rng.shuffle(candidates)
    selected = None
    for fact, angle in candidates:
        hook = rng.choice(hooks)
        analogy_frame = rng.choice(analogy_frames)
        humour_frame = rng.choice(humour_frames)
        script, pending = build_script(
            fact, angle, hook, analogy_frame, humour_frame, pipeline_dir
        )
        if pending["topic_id"] not in used_ids:
            selected = script, pending
            break
    if selected is None:
        raise RuntimeError("No unused unique topic candidate remains.")

    script, pending = selected
    scripts_dir = pipeline_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    out_script = scripts_dir / "generated_topic.json"
    out_script.write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending_path = state_dir / "pending_topic.json"
    pending_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (pipeline_dir / "generated_topic_metadata.json").write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[topics] selected: {pending['question']}")
    print(f"[topics] category: {pending['category']} / {pending['subcategory']}")
    print(f"[topics] angle: {pending['angle']}")
    print(f"[topics] topic id: {pending['topic_id']}")
    print(f"[topics] source: {pending['source_ref']}")
    print(f"[topics] script: {out_script}")


def finalize(state_dir: Path, video_path: Path, mode: str):
    pending_path = state_dir / "pending_topic.json"
    if not pending_path.exists():
        raise RuntimeError("No pending topic found. Refusing to mark an unknown topic as used.")
    if not video_path.exists() or video_path.stat().st_size < 100_000:
        raise RuntimeError(f"Rendered MP4 missing or too small: {video_path}")

    pending = read_json(pending_path)
    history = state_dir / "used_topics.jsonl"
    state_dir.mkdir(parents=True, exist_ok=True)
    used_semantic, used_ids = read_history(history)
    if pending["semantic_key"] in used_semantic or pending["topic_id"] in used_ids:
        raise RuntimeError("Topic already exists in used history; duplicate consumption blocked.")

    record = dict(pending)
    record["completed_mode"] = mode
    record["video_bytes"] = video_path.stat().st_size
    record["completed_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with history.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    pending_path.unlink(missing_ok=True)
    print(f"[topics] marked used after successful {mode}: {pending['question']}")
    print(f"[topics] used topic id: {pending['topic_id']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="select one unused topic and create a pipeline-compatible JSON script")
    gen.add_argument("--pipeline-dir", type=Path, required=True)
    gen.add_argument("--state-dir", type=Path, default=ROOT / "state")
    fin = sub.add_parser("finalize", help="consume the pending topic after successful output")
    fin.add_argument("--state-dir", type=Path, default=ROOT / "state")
    fin.add_argument("--video", type=Path, required=True)
    fin.add_argument("--mode", choices=["public", "download"], required=True)
    args = parser.parse_args()

    if args.command == "generate":
        generate(args.pipeline_dir.resolve(), args.state_dir.resolve())
    elif args.command == "finalize":
        finalize(args.state_dir.resolve(), args.video.resolve(), args.mode)


if __name__ == "__main__":
    main()
