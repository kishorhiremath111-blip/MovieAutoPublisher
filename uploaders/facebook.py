#!/usr/bin/env python3
"""Facebook Page publisher using the official Graph API.

Configure credentials/facebook_page.json locally; never commit it.
"""
import json
import time
import subprocess
from pathlib import Path
from viral_tracker import score_candidate, trend_index

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


def publish_daily_images(limit=3):
    state_path = ROOT / 'state' / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    today = time.strftime('%Y-%m-%d')
    done = 0
    for item in state.get('image_posts', []):
        if item.get('date') != today:
            continue
        # Ignore legacy/news cards; only separately licensed image-source cards are eligible.
        if item.get('asset_type') not in {'licensed_image_source', 'ai_generated_image'}:
            continue
        if item.get('status') != 'ready' or item.get('facebook', {}).get('status') == 'uploaded':
            continue
        image = ROOT / item['image']
        if not image.exists():
            continue
        post_id = publish_photo(image, item.get('caption', ''))
        item.setdefault('facebook', {})['status'] = 'uploaded'
        item['facebook']['post_id'] = post_id
        item['facebook']['updated_at'] = int(time.time())
        daily = state.setdefault('daily', {}).setdefault(today, {'long': [], 'short': [], 'reel': [], 'images': []})
        daily.setdefault('image_posts_uploaded', []).append(item.get('source_item') or item.get('id'))
        done += 1
        if done >= limit:
            break
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Facebook images: {done}/{limit}')


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



def publish_movie_reels(limit=1):
    """Publish a distinct authorized movie/series/anime Short as today's Page Reel."""
    from datetime import date, timedelta
    state_path = ROOT / 'state' / 'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    today = time.strftime('%Y-%m-%d')
    daily = state.setdefault('daily', {}).setdefault(today, {'long': [], 'short': [], 'reel': [], 'images': []})
    if daily.get('movie_reel_sources'):
        print('Facebook movie Reel: already recorded for today')
        return

    cutoff = date.fromisoformat(today) - timedelta(days=30)
    used_ids = set()
    used_sources = set()
    processed = state.get('processed', {})
    for stamp, row in state.get('daily', {}).items():
        try:
            row_day = date.fromisoformat(str(stamp)[:10])
        except Exception:
            continue
        if cutoff <= row_day <= date.fromisoformat(today):
            for key in ('long', 'short', 'reel'):
                used_ids.update(str(x) for x in row.get(key, []) if x is not None)
    # Source-path separation is required for today's three formats. Reuse on
    # later days is allowed only through a fresh scene window created by process.py.
    for item_id in daily.get('long', []) + daily.get('short', []):
        src = processed.get(str(item_id), {}).get('source')
        if src:
            used_sources.add(str((ROOT / src).resolve()))

    # Topic identity must also differ from today's YouTube long video and Short.
    blocked_topics = {
        str(x).strip().casefold()
        for key in ('movie_long_topics', 'movie_short_topics')
        for x in daily.get(key, []) if x
    }
    # Keep topics unique across recent days, including previously published image cards.
    cutoff_topics = date.fromisoformat(today) - timedelta(days=30)
    today_date = date.fromisoformat(today)
    for stamp, history in state.get('daily', {}).items():
        try:
            history_date = date.fromisoformat(str(stamp)[:10])
        except Exception:
            continue
        if cutoff_topics <= history_date < today_date:
            for key in ('movie_long_topics', 'movie_short_topics', 'movie_reel_topics'):
                blocked_topics.update(str(x).strip().casefold() for x in history.get(key, []) if x)
    for post in state.get('image_posts', []):
        try:
            post_day = date.fromtimestamp(float(post.get('created_at', 0)))
        except Exception:
            continue
        if cutoff_topics <= post_day < today_date and post.get('topic_id'):
            blocked_topics.add(str(post['topic_id']).strip().casefold())
    # Rank only authorized source files with current trend metadata. We reuse
    # the metadata signal, never the trending creators' videos themselves.
    trends = trend_index()
    tracker_path = ROOT / 'state' / 'viral_tracker.json'
    try:
        tracker = json.loads(tracker_path.read_text(encoding='utf-8'))
    except Exception:
        tracker = {}
    candidates = []
    for item in state.get('social', []):
        if item.get('date') != today:
            continue
        topic_id = str(item.get('topic_id') or item.get('source_item_id') or item.get('id') or '')
        if topic_id and topic_id.strip().casefold() in blocked_topics:
            continue
        item_id = str(item.get('id') or '')
        src_rel = str(item.get('source') or '')
        video_rel = str(item.get('video') or '')
        video = ROOT / video_rel
        source = ROOT / src_rel if src_rel else None
        if (item.get('licensed') is True and item.get('status') == 'ready'
                and item.get('facebook_reel', {}).get('status') != 'uploaded'
                and item_id and item_id not in used_ids and video.is_file()):
            source_key = str(source.resolve()) if source and source.exists() else str(video.resolve())
            if source_key not in used_sources:
                score, breakdown = score_candidate(item, trends, tracker)
                item['viral_score'] = score
                item['viral_breakdown'] = breakdown
                candidates.append((score, item_id, item, video, source_key, 'social'))

    for item in state.get('queue', []):
        item_id = str(item.get('item_id') or '')
        if item.get('date') != today:
            continue
        video_rel = str(item.get('short') or '')
        video = ROOT / video_rel
        source_rel = processed.get(item_id, {}).get('source', '')
        source_key = str((ROOT / source_rel).resolve()) if source_rel else str(video.resolve())
        topic_id = str(item.get('topic_id') or item.get('source_item_id') or item_id)
        if (item.get('status') == 'ready' and item_id and item_id not in used_ids
                and topic_id.strip().casefold() not in blocked_topics
                and video.is_file() and source_key not in used_sources):
            score_item = dict(item)
            score_item['id'] = item_id
            score_item['selected_highlight'] = item.get('short_highlight') or {}
            score, breakdown = score_candidate(score_item, trends, tracker)
            item['viral_score'] = score
            item['viral_breakdown'] = breakdown
            candidates.append((score, item_id, item, video, source_key, 'movie'))

    # Highest trend-relevance score wins among authorized, unused sources.
    candidates.sort(key=lambda row: row[0], reverse=True)
    selected = []
    seen_ids, seen_paths = set(), set()
    for row in candidates:
        if row[1] in seen_ids or row[4] in seen_paths:
            continue
        selected.append(row)
        seen_ids.add(row[1]); seen_paths.add(row[4])
        if len(selected) >= limit:
            break

    if not selected:
        print('Facebook movie Reel: 0/1; no distinct unused licensed source available.')
        return

    done = 0
    for viral_score, item_id, item, video, source_key, source_kind in selected:
        # Check for actual audio and video streams; do not post a silent placeholder.
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type',
             '-of', 'csv=p=0', str(video)],
            capture_output=True, text=True
        )
        kinds = set(probe.stdout.split())
        if probe.returncode or not {'audio', 'video'}.issubset(kinds):
            print(f'Facebook Reel blocked by media QA: {video.name}')
            continue
        caption = str(item.get('description') or item.get('caption') or '').strip()
        caption_text = str(item.get('caption_text') or '').strip()
        if caption_text and caption_text not in caption:
            caption = (caption + '\n\n' + caption_text).strip()
        print(f"Facebook Reel candidate selected by trend score={viral_score:.2f}: {item.get('title', item_id)}")
        reel_id = publish_reel(video, caption)
        item.setdefault('facebook_reel', {}).update({
            'status': 'uploaded', 'video_id': reel_id,
            'updated_at': int(time.time()), 'source_kind': source_kind
        })
        daily.setdefault('reel', []).append(item_id)
        daily.setdefault('reel_sources', []).append(source_key)
        daily.setdefault('movie_reel_sources', []).append(source_key)
        daily.setdefault('movie_reel_topics', []).append(str(item.get('topic_id') or item.get('source_item_id') or item_id))
        daily.setdefault('movie_reel_scores', []).append(float(viral_score))
        blocked_topics.add(str(item.get('topic_id') or item.get('source_item_id') or item_id).strip().casefold())
        daily.setdefault('movie_reel_item_ids', []).append(str(item.get('source_item_id') or item_id))
        used_sources.add(source_key)
        used_ids.add(item_id)
        done += 1
        if done >= limit:
            break

    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Facebook movie Reel: {done}/{limit}')
