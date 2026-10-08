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
    if not path.exists(): return default
    with path.open('r', encoding='utf-8') as f: return json.load(f)

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
    ap.add_argument('--daily-images', action='store_true', help='Generate exactly 2 image posts')
    ap.add_argument('--facebook-images', action='store_true', help='Publish up to 2 ready images to a Facebook Page')
    ap.add_argument('--news', action='store_true', help='Fetch fresh RSS headlines and make 2 original news videos/cards')
    ap.add_argument('--news-upload', action='store_true', help='Upload up to 2 ready original news videos to YouTube')
    ap.add_argument('--facebook-reels', action='store_true', help='Publish up to 2 ready news videos as Facebook Reels')
    args = ap.parse_args()
    if args.check: check_config(); return
    if args.queue: show_queue(); return
    if args.authorize: get_youtube(); print('YouTube authorization complete.'); return
    if args.daily: publish_daily(); return
    if args.daily_images:
        from image_posts import generate_two
        generate_two(); return
    if args.facebook_images:
        from uploaders.facebook import publish_daily_images
        publish_daily_images(2); return
    if args.news:
        from news_engine import generate
        generate(2); return
    if args.news_upload:
        from uploaders.youtube import publish_news
        publish_news(2); return
    if args.facebook_reels:
        from uploaders.facebook import publish_daily_reels
        publish_daily_reels(2); return
    ap.print_help()

if __name__ == '__main__': main()
