#!/usr/bin/env python3
"""Cloud entry point for scheduled MovieAutoPublisher jobs."""
import base64
import json
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


def has_movie_sources():
    path = ROOT / 'metadata.json'
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return bool(data.get('items'))
    except Exception:
        return False


def verify_daily_youtube_quota():
    state_path = ROOT / 'state' / 'state.json'
    if not state_path.exists():
        raise RuntimeError('Daily publish audit failed: state/state.json was not created.')
    state = json.loads(state_path.read_text(encoding='utf-8'))
    today = __import__('time').strftime('%Y-%m-%d')
    daily = state.get('daily', {}).get(today, {})
    long_count = len(daily.get('long', []))
    short_count = len(daily.get('short', []))
    print(f'Daily YouTube publish audit: long={long_count}/1, short={short_count}/1')
    if long_count < 1 or short_count < 1:
        raise RuntimeError(
            'Daily YouTube quota not met. Check current-day fresh news, OAuth credentials, '
            'and upload logs; refusing to report a green run with zero uploads.'
        )


def main():
    restore_secret('YOUTUBE_CLIENT_SECRET_B64', CREDS / 'client_secret.json')
    restore_secret('YOUTUBE_TOKEN_B64', CREDS / 'token.json')
    restore_secret('FACEBOOK_PAGE_B64', CREDS / 'facebook_page.json')
    restore_secret('INSTAGRAM_ACCESS_TOKEN_B64', CREDS / 'instagram_access_token.txt')

    # Fail early if the required YouTube OAuth pair is missing. A green run
    # without upload credentials would misleadingly look like publishing worked.
    missing_youtube = [
        name for name, path in (
            ('YOUTUBE_CLIENT_SECRET_B64', CREDS / 'client_secret.json'),
            ('YOUTUBE_TOKEN_B64', CREDS / 'token.json'),
        ) if not path.exists()
    ]
    if missing_youtube:
        raise RuntimeError('Missing required YouTube Actions secrets: ' + ', '.join(missing_youtube))

    if not os.getenv('YOUTUBE_API_KEY', '').strip():
        print('WARNING: YOUTUBE_API_KEY is missing; YouTube trend discovery/performance updates are disabled.')
    if not (CREDS / 'facebook_page.json').exists():
        print('WARNING: FACEBOOK_PAGE_B64 is missing; Facebook publishing will be skipped.')
    if not (CREDS / 'instagram_access_token.txt').exists() or not os.getenv('INSTAGRAM_USER_ID', '').strip():
        print('WARNING: Instagram trend credentials are incomplete; Instagram trend discovery will be skipped.')

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

    # 3) Generate original news and any available authorized social/movie content.
    run('upload_queue', '--social')
    run('upload_queue', '--news')
    run('upload_queue', '--daily-images')

    if has_movie_sources():
        run('process')
    else:
        print('No licensed movie/series/anime source configured; original news is the daily long/Short fallback.')

    # 4) Strict viral score gate for optional social clips; fresh news is checked separately.
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

    if has_movie_sources():
        run('upload_queue', '--daily')

    verify_daily_youtube_quota()


if __name__ == '__main__':
    main()
