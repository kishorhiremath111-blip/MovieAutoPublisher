#!/usr/bin/env python3
"""Facebook Page publisher using the official Graph API.

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
        raise FileNotFoundError(
            f'Missing {CREDS}. Copy the example and add your Page ID/token locally.'
        )
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


def publish_video(video_path, title='', description=''):
    """Publish a normal Page video, separate from Reels."""
    cfg = load_creds()
    page_id = cfg['page_id']
    token = cfg['page_access_token']
    version = cfg.get('graph_api_version', 'v24.0')
    url = f'https://graph.facebook.com/{version}/{page_id}/videos'
    with Path(video_path).open('rb') as fh:
        response = requests.post(
            url,
            data={
                'access_token': token,
                'title': title[:255],
                'description': description[:5000],
            },
            files={'source': (Path(video_path).name, fh, 'video/mp4')},
            timeout=600,
        )
    response.raise_for_status()
    data = response.json()
    return data.get('id')


def publish_daily_images(limit=2):
    state_path = ROOT / 'state' / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    done = 0
    for item in state.get('image_posts', []):
        if item.get('status') != 'ready' or item.get('facebook', {}).get('status') == 'uploaded':
            continue
        image = ROOT / item['image']
        if not image.exists():
            continue
        post_id = publish_photo(image, item.get('caption', ''))
        item.setdefault('facebook', {})['status'] = 'uploaded'
        item['facebook']['post_id'] = post_id
        item['facebook']['updated_at'] = int(time.time())
        done += 1
        if done >= limit:
            break
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Facebook images: {done}/{limit}')


def publish_news_video(limit=1):
    """Publish ready daily news roundup(s) as normal Facebook Page videos."""
    state_path = ROOT / 'state' / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    done = 0
    for item in state.get('news', []):
        if item.get('status') != 'ready':
            continue
        if item.get('facebook_video', {}).get('status') == 'uploaded':
            continue
        video = ROOT / item.get('video', '')
        if not video.exists():
            continue
        video_id = publish_video(
            video,
            item.get('title', ''),
            item.get('caption', ''),
        )
        item.setdefault('facebook_video', {})['status'] = 'uploaded'
        item['facebook_video']['video_id'] = video_id
        item['facebook_video']['updated_at'] = int(time.time())
        done += 1
        if done >= limit:
            break
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Facebook news videos: {done}/{limit}')


def publish_reel(video_path, description=''):
    """Publish a short vertical MP4 as a Facebook Page Reel via the Graph API."""
    cfg = load_creds()
    page_id = cfg['page_id']
    token = cfg['page_access_token']
    version = cfg.get('graph_api_version', 'v24.0')
    base = f'https://graph.facebook.com/{version}/{page_id}/video_reels'
    start = requests.post(
        base,
        params={
            'access_token': token,
            'upload_phase': 'start',
        },
        timeout=120,
    )
    start.raise_for_status()
    data = start.json()
    video_id = data.get('video_id')
    upload_url = data.get('upload_url')
    if not video_id or not upload_url:
        raise RuntimeError(f'Facebook Reel start failed: {data}')

    size = Path(video_path).stat().st_size
    with Path(video_path).open('rb') as fh:
        upload = requests.post(
            upload_url,
            headers={
                'Authorization': f'OAuth {token}',
                'offset': '0',
                'file_size': str(size),
            },
            data=fh,
            timeout=300,
        )
    upload.raise_for_status()

    finish = requests.post(
        base,
        params={
            'access_token': token,
            'upload_phase': 'finish',
            'video_id': video_id,
            'video_state': 'PUBLISHED',
            'description': description[:5000],
        },
        timeout=120,
    )
    finish.raise_for_status()
    return video_id


def publish_daily_reels(limit=2):
    state_path = ROOT / 'state' / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    done = 0
    for item in state.get('news', []):
        if item.get('status') != 'ready' or item.get('facebook_reel', {}).get('status') == 'uploaded':
            continue
        video = ROOT / item['short'] if item.get('short') else ROOT / item['video']
        if not video.exists():
            continue
        reel_id = publish_reel(video, item.get('caption', ''))
        item.setdefault('facebook_reel', {})['status'] = 'uploaded'
        item['facebook_reel']['video_id'] = reel_id
        item['facebook_reel']['updated_at'] = int(time.time())
        done += 1
        if done >= limit:
            break
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Facebook reels: {done}/{limit}')
