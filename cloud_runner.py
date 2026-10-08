#!/usr/bin/env python3
"""Cloud entry point for scheduled MovieAutoPublisher jobs.

Designed for GitHub Actions/Cloud Run style runners. Credentials are injected
through environment variables or mounted files; secrets are never committed.
"""
import base64
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CREDS = ROOT / 'credentials'


def restore_secret(name, target):
    value = os.getenv(name, '').strip()
    if not value:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(base64.b64decode(value, validate=True))
    except Exception as exc:
        raise RuntimeError(f'{name} is not valid base64: {exc}')
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return True


def run(*args):
    cmd = [sys.executable, '-m', *args]
    print('RUN:', ' '.join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main():
    restore_secret('YOUTUBE_CLIENT_SECRET_B64', CREDS / 'client_secret.json')
    restore_secret('YOUTUBE_TOKEN_B64', CREDS / 'token.json')
    restore_secret('FACEBOOK_PAGE_B64', CREDS / 'facebook_page.json')
    restore_secret('INSTAGRAM_ACCESS_TOKEN_B64', CREDS / 'instagram_access_token.txt')

    # Official YouTube trend metadata for India: current popular videos + music.
    # Metadata only; third-party video/audio is never downloaded.
    if os.getenv('YOUTUBE_API_KEY', '').strip():
        run('trend_engine')

    # Optional Instagram trend signal via the official Meta API.
    # Only metadata is stored; third-party Instagram media is not reposted.
    if (CREDS / 'instagram_access_token.txt').exists() and os.getenv('INSTAGRAM_USER_ID', '').strip():
        os.environ['INSTAGRAM_ACCESS_TOKEN'] = (CREDS / 'instagram_access_token.txt').read_text(encoding='utf-8').strip()
        run('instagram_trends')

    # Prepare authorized TaskEarn brand assets from input/taskearn.apk or supplied images.
    if (ROOT / 'input' / 'taskearn.apk').exists() or (ROOT / 'input' / 'brand_assets').exists():
        run('brand_assets')

    # SHORTS/REELS: process only explicitly authorized/licensed source clips.\n    # Trend metadata is used as a signal; third-party social videos are never downloaded.\n    run('upload_queue', '--social')\n    run('upload_queue', '--social-upload')\n    if (CREDS / 'facebook_page.json').exists():\n        run('upload_queue', '--facebook-social-reels')\n\n    # DAILY NEWS: one worldwide roundup, not nine separate news posts.
    # Each story can show 1-6 real, rights-cleared images as slides with
    # a story-specific take/question. Freshness + duplicate checks happen in news_engine.
    run('upload_queue', '--news')
    run('upload_queue', '--news-upload')
    if (CREDS / 'facebook_page.json').exists():
        run('upload_queue', '--facebook-news-video')

    # Facebook Reels are intentionally NOT required every day. They remain
    # available through the manual --facebook-reels command when needed.
    
    # Separate daily image posts are intentionally not automatic.
    # News images are already assembled as 1-6 slides inside the single roundup.
    # The manual --daily-images command remains available when specifically needed.


    # Process any licensed content already supplied to the cloud workspace.
    # Metadata controls which items are eligible; no source is fetched from
    # third-party movie/anime streaming sites.
    if (ROOT / 'metadata.json').exists():
        run('process')
        run('upload_queue', '--daily')


if __name__ == '__main__':
    main()
