#!/usr/bin/env python3
"""One-time YouTube OAuth connection test for MovieAutoPublisher."""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent
CREDS = ROOT / "credentials"
CLIENT_SECRET = CREDS / "client_secret.json"
TOKEN = CREDS / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    if not CLIENT_SECRET.exists():
        raise SystemExit(
            f"Missing {CLIENT_SECRET}. Put your downloaded Google Desktop OAuth JSON there."
        )

    print("Starting Google OAuth...")
    print("A browser page should open. Sign in with the YouTube/Google account")
    print("that owns the channel, then allow the requested YouTube permission.")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET), SCOPES
    )
    creds = flow.run_local_server(open_browser=False,
        host="127.0.0.1",
        port=0,
        access_type="offline",
        prompt="consent",
    )

    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    print(f"OAuth token saved: {TOKEN}")

    youtube = build("youtube", "v3", credentials=creds)
    response = youtube.channels().list(part="snippet", mine=True).execute()
    items = response.get("items", [])

    if not items:
        raise SystemExit("OAuth worked, but no YouTube channel was returned for this account.")

    channel = items[0]["snippet"]["title"]
    print(f"YouTube connection OK: {channel}")
    print("OAuth test completed successfully.")


if __name__ == "__main__":
    main()
