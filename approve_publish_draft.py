#!/usr/bin/env python3
"""Human-approved upload of the exact VYROX draft artifact after QA and rights review."""
import base64
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def require_true(name):
    if os.getenv(name, "").strip().lower() != "true":
        raise RuntimeError(f"Upload blocked: explicit human confirmation {name}=true is required.")


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: approve_publish_draft.py <metadata.json> <video.mp4>")
    metadata_path, video_path = map(Path, sys.argv[1:])
    if not metadata_path.is_file() or not video_path.is_file():
        raise RuntimeError("Approved draft artifact is incomplete: metadata/video missing.")
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    require_true("HUMAN_UPLOAD_APPROVED")
    require_true("HUMAN_FACT_CHECK_CONFIRMED")
    require_true("HUMAN_RIGHTS_CONFIRMED")

    score = float(meta.get("viral_score", 0) or 0)
    threshold = float(meta.get("viral_score_threshold", 75) or 75)
    if score < threshold:
        raise RuntimeError(f"Upload blocked: viral score {score:.2f} is below threshold {threshold:.2f}.")
    if not meta.get("quality_report", {}).get("passed"):
        raise RuntimeError("Upload blocked: media quality report did not pass.")
    rights = meta.get("rights_report", {})
    if not rights.get("recognized_reuse_license"):
        raise RuntimeError("Upload blocked: no recognizable reusable image license was found.")
    if not str(meta.get("source", "")).startswith("https://"):
        raise RuntimeError("Upload blocked: source URL is missing or not HTTPS.")
    if not meta.get("voiceover", {}).get("verified_file"):
        raise RuntimeError("Upload blocked: voiceover generation was not verified.")
    if meta.get("approval_status") != "pending_human_review" or meta.get("upload_allowed") is not True:
        raise RuntimeError("Upload blocked: this draft did not pass pre-publish gates.")

    if os.getenv("GITHUB_ACTIONS") == "true":
        creds = ROOT / "credentials"
        creds.mkdir(exist_ok=True)
        for secret, target in (
            ("YOUTUBE_CLIENT_SECRET_B64", creds / "client_secret.json"),
            ("YOUTUBE_TOKEN_B64", creds / "token.json"),
        ):
            value = os.getenv(secret, "").strip()
            if not value:
                raise RuntimeError(f"Missing GitHub Actions secret: {secret}")
            target.write_bytes(base64.b64decode(value, validate=True))
            target.chmod(0o600)

    sys.path.insert(0, str(ROOT))
    from uploaders.youtube import upload_video, record_tracker
    privacy = os.getenv("VYROX_PRIVACY", "private").strip().lower()
    if privacy not in ("private", "unlisted", "public"):
        privacy = "private"
    title = str(meta.get("title", ""))[:100]
    description = str(meta.get("description", ""))[:5000]
    if not title or not description:
        raise RuntimeError("Upload blocked: title/description missing from reviewed metadata.")
    video_id = upload_video(
        str(video_path), title, description,
        tags=["VYROX DAILY", str(meta.get("category", "WORLD")), "Shorts", "News"],
        privacy=privacy
    )
    record_tracker(video_id, {
        "category": meta.get("category", "WORLD"),
        "edit_style": "news-voiceover",
        "viral_score": score,
        "title": title
    }, "vyrox-daily-news")
    print(f"APPROVED_DRAFT_UPLOADED ({privacy}): https://youtube.com/shorts/{video_id}")
    print("Performance tracking: video ID recorded in state/viral_tracker.json.")


if __name__ == "__main__":
    main()
