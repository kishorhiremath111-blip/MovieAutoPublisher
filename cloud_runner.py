#!/usr/bin/env python3
"""Cloud entry point for scheduled MovieAutoPublisher jobs."""
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

    # 1) Collect fresh trend signals and learn from previous uploads.
    if os.getenv('YOUTUBE_API_KEY', '').strip():
        run('trend_engine')

    if (CREDS / 'instagram_access_token.txt').exists() and os.getenv('INSTAGRAM_USER_ID', '').strip():
        os.environ['INSTAGRAM_ACCESS_TOKEN'] = (
            CREDS / 'instagram_access_token.txt'
        ).read_text(encoding='utf-8').strip()
        run('instagram_trends')

    if os.getenv('VIRAL_TRACKER_DISABLED', '').strip().lower() != 'true':
        run('viral_tracker', '--update')
        run('viral_tracker', '--plan')

    # 2) Prepare authorized TaskEarn brand assets.
    if (ROOT / 'input' / 'taskearn.apk').exists() or (ROOT / 'input' / 'brand_assets').exists():
        run('brand_assets')

    # 3) Generate content first. Nothing is published until the viral gate passes.
    run('upload_queue', '--social')
    run('upload_queue', '--news')
    run('upload_queue', '--daily-images')

    if (ROOT / 'metadata.json').exists():
        run('process')

    # 4) Strict pre-publish gate: fresh, non-repeated and trend-aligned content only.
    if os.getenv('VIRAL_TRACKER_DISABLED', '').strip().lower() != 'true':
        run('viral_tracker', '--gate')

    # 5) Publish the daily quotas.
    run('upload_queue', '--social-upload')
    if (CREDS / 'facebook_page.json').exists():
        # Prefer an authorized social Reel; if none exists, the news Short
        # becomes the single daily Reel fallback.
        run('upload_queue', '--facebook-social-reels')

    run('upload_queue', '--news-upload')
    if (CREDS / 'facebook_page.json').exists():
        run('upload_queue', '--facebook-news-video')
        run('upload_queue', '--facebook-reels')

    if (CREDS / 'facebook_page.json').exists():
        run('upload_queue', '--facebook-images')

    if (ROOT / 'metadata.json').exists():
        run('upload_queue', '--daily')


if __name__ == '__main__':
    main()
