#!/usr/bin/env python3
"""Official YouTube Data API uploader for licensed/reusable content."""
import json, time
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
    if not path.exists(): return default
    with path.open('r', encoding='utf-8') as f: return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def get_youtube():
    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(f'Missing {CLIENT_SECRET}. Put your downloaded Google Desktop OAuth JSON here.')
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
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response['id']
    if thumbnail and Path(thumbnail).exists():
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail))).execute()
        except HttpError as exc:
            print(f'Warning: thumbnail upload failed: {exc}')
    return video_id


def publish_daily(limit_long=1, limit_short=1):
    state_path = ROOT / 'state' / 'state.json'
    state = load_json(state_path, {'processed': {}, 'queue': [], 'daily': {}})
    day = time.strftime('%Y-%m-%d')
    daily = state.setdefault('daily', {}).setdefault(day, {'long': [], 'short': []})
    long_done = 0
    short_done = 0

    # Queue order is deterministic. One long and one short per day.
    for item in state.get('queue', []):
        if item.get('status') != 'ready':
            continue
        uploads = item.setdefault('uploads', {})
        yt = uploads.get('youtube', {})
        video = ROOT / item['video']
        short = ROOT / item['short']
        thumb = ROOT / item['thumbnail'] if item.get('thumbnail') else None
        description = item.get('description', '')
        tags = item.get('tags', [])
        privacy = item.get('privacy_status', 'private')

        if long_done < limit_long and yt.get('long_status') != 'uploaded':
            print(f'Uploading long: {video}')
            vid = upload_video(video, item['title'], description, tags, privacy, thumb)
            yt['long_status'] = 'uploaded'; yt['long_video_id'] = vid; yt['updated_at'] = int(time.time())
            long_done += 1
            daily['long'].append(item.get('item_id'))

        if short_done < limit_short and yt.get('short_status') != 'uploaded':
            short_title = item['title']
            if '#Shorts' not in short_title:
                short_title = short_title[:88].rstrip() + ' #Shorts'
            print(f'Uploading short: {short}')
            vid = upload_video(short, short_title, description, tags, privacy, thumb)
            yt['short_status'] = 'uploaded'; yt['short_video_id'] = vid; yt['updated_at'] = int(time.time())
            short_done += 1
            daily['short'].append(item.get('item_id'))

        if long_done >= limit_long and short_done >= limit_short:
            break

    save_json(state_path, state)
    print(f'Daily result: long={long_done}/{limit_long}, short={short_done}/{limit_short}')


if __name__ == '__main__':
    publish_daily()
