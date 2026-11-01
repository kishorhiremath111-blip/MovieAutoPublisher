#!/usr/bin/env python3
"""Official YouTube Data API v3 uploader.

MovieAutoPublisher jaise hi GitHub secrets use karta hai:
  YOUTUBE_CLIENT_SECRET_B64  (client_secret.json ka base64)
  YOUTUBE_TOKEN_B64          (token.json ka base64, scope youtube.upload)
"""
import base64
import os
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
ROOT = Path(__file__).resolve().parent
CREDS = ROOT / "credentials"


def _write_secrets():
    CREDS.mkdir(exist_ok=True)
    for env, name in (("YOUTUBE_CLIENT_SECRET_B64", "client_secret.json"),
                      ("YOUTUBE_TOKEN_B64", "token.json")):
        val = os.getenv(env)
        if val:
            (CREDS / name).write_bytes(base64.b64decode(val))


def get_youtube():
    _write_secrets()
    token = CREDS / "token.json"
    if not token.exists():
        raise FileNotFoundError(
            "token.json nahi mila. GitHub secret YOUTUBE_TOKEN_B64 set karo.")
    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                raise RuntimeError(
                    "YouTube token refresh fail (%s). Dobara authorize karke "
                    "YOUTUBE_TOKEN_B64 update karo. Google OAuth app 'Testing' mode me ho "
                    "to token 7 din me expire hota hai, usse Production me publish karo." % exc
                ) from exc
        else:
            raise RuntimeError("Token invalid hai aur refresh nahi ho sakta.")
    return build("youtube", "v3", credentials=creds)


def upload_video(path, title, description, tags, privacy="public",
                 made_for_kids=True, category_id="24"):
    youtube = get_youtube()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": str(category_id),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": bool(made_for_kids),
        },
    }
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response, retries = None, 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and retries < 5:
                retries += 1
                time.sleep(2 ** retries)
                continue
            raise
    return response["id"]
