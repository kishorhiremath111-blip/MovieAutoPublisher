#!/usr/bin/env python3
"""Facebook Page photo publisher using the official Graph API.

Configure credentials/facebook_page.json locally; never commit it.
"""
import json
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT / 'credentials' / 'facebook_page.json'


def load_creds():
    if not CREDS.exists():
        raise FileNotFoundError(f'Missing {CREDS}. Copy the example and add your Page ID/token locally.')
    return json.loads(CREDS.read_text(encoding='utf-8'))


def publish_photo(image_path, message=''):
    cfg = load_creds()
    page_id = cfg['page_id']
    token = cfg['page_access_token']
    version = cfg.get('graph_api_version', 'v24.0')
    url = f'https://graph.facebook.com/{version}/{page_id}/photos'
    with Path(image_path).open('rb') as fh:
        response = requests.post(
            url,
            data={'access_token': token, 'caption': message},
            files={'source': (Path(image_path).name, fh, 'image/jpeg')},
            timeout=120,
        )
    response.raise_for_status()
    data = response.json()
    return data.get('post_id') or data.get('id')


def publish_daily_images(limit=2):
    state_path = ROOT / 'state' / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    done = 0
    for item in state.get('image_posts', []):
        if item.get('status') != 'ready' or item.get('facebook', {}).get('status') == 'uploaded':
            continue
        image = ROOT / item['image']
        post_id = publish_photo(image, item.get('caption', ''))
        item.setdefault('facebook', {})['status'] = 'uploaded'
        item['facebook']['post_id'] = post_id
        item['facebook']['updated_at'] = int(time.time())
        done += 1
        if done >= limit:
            break
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Facebook images: {done}/{limit}')


if __name__ == '__main__':
    publish_daily_images()
