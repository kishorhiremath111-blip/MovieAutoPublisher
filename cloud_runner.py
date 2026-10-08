#!/usr/bin/env python3
"""Cloud entry point for scheduled MovieAutoPublisher jobs.

Designed for GitHub Actions/Cloud Run style runners. Credentials are injected
through environment variables or mounted files; secrets are never committed.
"""
import base64, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CREDS = ROOT / 'credentials'


def restore_secret(name, target):
    value = os.getenv(name, '').strip()
    if not value:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Secrets are expected as base64-encoded JSON.
        target.write_bytes(base64.b64decode(value))
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

    # Fresh original news cards/videos: exactly two per scheduled run.
    run('upload_queue', '--news')
    run('upload_queue', '--news-upload')

    # Generate the two daily image cards only when an authorized source video
    # exists. A missing optional movie/series source must not fail the whole
    # worldwide-news run.
    videos_dir = ROOT / 'input' / 'videos'
    has_video = videos_dir.exists() and any(videos_dir.glob('*'))
    if has_video:
        run('upload_queue', '--daily-images')
        if (CREDS / 'facebook_page.json').exists():
            run('upload_queue', '--facebook-images')
    else:
        print('No authorized source video; skipping optional daily image cards.')

    # Process any licensed content already supplied to the cloud workspace.
    # Metadata controls which items are eligible; no source is fetched from
    # third-party movie/anime sites.
    if (ROOT / 'metadata.json').exists():
        run('process')
        run('upload_queue', '--daily')


if __name__ == '__main__':
    main()
