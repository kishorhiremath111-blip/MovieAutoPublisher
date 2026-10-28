#!/usr/bin/env python3
"""daily_luxury.py - one luxury Short per day: find topic -> verify -> build -> upload.

Steps
  1. Pick today's theme (Mon-Sun rotation) and ask Gemini (with Google Search) for ONE fresh
     topic. News themes need real, recent news backed by 2+ search sources and a second
     fact-check pass. Weekend themes are clearly labelled "concept" (imagined, AI visuals).
  2. Skip anything similar to an earlier topic (state/published.json).
  3. Build project.json and render the video with luxury_editor.py (Gemini images + music).
  4. Upload to YouTube: UPLOAD_MODE = dry (build only) | private | public. Default: dry.

Music: put licensed tracks in music/ (they rotate daily); empty = built-in modern score.
Env: GEMINI_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
Optional: UPLOAD_MODE, VIDEO_RES (4k|1080), GEMINI_TEXT_MODEL, GEMINI_IMAGE_MODEL,
          TZ_OFFSET_MIN (default 330 = India)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / 'state' / 'published.json'
OUT_DIR = ROOT / 'output'
API = 'https://generativelanguage.googleapis.com/v1beta'
# Model IDs from Google's docs (Oct 2026). First one that exists for your key is used.
TEXT_MODELS = ([os.environ['GEMINI_TEXT_MODEL']] if os.environ.get('GEMINI_TEXT_MODEL') else
               ['gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite'])
IMAGE_MODELS = ['gemini-3.1-flash-image', 'gemini-3.1-flash-image-preview',
                'gemini-3.1-flash-lite-image', 'gemini-2.5-flash-image']
_ACTIVE = {}

THEMES = {
    0: ('news', 'Billionaire / trillionaire wealth news: fortunes, rankings, big deals'),
    1: ('news', 'Supercars and hypercars: a new launch, record sale or auction'),
    2: ('news', 'Dubai and world mega-projects, record-expensive mansions, palaces, penthouses'),
    3: ('news', 'Private jets, mega yachts, private islands: a launch, sale or record'),
    4: ('news', 'Luxury watches and collections: a record auction or launch'),
    5: ('concept', 'Imagined luxury morning routine and breakfast of the ultra-wealthy'),
    6: ('concept', 'Imagined ultra-luxury chill party / evening lifestyle'),
}
STOP = {'the', 'and', 'for', 'new', 'with', 'from', 'that', 'this', 'its', 'his', 'her',
        'has', 'are', 'was', 'you', 'your', 'inside', 'world', 'most'}


class Fatal(Exception):
    """Do not retry."""


def log(msg):
    print(f'[{datetime.now(timezone.utc):%H:%M:%S}] {msg}', flush=True)


# ---------------- state ----------------
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {'entries': []}


def save_state(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(STATE_FILE)


def tokens(s):
    return {w for w in re.findall(r'[a-z0-9]+', s.lower()) if len(w) > 2 and w not in STOP}


def is_duplicate(title, previous, thr=0.55):
    a = tokens(title)
    for p in previous:
        b = tokens(p)
        if a and b:
            inter = len(a & b)
            if inter / len(a | b) >= thr or inter / min(len(a), len(b)) >= 0.8:
                return True
    return False


# ---------------- Gemini text ----------------
def need_key():
    k = os.environ.get('GEMINI_API_KEY', '').strip()
    if not k:
        raise Fatal('GEMINI_API_KEY is not set.')
    return k


def api_detail(e):
    """Short, key-free reason from a Google API error response."""
    try:
        j = json.loads(e.read() or b'{}').get('error', {})
        return (str(j.get('status', '')) + ' ' + ' '.join(str(j.get('message', '')).split())[:300]).strip()
    except Exception:
        return ''


def gemini(prompt, search=True, temperature=0.8):
    key = need_key()
    body = {'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': temperature}}
    if search:
        body['tools'] = [{'google_search': {}}]
    data, failures, quota_hits = None, [], 0
    for model in ([_ACTIVE[search]] if _ACTIVE.get(search) else TEXT_MODELS):
        for attempt in range(4):
            try:
                req = urllib.request.Request(
                    f'{API}/models/{model}:generateContent', json.dumps(body).encode(),
                    {'Content-Type': 'application/json', 'x-goog-api-key': key})
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                detail = api_detail(e)
                if e.code in (400, 404):          # model missing, or it cannot do search
                    log(f'  model "{model}" cannot be used here (HTTP {e.code}): {detail[:140]}')
                    failures.append(f'{model}: HTTP {e.code} {detail}')
                    break
                if e.code in (401, 403):
                    raise Fatal(f'Gemini refused the key (HTTP {e.code}) on "{model}": {detail}. '
                                f'Check the key and that the API is enabled in AI Studio.')
                if e.code == 429:
                    failures.append(f'{model}: HTTP 429 {detail}')
                    if attempt == 0:
                        log(f'  model "{model}" is rate-limited; waiting 20s, then trying again')
                        time.sleep(20)
                        continue
                    quota_hits += 1
                    log(f'  model "{model}" quota is used up; trying the next model')
                    break
                failures.append(f'{model}: HTTP {e.code} {detail}')
                time.sleep(2 ** attempt * 2)
            except (urllib.error.URLError, TimeoutError) as e:
                failures.append(f'{model}: network {type(e).__name__}')
                time.sleep(2 ** attempt * 2)
        if data:
            if _ACTIVE.get(search) != model:
                log(f'  using text model: {model} (search={"on" if search else "off"})')
            _ACTIVE[search] = model
            break
    if not data and quota_hits:
        raise Fatal(f'Gemini QUOTA/BILLING limit (HTTP 429) on {quota_hits} model(s): ' +
                    ' | '.join(failures[-3:]) + '. Wait for the daily reset, or enable billing / use '
                    'another project key: https://ai.dev/rate-limit')
    if not data:
        raise Fatal('Gemini text call failed on every model. Last errors: ' +
                    ' | '.join(failures[-4:]) + '. Run the "Gemini check" workflow.')
    if not data.get('candidates'):
        raise RuntimeError('Gemini returned no candidates: ' +
                           json.dumps(data.get('promptFeedback', {}))[:300])
    cand = data['candidates'][0]
    text = ''.join(p.get('text', '') for p in cand.get('content', {}).get('parts', []))
    chunks = cand.get('groundingMetadata', {}).get('groundingChunks', [])
    sources = [{'title': c['web'].get('title', ''), 'uri': c['web'].get('uri', '')}
               for c in chunks if 'web' in c]
    return text, sources


def extract_json(text):
    text = re.sub(r'```(?:json)?', '', text)
    i, j = text.find('{'), text.rfind('}')
    if i < 0 or j <= i:
        raise ValueError('no JSON in reply')
    return json.loads(text[i:j + 1])


SCHEMA = '''Return ONLY JSON:
{"topic": "short unique name", "mode": "%(mode)s", "news_date": "YYYY-MM-DD or empty",
 "title": "YouTube title, max 80 chars, truthful, no fake claims",
 "hook": "max 10 words, ALL CAPS, English letters only, curiosity-driven and TRUE",
 "facts": ["3-5 specific facts with numbers/dates"],
 "description": "2 sentences",
 "hashtags": ["#luxury", "...5 to 7 total"],
 "scenes": [
  {"type": "full", "prompt": "photographic scene", "search": "stock photo query", "seconds": 4.5},
  {"type": "stack", "top_prompt": "...", "top_search": "...", "bottom_prompt": "...",
   "bottom_search": "...", "seconds": 5}]}
Every image has BOTH a "prompt" (for AI) and a "search" (2-4 words for a real stock-photo
search, generic and photographable, e.g. "Dubai skyline night", "luxury yacht deck",
"supercar headlight close up". Never a person's name or a brand logo).
Scenes: 6 or 7. Scene 1 must be "full" and visually striking (it carries the hook). Use 2 "stack"
scenes (two different views, e.g. exterior + detail). Sum of all scene seconds between 32 and 52.
Every prompt describes a real-photograph-style scene about this topic: no text, no logos,
no real person's face (use silhouettes, hands, backs, objects, architecture instead).'''


def propose(mode, theme, today, avoid):
    if mode == 'news':
        rules = (f'Today is {today:%Y-%m-%d}. Use Google Search to find ONE real luxury news story '
                 f'published in the last 7 days about: {theme}. Do not invent anything. If a number '
                 f'or claim cannot be confirmed by search, leave it out. Set mode "news" and '
                 f'news_date to the story date.')
    else:
        rules = (f'Create ONE imagined (not real) concept about: {theme}. It must not name any real '
                 f'person, brand or event, and must not claim to be true. Set mode "concept", '
                 f'news_date "".')
    prompt = (f'{rules}\nAvoid these topics already covered: {json.dumps(avoid[-60:])}\n'
              f'{SCHEMA % {"mode": mode}}')
    text, sources = gemini(prompt, search=(mode == 'news'))
    t = extract_json(text)
    t['sources'] = sources
    return t


def verify_news(t):
    prompt = ('You are a strict fact-checker. Use Google Search. Check the hook and every fact '
              'below. Pass only if ALL are supported by reliable sources and the hook is not '
              'misleading.\n' + json.dumps({'hook': t['hook'], 'facts': t['facts']}) +
              '\nReturn ONLY JSON: {"verdict": "pass" or "fail", "issues": ["..."]}')
    text, _ = gemini(prompt, search=True, temperature=0.1)
    v = extract_json(text)
    return v.get('verdict') == 'pass', v.get('issues', [])


def validate(t, mode, today):
    def bad(msg):
        raise ValueError(msg)
    for k in ('topic', 'title', 'hook', 'facts', 'description', 'hashtags', 'scenes'):
        if not t.get(k):
            bad(f'missing {k}')
    if t.get('mode') != mode:
        bad('wrong mode')
    hook = re.sub(r'[^A-Za-z0-9 ,.!?$%&\'-]', '', t['hook']).upper().strip()
    if not hook or len(hook.split()) > 12:
        bad('hook empty or too long')
    t['hook'] = hook
    sc = t['scenes']
    if not 5 <= len(sc) <= 8 or sc[0].get('type') != 'full':
        bad('need 5-8 scenes, first must be full')
    total = 0
    for s in sc:
        if s.get('type') == 'full':
            ok = bool(s.get('prompt') or s.get('search'))
        elif s.get('type') == 'stack':
            ok = bool((s.get('top_prompt') or s.get('top_search')) and
                      (s.get('bottom_prompt') or s.get('bottom_search')))
        else:
            ok = False
        if not ok:
            bad('bad scene')
        s['seconds'] = min(7.0, max(3.0, float(s.get('seconds', 4.5))))
        total += s['seconds']
    total -= 0.7 * (len(sc) - 1)
    if not 25 <= total <= 58:
        bad(f'duration {total:.0f}s outside 25-58s')
    if mode == 'news':
        try:
            age = (today.date() - datetime.strptime(t.get('news_date', ''), '%Y-%m-%d').date()).days
        except ValueError:
            bad('news_date missing')
        if not -1 <= age <= 10:
            bad(f'news is {age} days old')
        if len({s['title'] for s in t['sources'] if s['title']}) < 2:
            bad('fewer than 2 distinct search sources')
    t['hashtags'] = [h if h.startswith('#') else '#' + h for h in t['hashtags']][:8]
    return t


def pick_topic(mode, theme, today, state):
    prior = [e['topic'] for e in state['entries']] + [e['title'] for e in state['entries']]
    for attempt in range(1, 5):
        log(f'Topic search, attempt {attempt}...')
        raw = None
        try:
            raw = propose(mode, theme, today, prior)
            t = validate(raw, mode, today)
            if is_duplicate(t['topic'], prior) or is_duplicate(t['title'], prior):
                raise ValueError('too similar to an earlier video')
            if mode == 'news':
                ok, issues = verify_news(t)
                if not ok:
                    raise ValueError(f'fact-check failed: {issues}')
            return t
        except Fatal:
            raise
        except (ValueError, RuntimeError, KeyError, TypeError) as e:
            log(f'  rejected: {e}')
            if isinstance(raw, dict) and raw.get('topic'):
                prior.append(str(raw['topic']))
                state['entries'].append({'date': f'{today:%Y-%m-%d}', 'topic': str(raw['topic']),
                                         'title': str(raw.get('title', '')), 'status': 'rejected',
                                         'reason': str(e)[:200]})
    raise Fatal('No acceptable topic found today. Nothing was faked or uploaded.')


# ---------------- build ----------------
MUSIC_DIR = ROOT / 'music'
MUSIC_EXT = {'.mp3', '.m4a', '.wav', '.aac', '.ogg'}


def pick_music(day_ordinal):
    """Licensed tracks you put in music/ rotate daily. Empty folder -> built-in modern score."""
    files = sorted(f for f in MUSIC_DIR.glob('*') if f.suffix.lower() in MUSIC_EXT) \
        if MUSIC_DIR.exists() else []
    return files[day_ordinal % len(files)] if files else None


def build_video(t, day_dir, res):
    day_dir.mkdir(parents=True, exist_ok=True)
    track = pick_music(datetime.now(timezone.utc).toordinal())
    t['music_file'] = track.name if track else ''
    project = {'hook': t['hook'], 'music': str(track) if track else 'auto',
               'music_style': 'modern', 'hook_y': 0.45, 'scenes': t['scenes']}
    pj = day_dir / 'project.json'
    pj.write_text(json.dumps(project, indent=2), encoding='utf-8')
    out = day_dir / 'short.mp4'
    cmd = [sys.executable, str(ROOT / 'luxury_editor.py'), str(pj), '-o', str(out),
           '--res', res, '--preset', 'veryfast', '--crf', '18']
    log(f'Rendering video ({res})...')
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3300)
    sys.stdout.write(r.stdout[-1500:])
    if r.returncode or not out.exists():
        raise Fatal('Video build failed:\n' + (r.stderr or r.stdout)[-1500:])
    cj = out.with_suffix('.credits.json')
    try:
        c = json.loads(cj.read_text(encoding='utf-8'))
        t['credits'], t['ai_count'] = c.get('stock', []), int(c.get('ai_count', 0))
    except (OSError, ValueError):
        t['credits'], t['ai_count'] = [], 1
    return out


def build_description(t):
    ai = t.get('ai_count', 1) > 0
    lines = [t['description'].strip(), '']
    if t['mode'] == 'concept':
        lines += ['Imagined luxury concept. Not a real event.' + (' Visuals are AI-generated.' if ai else '')]
    else:
        lines += ['Visuals are AI-generated illustrations, not photographs of the event.' if ai
                  else 'Photos are illustrative stock images, not footage of the event.']
        names = sorted({s['title'] for s in t['sources'] if s['title']})[:4]
        if names:
            lines += ['Sources: ' + ', '.join(names)]
    if t.get('credits'):
        lines += [', '.join(sorted({c['credit'] for c in t['credits']}))[:700]]
    credits = MUSIC_DIR / 'credits.txt'
    if t.get('music_file') and credits.exists():       # attribution some free tracks require
        lines += ['', credits.read_text(encoding='utf-8').strip()[:500]]
    lines += ['', ' '.join(t['hashtags']) + ' #Shorts']
    return '\n'.join(lines)[:4800]


# ---------------- YouTube ----------------
def youtube_client():
    """Reuse the existing VYROX uploader's base64-encoded OAuth JSON secrets."""
    import base64
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    client_b64 = os.environ.get('YOUTUBE_CLIENT_SECRET_B64', '').strip()
    token_b64 = os.environ.get('YOUTUBE_TOKEN_B64', '').strip()
    missing = [name for name, value in (
        ('YOUTUBE_CLIENT_SECRET_B64', client_b64),
        ('YOUTUBE_TOKEN_B64', token_b64),
    ) if not value]
    if missing:
        raise Fatal('Missing existing YouTube uploader secrets: ' + ', '.join(missing))
    try:
        client_info = json.loads(base64.b64decode(client_b64, validate=True))
        token_info = json.loads(base64.b64decode(token_b64, validate=True))
        # Validate the OAuth client JSON, but use the authorized token file's matching
        # client_id/client_secret/refresh_token so the existing token scope is preserved.
        oauth_client = client_info.get('installed') or client_info.get('web') or {}
        if not oauth_client.get('client_id') or not oauth_client.get('client_secret'):
            raise ValueError('client_secret.json has no installed/web OAuth client')
        if not token_info.get('refresh_token'):
            raise ValueError('token.json has no refresh_token')
        creds = Credentials.from_authorized_user_info(
            token_info, scopes=['https://www.googleapis.com/auth/youtube.upload'])
    except Exception as exc:
        raise Fatal('Could not read existing YouTube OAuth JSON secrets. Check YOUTUBE_CLIENT_SECRET_B64 and YOUTUBE_TOKEN_B64 in Actions secrets (' + type(exc).__name__ + ').') from exc
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


def upload(yt, video, t, privacy):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    title = t['title'].strip()
    if t['mode'] == 'concept' and 'concept' not in title.lower():
        title = title[:70].rstrip() + ' (Concept)'
    body = {'snippet': {'title': title[:100], 'description': build_description(t),
                        'tags': [h.lstrip('#') for h in t['hashtags']], 'categoryId': '22'},
            'status': {'privacyStatus': privacy, 'selfDeclaredMadeForKids': False}}
    if t.get('ai_count', 1) > 0:                  # AI images -> disclose; stock-only -> not needed
        body['status']['containsSyntheticMedia'] = True
    def start():
        media = MediaFileUpload(str(video), mimetype='video/mp4', resumable=True,
                                chunksize=8 * 1024 * 1024)
        return yt.videos().insert(part='snippet,status', body=body, media_body=media)

    req = start()
    resp, fails, dropped = None, 0, False
    while resp is None:
        try:
            _, resp = req.next_chunk()
        except HttpError as e:
            code = e.resp.status
            text = (getattr(e, 'content', b'') or b'').decode('utf-8', 'replace')
            reason = ' '.join(text.split())[:240]
            if code in (500, 502, 503, 504) and fails < 5:
                fails += 1
                time.sleep(2 ** fails)
                continue
            if code == 400 and 'containsSyntheticMedia' in text and not dropped:
                log('  YouTube did not accept the AI-disclosure field; retrying without it. '
                    'Please tick "altered content" in YouTube Studio for this video.')
                body['status'].pop('containsSyntheticMedia', None)
                dropped = True
                req = start()
                continue
            if code == 403 and 'quota' in text.lower():
                raise Fatal('YouTube daily upload quota is used up. It resets daily; try tomorrow.')
            if code in (401, 403):
                raise Fatal(f'YouTube refused the request (HTTP {code}): {reason} | If this says '
                            f'invalid_grant/unauthorized: the refresh token expired (app still in '
                            f'Testing mode) - make a new token.')
            raise Fatal(f'YouTube upload failed: HTTP {code}: {reason}')
    return resp['id']


# ---------------- preflight ----------------
def preflight(mode):
    """Stock-only preflight: no Gemini API key or model checks."""
    import shutil
    ok = True
    names = (['YOUTUBE_CLIENT_SECRET_B64', 'YOUTUBE_TOKEN_B64'] if mode != 'dry' else [])
    for n in names:
        has = bool(os.environ.get(n, '').strip())
        ok &= has
        print(f'secret {n}: {"OK" if has else "MISSING  <- add it in repository Actions secrets"}')
    print('image source: Wikimedia Commons licensed photos (Gemini disabled; no photo API key required)')
    for tool in ('ffmpeg', 'ffprobe'):
        has = bool(shutil.which(tool))
        ok &= has
        print(f'{tool}: {"OK" if has else "MISSING"}')
    has_editor = (ROOT / 'luxury_editor.py').exists()
    ok &= has_editor
    print(f'file luxury_editor.py: {"OK" if has_editor else "MISSING"}')
    print('PREFLIGHT', 'PASSED' if ok else 'FAILED')
    return 0 if ok else 1


def stock_only_topic(today, theme, state):
    """Build a safe evergreen luxury topic from a fixed rotation; never calls Gemini."""
    ideas = [
        ('Dubai skyline luxury architecture', 'Inside the Visual World of Dubai Luxury Architecture',
         'THE SKYLINE THAT LOOKS UNREAL', 'Dubai skyline night|luxury skyscraper exterior|modern penthouse interior|Dubai waterfront skyline|luxury architectural details|city skyline aerial|premium hotel lobby',
         '#luxury #Dubai #architecture #luxurylifestyle #Shorts'),
        ('supercar design details', 'The Details That Make Supercars Look Extraordinary',
         'EVERY DETAIL FEELS EXPENSIVE', 'luxury sports car detail|supercar headlight closeup|sports car wheel detail|supercar rear design|luxury car interior|sports car road cinematic|supercar showroom',
         '#supercar #luxurycars #cardesign #luxury #Shorts'),
        ('luxury yacht design', 'Inside the Details of Modern Luxury Yachts',
         'THIS IS LUXURY ON THE WATER', 'luxury yacht ocean|yacht deck design|yacht interior luxury|yacht bow closeup|superyacht marina|yacht sea aerial|luxury boat sunset',
         '#luxuryyacht #yachtlife #luxurytravel #luxury #Shorts'),
        ('luxury mansion interiors', 'Luxury Mansion Details That Make a Statement',
         'THE DETAILS CHANGE EVERYTHING', 'luxury mansion exterior|modern mansion living room|luxury staircase interior|marble mansion interior|luxury bedroom design|infinity pool mansion|luxury home architecture',
         '#luxuryhomes #mansion #interiordesign #luxury #Shorts'),
        ('luxury watches craftsmanship', 'The Craftsmanship Behind Luxury Watch Design',
         'PRECISION IN EVERY DETAIL', 'luxury watch closeup|mechanical watch movement|watch dial macro|luxury watch wrist|watchmaker hands detail|premium watch display|watch case detail',
         '#luxurywatch #watchmaking #craftsmanship #luxury #Shorts'),
        ('private aviation luxury', 'A Closer Look at Private Aviation Luxury',
         'A DIFFERENT VIEW OF LUXURY', 'private jet airport|private jet cabin interior|private aircraft exterior|luxury aircraft seating|private jet stairs|business jet runway|aircraft window view',
         '#privatejet #aviation #luxurytravel #luxury #Shorts'),
        ('luxury resort and travel design', 'Luxury Resort Design Made for the Escape',
         'ESCAPE INTO ANOTHER WORLD', 'luxury resort infinity pool|tropical luxury villa|resort ocean view|luxury hotel suite|luxury resort architecture|private villa pool|luxury resort sunset',
         '#luxurytravel #luxuryresort #travelinspiration #luxury #Shorts')
    ]
    idx = today.date().toordinal() % len(ideas)
    previous = {str(e.get('topic', '')).lower() for e in state.get('entries', [])}
    for off in range(len(ideas)):
        candidate = ideas[(idx + off) % len(ideas)]
        if candidate[0].lower() not in previous:
            idx = (idx + off) % len(ideas)
            break
    topic, title, hook, queries, hashtags = ideas[idx]
    q = queries.split('|')
    scenes = [
        {'type': 'full', 'search': q[0], 'seconds': 4.5},
        {'type': 'stack', 'top_search': q[1], 'bottom_search': q[2], 'seconds': 5},
        {'type': 'full', 'search': q[3], 'seconds': 4.5},
        {'type': 'stack', 'top_search': q[4], 'bottom_search': q[5], 'seconds': 5},
        {'type': 'full', 'search': q[6], 'seconds': 4.5},
        {'type': 'full', 'search': q[1], 'seconds': 4.5}
    ]
    return {'topic': topic, 'title': title, 'hook': hook,
            'description': 'A cinematic look at premium design, craftsmanship and luxury lifestyle details, using licensed stock photography.',
            'hashtags': hashtags.split(), 'facts': [], 'mode': 'concept', 'news_date': '',
            'sources': [], 'scenes': scenes, 'stock_only': True}


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default=os.environ.get('UPLOAD_MODE') or 'dry',
                    choices=['dry', 'private', 'public'])
    ap.add_argument('--res', default=os.environ.get('VIDEO_RES') or '4k', choices=['4k', '1080'])
    ap.add_argument('--weekday', type=int, help='0=Mon..6=Sun, for testing a theme')
    ap.add_argument('--force', action='store_true', help='allow a second video today')
    ap.add_argument('--preflight', action='store_true', help='check secrets, files and models only')
    a = ap.parse_args()
    if a.preflight:
        return preflight(a.mode)

    now = datetime.now(timezone.utc) + timedelta(minutes=int(os.environ.get('TZ_OFFSET_MIN') or 330))
    state = load_state()
    day = f'{now:%Y-%m-%d}'
    done = [e for e in state['entries'] if e.get('date') == day and e.get('status', '')
            .startswith(('uploaded', 'built'))]
    if done and not a.force:
        log(f'Already made today\'s video ({done[0]["title"]}). Skipping.')
        return 0

    mode, theme = THEMES[a.weekday if a.weekday is not None else now.weekday()]
    log(f'Mode={a.mode}  stock-only theme: {theme}')
    try:
        t = stock_only_topic(now, theme, state)
        log('Gemini API disabled: using built-in luxury topics and Pexels photo tracking.')
        log(f'Topic: {t["title"]}  | hook: {t["hook"]}')
        video = build_video(t, OUT_DIR / day, a.res)
        entry = {'date': day, 'topic': t['topic'], 'title': t['title'], 'mode': t['mode'],
                 'status': 'built', 'video_id': '', 'music': t.get('music_file', ''),
                 'sources': sorted({s['title'] for s in t['sources'] if s['title']})}
        state['entries'].append(entry)
        save_state(state)
        if a.mode == 'dry':
            log(f'DRY mode: video saved at {video}. Nothing uploaded.')
            return 0
        vid = upload(youtube_client(), video, t, a.mode)
        entry.update(status=f'uploaded_{a.mode}', video_id=vid)
        save_state(state)
        log(f'Uploaded ({a.mode}): https://youtu.be/{vid}')
        return 0
    except Fatal as e:
        log(f'FAILED: {e}')
        save_state(state)
        return 1
    except Exception as e:                      # never leave a silent traceback
        log(f'FAILED unexpectedly: {type(e).__name__}: {str(e)[:300]}')
        save_state(state)
        return 1


if __name__ == '__main__':
    sys.exit(main())
