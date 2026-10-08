#!/usr/bin/env python3
"""YouTube trend metadata collector.

Uses the official YouTube Data API to discover what is popular in India and
what music is trending. It stores metadata only; it does not download or
re-upload other creators' videos or audio.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config' / 'config.json'
OUT = ROOT / 'state' / 'youtube_trends.json'
API = 'https://www.googleapis.com/youtube/v3/videos'


def load(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def fetch_chart(api_key, region, category=None, max_results=50):
    params = {
        'part': 'snippet,statistics,contentDetails',
        'chart': 'mostPopular',
        'regionCode': region,
        'maxResults': max(1, min(50, int(max_results))),
        'key': api_key,
    }
    if category:
        params['videoCategoryId'] = str(category)
    url = API + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'MovieAutoPublisher/Trend-Discovery/1.0'}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode('utf-8'))


def channel_stats(api_key, channel_ids):
    if not channel_ids:
        return {}
    url = 'https://www.googleapis.com/youtube/v3/channels?' + urllib.parse.urlencode({
        'part': 'statistics,snippet',
        'id': ','.join(sorted(channel_ids))[:8000],
        'key': api_key,
    })
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'MovieAutoPublisher/Trend-Discovery/1.0'}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode('utf-8'))
    return {
        item['id']: {
            'title': item.get('snippet', {}).get('title', ''),
            'subscribers': int(item.get('statistics', {}).get('subscriberCount', 0) or 0),
        }
        for item in data.get('items', [])
    }


def normalize(items, channel_map, source):
    out = []
    for item in items:
        sn = item.get('snippet', {})
        stats = item.get('statistics', {})
        vid = item.get('id')
        cid = sn.get('channelId', '')
        if not vid or not cid:
            continue
        out.append({
            'video_id': vid,
            'title': sn.get('title', ''),
            'channel_id': cid,
            'channel_title': sn.get('channelTitle', ''),
            'published_at': sn.get('publishedAt', ''),
            'category_id': sn.get('categoryId', ''),
            'view_count': int(stats.get('viewCount', 0) or 0),
            'like_count': int(stats.get('likeCount', 0) or 0),
            'subscribers': channel_map.get(cid, {}).get('subscribers', 0),
            'source': source,
            'url': f'https://www.youtube.com/watch?v={vid}',
        })
    return out


def main():
    cfg = load(CONFIG, {})
    if not cfg.get('youtube_trend_discovery', True):
        print('YouTube trend discovery disabled.')
        return

    api_key = os.getenv('YOUTUBE_API_KEY', '').strip()
    if not api_key:
        print('YOUTUBE_API_KEY not set; skipping YouTube trend discovery.')
        return

    region = str(cfg.get('youtube_trend_region', 'IN')).upper()
    max_results = int(cfg.get('youtube_trend_max_results', 50))
    music_max = int(cfg.get('youtube_music_trend_max_results', 25))

    try:
        all_data = fetch_chart(api_key, region, None, max_results)
        music_data = fetch_chart(api_key, region, '10', music_max)
    except Exception as exc:
        print(f'YouTube trend API failed: {exc}')
        return

    raw_items = all_data.get('items', []) + music_data.get('items', [])
    channel_ids = {x.get('snippet', {}).get('channelId') for x in raw_items}
    channel_ids.discard(None)
    try:
        channels = channel_stats(api_key, channel_ids)
    except Exception as exc:
        print(f'Channel stats failed: {exc}')
        channels = {}

    items = normalize(all_data.get('items', []), channels, 'mostPopular-IN')
    music = normalize(music_data.get('items', []), channels, 'music-IN')

    min_subs = int(cfg.get('popular_creator_min_subscribers', 10000000))
    big_creators = [
        x for x in items
        if x['subscribers'] >= min_subs
    ]

    payload = {
        'created_at': int(time.time()),
        'region': region,
        'popular': items,
        'music': music,
        'popular_creator_min_subscribers': min_subs,
        '10m_plus_popular_metadata': big_creators,
        'policy': {
            'metadata_only': True,
            'third_party_clip_download': False,
            'creator_clip_use': 'authorized_or_rights_cleared_only',
            'music_use': 'platform_library_or_licensed_local_only'
        }
    }
    save(OUT, payload)
    print(
        f'YouTube trends saved: popular={len(items)} music={len(music)} '
        f'10m+ creators in chart={len(big_creators)}'
    )


if __name__ == '__main__':
    main()
