#!/usr/bin/env python3
"""Daily official-API queue controller."""
import argparse
from pathlib import Path
from uploaders.youtube import publish_daily, get_youtube
import json

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state' / 'state.json'
CREDS = ROOT / 'credentials'


def load(path, default):
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def check_config():
    print('YouTube client JSON:', 'present' if (CREDS / 'client_secret.json').exists() else 'missing')
    print('YouTube token:', 'present' if (CREDS / 'token.json').exists() else 'not authorized yet')
    print('Facebook Page:', 'ready later' if (CREDS / 'facebook_page.json').exists() else 'not configured')


def show_queue():
    state = load(STATE, {'queue': []})
    for x in state.get('queue', []):
        if x.get('status') == 'ready':
            print(f"{x.get('item_id')} | {x.get('title')} | {x.get('video')} | {x.get('short')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--queue', action='store_true')
    ap.add_argument('--authorize', action='store_true')
    ap.add_argument('--daily', action='store_true')
    ap.add_argument('--daily-images', action='store_true', help='Generate up to 3 separately sourced authorized image posts')
    ap.add_argument('--facebook-images', action='store_true', help='Publish up to 3 separately sourced image cards to a Facebook Page')
    ap.add_argument('--facebook-movie-reels', action='store_true', help='Publish a separate authorized movie/anime scene as a Facebook Reel')
    ap.add_argument('--social', action='store_true', help='Generate Shorts/Reels from explicitly authorized social source clips')
    args = ap.parse_args()

    if args.check:
        check_config()
        return
    if args.queue:
        show_queue()
        return
    if args.authorize:
        get_youtube()
        print('YouTube authorization complete.')
        return
    if args.daily:
        publish_daily()
        return
    if args.daily_images:
        from image_posts import generate_daily_images
        generate_daily_images()
        return
    if args.facebook_images:
        from uploaders.facebook import publish_daily_images
        publish_daily_images(3)
        return
    if args.social:
        from social_clips import main as generate_social_clips
        generate_social_clips()
        return
    if args.facebook_movie_reels:
        from uploaders.facebook import publish_movie_reels
        publish_movie_reels(1)
        return
    ap.print_help()


if __name__ == '__main__':
    main()
