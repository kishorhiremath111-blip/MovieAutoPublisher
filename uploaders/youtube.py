#!/usr/bin/env python3
"""Official YouTube Data API uploader for licensed/reusable content."""
import json
import time
import subprocess
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parents[1]
CREDS = ROOT / 'credentials'
CLIENT_SECRET = CREDS / 'client_secret.json'
TOKEN = CREDS / 'token.json'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']


def load_json(path, default):
    if not path.exists():
        return default
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def get_youtube():
    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(
            f'Missing {CLIENT_SECRET}. Put your downloaded Google Desktop OAuth JSON here.'
        )
    creds = None
    if TOKEN.exists():
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
        TOKEN.write_text(creds.to_json(), encoding='utf-8')
    return build('youtube', 'v3', credentials=creds)


def upload_video(video_path, title, description='', tags=None, privacy='private', thumbnail=None):
    youtube = get_youtube()
    body = {
        'snippet': {
            'title': title[:100],
            'description': description[:5000],
            'tags': (tags or [])[:500],
            'categoryId': '22'
        },
        'status': {'privacyStatus': privacy}
    }
    media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response['id']
    if thumbnail and Path(thumbnail).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail))
            ).execute()
        except HttpError as exc:
            print(f'Warning: thumbnail upload failed: {exc}')
    return video_id



def record_tracker(video_id, item, kind):
    tracker_path = ROOT / 'state' / 'viral_tracker.json'
    tracker = load_json(tracker_path, {'published_youtube': [], 'performance': [], 'used': []})
    rows = tracker.setdefault('published_youtube', [])
    if any(str(x.get('video_id')) == str(video_id) for x in rows):
        return
    rows.append({
        'video_id': video_id,
        'published_at': int(time.time()),
        'category': item.get('category', kind),
        'edit_style': item.get('edit_style', kind),
        'viral_score': item.get('viral_score', 0),
        'kind': kind,
        'title': item.get('title', ''),
    })
    save_json(tracker_path, tracker)


def _item_key(item):
    return str(item.get('item_id') or item.get('id') or '')


def _recently_used_sources(state, day, cooldown_days=30):
    from datetime import date, timedelta
    today = date.fromisoformat(day)
    cutoff = today - timedelta(days=cooldown_days)
    used = set()
    for stamp, row in state.get('daily', {}).items():
        try:
            age_day = date.fromisoformat(str(stamp)[:10])
        except Exception:
            continue
        if cutoff <= age_day <= today:
            for key in ('long', 'short', 'reel'):
                used.update(str(x) for x in row.get(key, []) if x is not None)
    return used


def _check_audio_video(path):
    """Refuse blank/silent uploads; preserve the original scene audio."""
    path = Path(path)
    if not path.exists() or path.stat().st_size < 100_000:
        raise RuntimeError(f'Media QA failed: missing or too-small file: {path}')
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type',
         '-of', 'csv=p=0', str(path)],
        capture_output=True, text=True
    )
    kinds = set(probe.stdout.split())
    if probe.returncode or not {'video', 'audio'}.issubset(kinds):
        raise RuntimeError(f'Media QA failed: video and original audio streams are required: {path}')
    dur = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        capture_output=True, text=True
    )
    try:
        seconds = float(dur.stdout.strip())
    except Exception:
        seconds = 0.0
    if dur.returncode or seconds < 8:
        raise RuntimeError(f'Media QA failed: invalid duration {seconds:.2f}s: {path}')
    print(f'Media QA OK: {path.name} duration={seconds:.1f}s audio+video=present')


def publish_daily(limit_long=1, limit_short=1):
    state_path = ROOT / 'state' / 'state.json'
    state = load_json(state_path, {'processed': {}, 'queue': [], 'daily': {}})
    day = time.strftime('%Y-%m-%d')
    daily = state.setdefault('daily', {}).setdefault(day, {'long': [], 'short': [], 'reel': [], 'images': []})
    daily.setdefault('long', [])
    daily.setdefault('short', [])
    daily.setdefault('reel', [])
    used_recent = _recently_used_sources(state, day, 30)

    # Build one output row per source so two parts of the same movie can never
    # masquerade as two distinct daily subjects.
    by_source = {}
    for item in state.get('queue', []):
        key = _item_key(item)
        if not key or item.get('status') != 'ready':
            continue
        by_source.setdefault(key, item)

    eligible = {}
    for key, item in by_source.items():
        if key in used_recent:
            continue
        video = ROOT / str(item.get('video', ''))
        short = ROOT / str(item.get('short', ''))
        uploads = item.setdefault('uploads', {}).setdefault('youtube', {})
        if video.exists() and short.exists():
            eligible[key] = (item, uploads, video, short)

    long_candidates = [
        (key, *data) for key, data in eligible.items()
        if data[1].get('long_status') != 'uploaded'
    ]
    short_candidates = [
        (key, *data) for key, data in eligible.items()
        if data[1].get('short_status') != 'uploaded'
    ]
    if not long_candidates or not short_candidates:
        raise RuntimeError(
            'Not enough unused authorized video sources for today. Need one fresh long-video source '
            'and a DIFFERENT fresh Short source. Add more licensed movie/series/anime files to metadata.json.'
        )
    long_choice = long_candidates[0]
    short_choice = next((row for row in short_candidates if row[0] != long_choice[0]), None)
    if short_choice is None:
        raise RuntimeError(
            'Only one unused source is available. Refusing to upload the same subject as both the long video and Short.'
        )

    long_key, long_item, long_uploads, long_video, long_short_path = long_choice
    short_key, short_item, short_uploads, short_source_video, short_video = short_choice
    # Validate both exports before either is published.
    _check_audio_video(long_video)
    _check_audio_video(short_video)

    long_thumb = ROOT / long_item['thumbnail'] if long_item.get('thumbnail') else None
    long_pack = long_item.get('viral_pack') or {}
    long_title = long_pack.get('title') or long_item.get('title', 'Movie Scene Highlights')
    long_description = long_item.get('description', '')
    long_tags = long_item.get('tags', [])
    long_privacy = long_item.get('privacy_status', 'public')

    print(f'Uploading long from distinct source {long_key}: {long_video}')
    long_id = upload_video(long_video, long_title, long_description, long_tags, long_privacy, long_thumb)
    record_tracker(long_id, long_item, 'movie-long')
    long_uploads['long_status'] = 'uploaded'
    long_uploads['long_video_id'] = long_id
    long_uploads['updated_at'] = int(time.time())
    daily['long'].append(long_key)

    short_thumb = ROOT / short_item['thumbnail'] if short_item.get('thumbnail') else None
    short_pack = short_item.get('viral_pack') or {}
    short_title = short_pack.get('title') or short_item.get('title', 'Scene of the Day')
    if '#Shorts' not in short_title:
        short_title = short_title[:88].rstrip() + ' #Shorts'
    short_description = short_item.get('description', '')
    if short_item.get('caption_text') and short_item['caption_text'] not in short_description:
        short_description = (short_description + '\\n\\n' + short_item['caption_text']).strip()
    print(f'Uploading Short from distinct source {short_key}: {short_video}')
    short_id = upload_video(short_video, short_title, short_description, short_item.get('tags', []),
                            short_item.get('privacy_status', 'public'), short_thumb)
    record_tracker(short_id, short_item, 'movie-short')
    short_uploads['short_status'] = 'uploaded'
    short_uploads['short_video_id'] = short_id
    short_uploads['updated_at'] = int(time.time())
    daily['short'].append(short_key)
    daily['long_video_id'] = long_id
    daily['short_video_id'] = short_id
    save_json(state_path, state)
    print(f'Daily result: long=1/1 source={long_key}; short=1/1 source={short_key}; distinct_sources=yes')


def publish_news(limit=1):
    """Upload only today's fresh worldwide roundup(s): long + Short."""
    state_path = ROOT / 'state' / 'state.json'
    state = load_json(state_path, {'news': [], 'daily': {}})
    day = time.strftime('%Y-%m-%d')
    done = 0
    daily = state.setdefault('daily', {}).setdefault(day, {'long': [], 'short': []})

    for item in state.get('news', []):
        if item.get('date') != day or item.get('status') != 'ready':
            continue
        if item.get('youtube', {}).get('status') == 'uploaded':
            continue

        video = ROOT / item['video']
        if not video.exists():
            print(f'News video missing: {video}')
            continue

        pack = item.get('viral_pack') or {}
        title = (pack.get('title') or item['title'])[:100]
        description = item.get('caption', '')[:5000]
        tags = [
            'News', 'WorldNews', 'IndiaNews', 'Sports', 'Health',
            'Technology', 'Electronics', 'Science', 'Space',
            'Cars', 'Bikes', 'Crime', 'Anime', 'Entertainment'
        ]
        vid = upload_video(video, title, description, tags, 'public', item.get('thumbnail'))
        record_tracker(vid, item, 'news')

        item.setdefault('youtube', {})['status'] = 'uploaded'
        item['youtube']['video_id'] = vid
        item['youtube']['updated_at'] = int(time.time())
        daily['long'].append(item.get('id'))

        # If no authorized social Short was uploaded today, use the fresh
        # rights-cleared news Short as the daily fallback. This guarantees the
        # daily Short quota without creating a second Short when social content
        # is available.
        if not daily.get('short') and item.get('short'):
            short = ROOT / item['short']
            if short.exists():
                short_title = (pack.get('title') or item['title'])[:88].rstrip() + ' #Shorts'
                short_vid = upload_video(short, short_title, description, tags, 'public', item.get('thumbnail'))
                record_tracker(short_vid, item, 'news-short')
                daily['short'].append(item.get('id'))
                item.setdefault('youtube', {})['short_status'] = 'uploaded'
                item['youtube']['short_video_id'] = short_vid

        done += 1
        if done >= limit:
            break

    save_json(state_path, state)
    print(f'News YouTube: roundups={done}/{limit}')


if __name__ == '__main__':
    publish_daily()


def publish_social(limit=1):
    """Upload today's authorized short-form social clips to YouTube."""
    state_path = ROOT / 'state' / 'state.json'
    state = load_json(state_path, {'social': [], 'daily': {}})
    day = time.strftime('%Y-%m-%d')
    done = 0
    daily = state.setdefault('daily', {}).setdefault(day, {'long': [], 'short': []})

    for item in state.get('social', []):
        if item.get('date') != day or item.get('status') != 'ready':
            continue
        yt = item.setdefault('youtube', {})
        if yt.get('status') == 'uploaded':
            continue
        video = ROOT / item['video']
        if not video.exists():
            continue
        pack = item.get('viral_pack') or {}
        title = (pack.get('title') or item.get('title', 'Short'))[:88].rstrip()
        if '#Shorts' not in title:
            title += ' #Shorts'
        tags = item.get('tags', [])[:500]
        vid = upload_video(
            video,
            title,
            item.get('description', ''),
            tags,
            'public',
            item.get('thumbnail')
        )
        record_tracker(vid, item, 'social-short')
        yt.update({'status': 'uploaded', 'video_id': vid, 'updated_at': int(time.time())})
        daily['short'].append(item.get('id'))
        done += 1
        if done >= limit:
            break

    save_json(state_path, state)
    print(f'Social YouTube: {done}/{limit}')
