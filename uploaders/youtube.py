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
from viral_tracker import score_candidate, trend_index

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


def _recently_used_topics(state, day, cooldown_days=30):
    from datetime import date, timedelta
    today = date.fromisoformat(day)
    cutoff = today - timedelta(days=max(1, int(cooldown_days)))
    used = set()
    for stamp, row in state.get('daily', {}).items():
        try:
            row_day = date.fromisoformat(str(stamp)[:10])
        except Exception:
            continue
        if not (cutoff <= row_day < today):
            continue
        for key in ('movie_long_topics', 'movie_short_topics', 'movie_reel_topics'):
            used.update(str(x).strip().casefold() for x in row.get(key, []) if x)
    for row in state.get('image_posts', []):
        try:
            made = date.fromtimestamp(float(row.get('created_at', 0)))
        except Exception:
            continue
        if cutoff <= made < today and row.get('topic_id'):
            used.add(str(row['topic_id']).strip().casefold())
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
    daily.setdefault('movie_long_sources', [])
    daily.setdefault('movie_short_sources', [])
    cooldown_days = int(load_json(ROOT / 'config' / 'config.json', {}).get('viral_no_repeat_days', 30))
    used_recent = _recently_used_sources(state, day, cooldown_days)
    used_recent_topics = _recently_used_topics(state, day, cooldown_days)

    long_done = bool(daily.get('movie_long_sources') and daily.get('long_video_id'))
    short_done = bool(daily.get('movie_short_sources') and daily.get('short_video_id'))
    if long_done and short_done:
        same_source = daily['movie_long_sources'][0] == daily['movie_short_sources'][0]
        long_topic_old = str((daily.get('movie_long_topics') or [''])[0])
        short_topic_old = str((daily.get('movie_short_topics') or [''])[0])
        if same_source or (long_topic_old and short_topic_old and long_topic_old == short_topic_old):
            raise RuntimeError('Daily audit failed: previously recorded long and Short reuse a source or topic.')
        print('Daily movie video and Short are already uploaded; skipping duplicate uploads.')
        return

    # Only today's date-specific recuts are eligible. Source paths are the
    # identity boundary, so one movie cannot fill both daily formats.
    by_source = {}
    for item in state.get('queue', []):
        key = _item_key(item)
        if not key or item.get('date') != day or item.get('status') != 'ready':
            continue
        by_source.setdefault(key, item)

    eligible = {}
    trends = trend_index()
    tracker = load_json(ROOT / 'state' / 'viral_tracker.json', {})
    candidate_scores = {}
    for key, item in by_source.items():
        if key in used_recent:
            continue
        source_path = str(item.get('source') or item.get('source_item_id') or key)
        topic_id = str(item.get('topic_id') or item.get('source_item_id') or key)
        if topic_id.strip().casefold() in used_recent_topics:
            continue
        video = ROOT / str(item.get('video', ''))
        short = ROOT / str(item.get('short', ''))
        uploads = item.setdefault('uploads', {}).setdefault('youtube', {})
        if video.exists() and short.exists():
            score_item = dict(item)
            score_item['id'] = key
            score_item['selected_highlight'] = item.get('short_highlight') or {}
            score, breakdown = score_candidate(score_item, trends, tracker)
            item['viral_score'] = score
            item['viral_breakdown'] = breakdown
            candidate_scores[key] = score
            eligible[key] = (item, uploads, video, short, source_path, topic_id)

    # Trend-match and source quality rank candidates; this ranking never downloads
    # or copies the popular creators' own videos.
    eligible = dict(sorted(
        eligible.items(), key=lambda row: candidate_scores.get(row[0], 0.0), reverse=True
    ))
    for key, data in eligible.items():
        print(f"Candidate rank: {data[0].get('title', key)} score={candidate_scores.get(key, 0.0):.2f}")

    existing_long_source = str(daily.get('movie_long_sources', [''])[0] or '')
    existing_short_source = str(daily.get('movie_short_sources', [''])[0] or '')
    existing_long_topic = str(daily.get('movie_long_topics', [''])[0] or '')
    existing_short_topic = str(daily.get('movie_short_topics', [''])[0] or '')
    long_candidates = [
        (key, *data) for key, data in eligible.items()
        if not long_done
        and data[1].get('long_status') != 'uploaded'
        and (not short_done or data[4] != existing_short_source)
        and (not existing_short_source or data[4] != existing_short_source)
        and (not existing_short_topic or data[5] != existing_short_topic)
    ]
    short_candidates = [
        (key, *data) for key, data in eligible.items()
        if not short_done
        and data[1].get('short_status') != 'uploaded'
        and (not long_done or data[4] != existing_long_source)
        and (not existing_long_source or data[4] != existing_long_source)
        and (not existing_long_topic or data[5] != existing_long_topic)
    ]

    long_choice = long_candidates[0] if not long_done and long_candidates else None
    if short_done:
        short_choice = None
    else:
        long_source_chosen = long_choice[5] if long_choice else existing_long_source
        long_topic_chosen = long_choice[6] if long_choice else existing_long_topic
        short_choice = next((row for row in short_candidates
                             if row[5] != long_source_chosen and row[6] != long_topic_chosen), None)

    if not long_done and long_choice is None:
        raise RuntimeError(
            'No fresh authorized source is ready for today\'s long video. Add valid licensed movie/series/anime source files.'
        )
    if not short_done and short_choice is None:
        raise RuntimeError(
            'No DIFFERENT fresh authorized source is ready for today\'s Short. '
            'The same source will not be reused for both formats.'
        )

    # Quality-check all uploads still needed before making a public upload.
    if long_choice:
        _check_audio_video(long_choice[3])
    if short_choice:
        _check_audio_video(short_choice[4])

    if long_choice:
        long_key, long_item, long_uploads, long_video, long_short_path, long_source_path, long_topic = long_choice
        long_thumb = ROOT / long_item['thumbnail'] if long_item.get('thumbnail') else None
        long_pack = long_item.get('viral_pack') or {}
        long_title = long_pack.get('title') or long_item.get('title', 'Movie Scene Highlights')
        long_description = long_item.get('description', '')
        long_tags = long_item.get('tags', [])
        long_privacy = long_item.get('privacy_status', 'public')
        print(f'Uploading long from source {long_source_path}: {long_video}')
        long_id = upload_video(long_video, long_title, long_description, long_tags, long_privacy, long_thumb)
        record_tracker(long_id, long_item, 'movie-long')
        long_uploads['long_status'] = 'uploaded'
        long_uploads['long_video_id'] = long_id
        long_uploads['updated_at'] = int(time.time())
        daily['long'].append(long_key)
        daily.setdefault('movie_long_variant_ids', []).append(long_key)
        daily['movie_long_sources'].append(long_source_path)
        daily.setdefault('movie_long_topics', []).append(str(long_item.get('topic_id') or long_item.get('source_item_id') or long_key))
        daily.setdefault('movie_long_item_ids', []).append(str(long_item.get('source_item_id') or long_key))
        daily['long_video_id'] = long_id
        save_json(state_path, state)
        existing_long_source = long_source_path
        existing_long_topic = long_topic
        long_done = True

    if short_choice:
        short_key, short_item, short_uploads, short_source_video, short_video, short_source_path, short_topic = short_choice
        short_thumb = ROOT / short_item['thumbnail'] if short_item.get('thumbnail') else None
        short_pack = short_item.get('viral_pack') or {}
        short_title = short_pack.get('title') or short_item.get('title', 'Scene of the Day')
        if '#Shorts' not in short_title:
            short_title = short_title[:88].rstrip() + ' #Shorts'
        short_description = short_item.get('description', '')
        if short_item.get('caption_text') and short_item['caption_text'] not in short_description:
            short_description = (short_description + '\n\n' + short_item['caption_text']).strip()
        print(f'Uploading Short from distinct source {short_source_path}: {short_video}')
        short_id = upload_video(short_video, short_title, short_description, short_item.get('tags', []),
                                short_item.get('privacy_status', 'public'), short_thumb)
        record_tracker(short_id, short_item, 'movie-short')
        short_uploads['short_status'] = 'uploaded'
        short_uploads['short_video_id'] = short_id
        short_uploads['updated_at'] = int(time.time())
        daily['short'].append(short_key)
        daily.setdefault('movie_short_variant_ids', []).append(short_key)
        daily['movie_short_sources'].append(short_source_path)
        daily.setdefault('movie_short_topics', []).append(str(short_item.get('topic_id') or short_item.get('source_item_id') or short_key))
        daily.setdefault('movie_short_item_ids', []).append(str(short_item.get('source_item_id') or short_key))
        daily['short_video_id'] = short_id
        save_json(state_path, state)
        existing_short_source = short_source_path
        existing_short_topic = short_topic
        short_done = True

    if long_done and short_done and (existing_long_source == existing_short_source or
                                     (existing_long_topic and existing_short_topic and existing_long_topic == existing_short_topic)):
        raise RuntimeError('Daily publish audit failed: long and Short share a source path or topic.')
    print(
        f'Daily result: long={int(long_done)}/{limit_long} source={existing_long_source}; '
        f'short={int(short_done)}/{limit_short} source={existing_short_source}; distinct_sources_and_topics=yes'
    )


if __name__ == '__main__':
    publish_daily()
