#!/usr/bin/env python3
"""Upload the voice-matched Reel directly as a public YouTube Short."""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def decode_secret(name: str) -> dict:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"GitHub Actions secret {name} is missing. Add the existing YouTube OAuth "
            "base64 JSON secret used by the repository's 3D Satisfying Video workflow."
        )
    try:
        decoded = base64.b64decode(value, validate=True)
        return json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"GitHub secret {name} is not valid base64-encoded JSON.") from exc


def get_youtube():
    client = decode_secret("YOUTUBE_CLIENT_SECRET_B64")
    token = decode_secret("YOUTUBE_TOKEN_B64")

    client_data = client.get("installed") or client.get("web") or client
    token.setdefault("client_id", client_data.get("client_id"))
    token.setdefault("client_secret", client_data.get("client_secret"))
    token.setdefault(
        "token_uri",
        client_data.get("token_uri") or "https://oauth2.googleapis.com/token",
    )

    if not token.get("refresh_token"):
        raise RuntimeError(
            "YouTube token JSON has no refresh_token. Re-authorize the channel with "
            "the youtube.upload scope and update YOUTUBE_TOKEN_B64."
        )

    credentials = Credentials.from_authorized_user_info(token, scopes=SCOPES)
    if not credentials.valid:
        if not credentials.expired or not credentials.refresh_token:
            raise RuntimeError("YouTube OAuth token is invalid and cannot be refreshed.")
        try:
            credentials.refresh(Request())
        except Exception as exc:
            raise RuntimeError(
                "YouTube OAuth refresh failed. Re-authorize the channel and update "
                "YOUTUBE_TOKEN_B64. Also verify the Google OAuth app is not in Testing mode."
            ) from exc

    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def upload(video_path: Path, script_path: Path) -> str:
    if not video_path.is_file() or video_path.stat().st_size < 100_000:
        raise RuntimeError(f"Rendered video is missing or unexpectedly small: {video_path}")
    if not script_path.is_file():
        raise FileNotFoundError(f"Script metadata file not found: {script_path}")

    document = json.loads(script_path.read_text(encoding="utf-8"))
    meta = document.get("meta", {})
    title = str(meta.get("title") or "Science Explainer").strip()
    if not title.lower().endswith("#shorts"):
        title = f"{title} #Shorts"
    title = title[:100]

    description = str(meta.get("description") or "").strip()
    description_parts = [description] if description else []
    description_parts.extend([
        "Hindi animated science explainer.",
        "#Shorts #Science #HindiFacts",
    ])
    description = "\n\n".join(description_parts)[:5000]

    raw_tags = meta.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [item.strip().lstrip("#") for item in raw_tags.replace(",", " ").split()]
    tags = [str(item).strip().lstrip("#")[:30] for item in raw_tags if str(item).strip()]
    if not tags:
        tags = ["science", "science facts", "Hindi facts", "education", "Rayleigh scattering"]

    youtube = get_youtube()
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags[:30],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,
        resumable=True,
    )
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"YouTube upload progress: {int(status.progress() * 100)}%", flush=True)
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and retries < 5:
                retries += 1
                delay = 2 ** retries
                print(f"Temporary YouTube API error; retry {retries}/5 in {delay}s", flush=True)
                time.sleep(delay)
                continue
            raise

    video_id = response["id"]
    url = f"https://youtube.com/shorts/{video_id}"
    print(f"PUBLIC_SHORT_URL={url}", flush=True)
    return url


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "Usage: upload_youtube.py VIDEO.mp4 SCRIPT.json RESULT.txt",
            file=sys.stderr,
        )
        return 2

    video_path, script_path, result_path = map(Path, sys.argv[1:])
    url = upload(video_path, script_path)
    result_path.write_text(
        json.dumps({"privacy": "public", "youtube_url": url}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved upload result: {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
