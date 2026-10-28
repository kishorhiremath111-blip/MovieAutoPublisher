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
    """Choose an unused, specific luxury angle; stock photos only, no Gemini/API key."""
    ideas = [
        ('Dubai skyline architecture', 'Why Dubai Skyscrapers Look So Futuristic', 'A SKYLINE BUILT TO STAND OUT', 'Dubai futuristic skyline|Dubai skyscraper facade|Dubai penthouse view|Dubai waterfront skyline|modern tower architecture|Dubai skyline dusk|luxury hotel architecture', '#Dubai #architecture #luxury #Shorts'),
        ('supercar aerodynamics', 'The Design Tricks That Make Supercars Look Fast', 'SPEED STARTS WITH THE SHAPE', 'supercar aerodynamic design|sports car front splitter|supercar rear diffuser|sports car side profile|supercar carbon fiber detail|supercar on road|supercar showroom', '#supercars #cardesign #luxury #Shorts'),
        ('yacht infinity pools', 'Inside the Most Impressive Features of Luxury Yachts', 'A POOL IN THE MIDDLE OF THE OCEAN', 'superyacht ocean|yacht infinity pool|luxury yacht deck|yacht lounge interior|superyacht marina|yacht rear platform|yacht sunset sea', '#yacht #luxurytravel #luxury #Shorts'),
        ('mansion hidden rooms', 'The Hidden Spaces Inside Ultra-Luxury Homes', 'THIS HOUSE HAS A SECRET SIDE', 'luxury mansion exterior|hidden room luxury home|luxury home cinema|mansion staircase|luxury wine cellar interior|modern mansion living room|luxury home architecture', '#mansion #luxuryhomes #interiordesign #Shorts'),
        ('mechanical watch movement', 'The Tiny Details Behind Mechanical Luxury Watches', 'HUNDREDS OF PARTS. ONE PERFECT MOMENT.', 'mechanical watch movement macro|watchmaker hands closeup|luxury watch dial macro|watch gears detail|watch case polishing|luxury watch display|precision watchmaking', '#watchmaking #luxurywatch #craftsmanship #Shorts'),
        ('private jet cabin design', 'How Private Jet Cabins Turn Travel Into Luxury', 'THE CABIN IS A PRIVATE LOUNGE', 'private jet exterior|private jet cabin luxury|private aircraft seats|private jet dining area|business jet window|private jet stairs|private jet airport', '#privatejet #aviation #luxurytravel #Shorts'),
        ('overwater luxury villas', 'Why Overwater Villas Feel Like Another World', 'WAKE UP ABOVE THE OCEAN', 'overwater luxury villa|tropical villa deck|overwater bungalow aerial|luxury villa ocean view|private pool villa|tropical resort architecture|overwater villa sunset', '#luxurytravel #resort #Shorts'),
        ('luxury hotel lobbies', 'The Design Details That Make Hotel Lobbies Feel Expensive', 'THE FIRST 5 SECONDS FEEL DIFFERENT', 'luxury hotel lobby|grand hotel chandelier|marble hotel reception|designer hotel interior|luxury lobby staircase|premium hotel lounge|luxury hotel entrance', '#luxuryhotels #interiordesign #Shorts'),
        ('premium car interiors', 'Why Premium Car Interiors Feel So Different', 'YOU CAN FEEL THE DETAIL', 'luxury car interior leather|premium car dashboard|car ambient lighting interior|luxury car seat stitching|premium steering wheel detail|luxury car console|high end car interior', '#luxurycars #cardesign #Shorts'),
        ('supercar paint finishes', 'The Paint Finishes That Make Supercars Pop', 'THIS FINISH CHANGES EVERYTHING', 'supercar metallic paint|sports car glossy finish|supercar paint closeup|car detailing luxury|supercar body reflections|sports car showroom|supercar side profile', '#supercars #carculture #Shorts'),
        ('designer lighting interiors', 'How Statement Lighting Transforms Luxury Interiors', 'ONE LIGHT CAN CHANGE A ROOM', 'luxury pendant chandelier|modern luxury living room lighting|designer floor lamp interior|architectural lighting luxury home|marble interior chandelier|premium hotel lighting|luxury dining room', '#interiordesign #luxuryhomes #Shorts'),
        ('luxury bathroom design', 'Inside the Details of Spa-Level Luxury Bathrooms', 'A PRIVATE SPA AT HOME', 'luxury bathroom marble|freestanding bathtub luxury|spa bathroom design|rain shower luxury bathroom|luxury vanity design|modern bathroom lighting|premium bathroom interior', '#luxuryhomes #design #Shorts'),
        ('rooftop infinity pools', 'Why Rooftop Infinity Pools Look Unreal', 'THE EDGE DISAPPEARS', 'rooftop infinity pool skyline|luxury rooftop pool|infinity pool aerial|city hotel rooftop pool|modern luxury architecture pool|skyline pool sunset|luxury hotel pool deck', '#luxurytravel #architecture #Shorts'),
        ('private island retreats', 'What Makes a Private Island Retreat So Exclusive', 'YOUR OWN PIECE OF PARADISE', 'private island aerial|luxury island villa|tropical island beach house|private island resort dock|luxury island pool|private island ocean view|island resort sunset', '#privateretreat #luxurytravel #Shorts'),
        ('luxury train suites', 'Inside the World of Luxury Train Suites', 'FIRST CLASS ON RAILS', 'luxury train exterior|luxury train suite interior|premium train dining car|luxury rail travel cabin|train suite bed|luxury train window scenery|elegant train lounge', '#luxurytravel #trainjourney #Shorts'),
        ('supercar cockpit design', 'The Cockpit Details Built Around a Supercar Driver', 'EVERY CONTROL HAS A PURPOSE', 'supercar cockpit interior|sports car steering wheel closeup|supercar digital dashboard|performance car paddle shifters|sports car bucket seats|supercar center console|carbon fiber cockpit', '#supercars #cardesign #Shorts'),
        ('luxury sneaker craftsmanship', 'The Craftsmanship Behind Premium Sneaker Design', 'SMALL DETAILS. BIG DIFFERENCE.', 'premium sneaker material detail|luxury sneaker stitching|designer sneaker sole closeup|sneaker craftsmanship hands|premium leather sneaker|minimal sneaker design|sneaker display', '#sneakerdesign #craftsmanship #Shorts'),
        ('bespoke tailoring', 'The Precision Behind Bespoke Luxury Tailoring', 'MADE TO FIT ONE PERSON', 'bespoke suit tailoring|tailor measuring suit|luxury fabric swatches|hand stitching suit detail|tailoring workshop|premium suit jacket detail|bespoke menswear', '#bespoke #mensstyle #Shorts'),
        ('luxury perfume bottles', 'Why Luxury Perfume Bottles Are Designed Like Art', 'THE BOTTLE IS PART OF THE EXPERIENCE', 'luxury perfume bottle closeup|perfume glass craftsmanship|premium fragrance display|perfume bottle cap detail|luxury fragrance counter|perfume bottle reflections|elegant perfume collection', '#fragrance #luxurydesign #Shorts'),
        ('fine dining presentation', 'The Visual Details Behind Luxury Fine Dining', 'EVERY PLATE IS A DESIGN', 'fine dining plated dish|luxury restaurant table setting|chef plating gourmet food|fine dining interior|premium dessert presentation|elegant dining table|luxury restaurant ambience', '#finedining #luxurylifestyle #Shorts'),
        ('luxury penthouse terraces', 'The Outdoor Spaces That Define a Luxury Penthouse', 'A BALCONY ABOVE THE CITY', 'luxury penthouse terrace|penthouse skyline balcony|modern rooftop garden|luxury apartment terrace|city view outdoor lounge|penthouse outdoor dining|high rise terrace sunset', '#penthouse #architecture #Shorts'),
        ('sculptural staircases', 'Why Sculptural Staircases Become a Mansion Centrepiece', 'THIS STAIRCASE IS THE ARTWORK', 'sculptural staircase luxury home|floating staircase modern house|curved marble staircase|luxury interior stairs|architectural staircase detail|modern mansion interior|grand staircase lighting', '#architecture #luxuryhomes #Shorts'),
        ('luxury garage design', 'Inside the Showroom-Style Garages of Luxury Homes', 'THE GARAGE IS PART OF THE DESIGN', 'luxury home car garage|supercar collection garage|modern glass garage|luxury garage lighting|car display room mansion|premium garage flooring|luxury car storage', '#luxurycars #luxuryhomes #Shorts'),
        ('designer luggage details', 'The Design Details That Make Premium Luggage Stand Out', 'TRAVEL GEAR, REFINED', 'premium luggage suitcase detail|luxury suitcase wheels|designer travel luggage|leather luggage handle|premium luggage collection|elegant suitcase design|luxury travel accessories', '#luxurytravel #design #Shorts'),
        ('modern palace interiors', 'How Modern Palaces Blend Grandeur With Minimalism', 'GRAND, WITHOUT THE CLUTTER', 'modern palace exterior|palace luxury interior|grand marble hall|modern royal residence architecture|luxury palace chandelier|palace courtyard architecture|grand residence entrance', '#architecture #luxury #Shorts'),
        ('luxury home libraries', 'Inside the Quiet Luxury of Private Home Libraries', 'A ROOM BUILT FOR ESCAPE', 'luxury home library|floor to ceiling bookshelves mansion|modern reading room interior|luxury library ladder|wood paneled library|reading lounge luxury home|library architectural lighting', '#luxuryhomes #interiordesign #Shorts'),
        ('luxury outdoor kitchens', 'The Outdoor Kitchens Built for Resort-Style Living', 'DINNER WITH A VIEW', 'luxury outdoor kitchen|modern outdoor dining pavilion|outdoor kitchen stone counter|luxury patio kitchen|villa outdoor dining|poolside outdoor kitchen|garden entertaining luxury home', '#luxurylifestyle #design #Shorts'),
        ('yacht interiors materials', 'The Materials That Make Yacht Interiors Feel Premium', 'DESIGNED FOR LIFE AT SEA', 'luxury yacht interior wood|yacht leather seating detail|yacht marble table interior|superyacht cabin design|yacht interior lighting|luxury yacht lounge|yacht material craftsmanship', '#yacht #interiordesign #Shorts'),
        ('watch dial finishing', 'The Finishing Techniques Behind Luxury Watch Dials', 'THE DIAL IS A MINIATURE MASTERPIECE', 'luxury watch dial macro|watch dial guilloche|watch hands closeup|watch face texture|watchmaker loupe hands|luxury watch markers|watch dial craftsmanship', '#watchmaking #luxurywatch #Shorts'),
        ('hypercar rear design', 'Why Hypercar Rear Designs Look So Dramatic', 'THE BACK IS BUILT FOR DRAMA', 'hypercar rear design|supercar taillight closeup|sports car diffuser detail|hypercar exhaust design|supercar rear wing|hypercar carbon fiber|supercar rear at dusk', '#hypercar #cardesign #Shorts'),
        ('luxury resort arrival', 'The Arrival Experiences Designed by Luxury Resorts', 'THE EXPERIENCE STARTS AT THE GATE', 'luxury resort entrance|resort arrival driveway|luxury hotel porte cochere|tropical resort welcome|luxury resort lobby entrance|villa arrival walkway|premium hotel exterior', '#luxurytravel #luxuryresort #Shorts'),
        ('architectural glass facades', 'How Glass Facades Make Luxury Buildings Feel Weightless', 'A BUILDING MADE OF LIGHT', 'modern glass skyscraper facade|glass luxury villa architecture|reflective tower exterior|architectural glass facade detail|glass mansion windows|modern building reflections|luxury architecture skyline', '#architecture #luxury #Shorts'),
        ('luxury watch bracelets', 'The Detail Work Behind Premium Watch Bracelets', 'EVEN THE BRACELET IS ENGINEERED', 'luxury watch bracelet closeup|watch metal links macro|watch clasp detail|polished watch bracelet|watchmaker bracelet finishing|premium watch wrist detail|watch bracelet craftsmanship', '#luxurywatch #craftsmanship #Shorts'),
        ('premium home audio rooms', 'Inside Dedicated Listening Rooms in Luxury Homes', 'SOUND HAS ITS OWN SPACE', 'luxury home listening room|premium speaker setup interior|high end audio room|modern media room luxury home|audiophile listening chair|luxury home cinema speakers|acoustic wall panels interior', '#luxuryhomes #audiophile #Shorts'),
        ('luxury pool architecture', 'The Architectural Details Behind Iconic Luxury Pools', 'WATER BECOMES PART OF THE ARCHITECTURE', 'luxury pool architecture|modern villa swimming pool|infinity pool edge detail|luxury pool stone deck|architectural pool lighting|mansion pool aerial|resort pool design', '#architecture #luxurytravel #Shorts'),
        ('superyacht helipads', 'How Superyachts Make Room for Helicopter Landings', 'A HELIPAD ON THE OCEAN', 'superyacht helipad|luxury yacht aerial view|superyacht deck design|yacht helicopter landing area|large yacht marina|superyacht stern|yacht open sea', '#superyacht #luxurytravel #Shorts'),
        ('luxury wardrobe design', 'The Details Inside a Bespoke Luxury Dressing Room', 'A WARDROBE DESIGNED LIKE A BOUTIQUE', 'luxury walk in closet|bespoke dressing room design|luxury wardrobe lighting|designer closet island|premium closet cabinetry|luxury shoe display room|modern dressing room interior', '#luxuryhomes #interiordesign #Shorts'),
        ('luxury resort villas at night', 'How Resort Villas Transform After Sunset', 'THE NIGHT VERSION IS DIFFERENT', 'luxury villa night lighting|tropical resort villa at night|luxury pool night lighting|resort architecture dusk|villa exterior warm lights|luxury terrace evening|resort walkway night', '#luxurytravel #resortdesign #Shorts'),
        ('luxury car lighting design', 'The Light Signatures That Give Premium Cars Their Identity', 'YOU KNOW THE CAR BEFORE THE BADGE', 'luxury car headlight closeup|supercar LED taillight|premium car light signature|sports car front lights night|automotive lighting design|car rear lights detail|luxury car at dusk', '#cardesign #luxurycars #Shorts'),
        ('minimalist luxury interiors', 'The Quiet Details Behind Minimalist Luxury Interiors', 'LESS, BUT BETTER', 'minimalist luxury living room|quiet luxury interior design|premium natural stone interior|minimalist luxury bedroom|designer furniture detail|neutral luxury home|modern luxury interior texture', '#quietluxury #interiordesign #Shorts'),

        ('rich vs ultra rich homes', 'Rich vs Ultra-Rich Homes: The Visual Difference', 'RICH IS ONE THING. ULTRA-RICH IS ANOTHER.', 'modern luxury villa exterior|luxury mansion driveway|billionaire estate aerial|ultra luxury mansion pool|grand mansion entrance|private estate gardens|modern palace exterior', '#ultraluxury #luxuryhomes #Shorts'),
        ('premium vs ultra luxury travel', 'Premium vs Ultra-Luxury Travel', 'SAME DESTINATION. DIFFERENT WORLD.', 'five star hotel suite|luxury resort infinity pool|private jet cabin suite|private island villa aerial|luxury yacht transfer|private villa ocean view|luxury travel lounge', '#luxurytravel #ultraluxury #Shorts'),
        ('luxury car vs hypercar', 'Luxury Car vs Hypercar: What Changes?', 'ONE IS LUXURY. ONE IS PURE DRAMA.', 'luxury sedan exterior|premium sports car interior|hypercar front view|hypercar carbon fiber detail|supercar cockpit|hypercar rear diffuser|hypercar at sunset', '#hypercar #luxurycars #Shorts'),
        ('premium hotel vs private villa', 'Five-Star Hotel vs Private Luxury Villa', 'WHICH STAY FEELS MORE EXCLUSIVE?', 'five star hotel lobby|luxury hotel suite bedroom|private villa exterior|private pool villa ocean view|luxury villa living room|resort villa terrace|luxury villa at dusk', '#luxuryhotels #luxurytravel #Shorts'),
        ('quiet luxury vs flashy luxury', 'Quiet Luxury vs Flashy Luxury', 'WHICH LOOK COSTS MORE?', 'quiet luxury neutral outfit|tailored cashmere outfit|bold luxury fashion outfit|statement jewellery fashion|minimal luxury accessories|designer eveningwear detail|luxury fashion editorial', '#quietluxury #luxuryfashion #Shorts'),
        ('premium watch vs haute horlogerie', 'Premium Watch vs Haute Horlogerie', 'LOOK CLOSER AT THE CRAFT.', 'premium mechanical watch|watch dial macro detail|luxury watch movement|watchmaker precision tools|hand finished watch movement|watch case polishing|luxury watch collection', '#luxurywatch #watchmaking #Shorts'),
        ('normal pool vs infinity pool', 'Private Pool vs Ultra-Luxury Infinity Pool', 'THE VIEW CHANGES EVERYTHING.', 'modern villa swimming pool|luxury pool deck|ocean infinity pool aerial|cliffside infinity pool sunset|luxury resort pool edge|private villa pool view|infinity pool architecture', '#luxurydesign #luxurytravel #Shorts'),
        ('premium dining vs private chef', 'Fine Dining vs a Private Chef Experience', 'THE ULTIMATE TABLE IS PRIVATE.', 'fine dining tasting menu|luxury restaurant table setting|chef plating gourmet dish|private chef villa dining|luxury outdoor dinner table|private dining room|gourmet dinner ocean view', '#finedining #luxurylifestyle #Shorts'),
        ('first class vs private jet', 'First Class vs Private Jet', 'TWO WAYS TO FLY IN LUXURY.', 'first class airline suite|luxury airline cabin seat|private jet cabin interior|private jet bedroom cabin|private jet lounge seats|business jet exterior|private jet stairs luxury', '#privatejet #luxurytravel #Shorts'),
        ('luxury yacht vs mega yacht', 'Luxury Yacht vs Mega Yacht', 'HOW MUCH SPACE CAN A YACHT HAVE?', 'luxury yacht marina|yacht deck lounge|superyacht aerial ocean|mega yacht multiple decks|superyacht swimming pool|superyacht helipad deck|mega yacht sunset', '#superyacht #luxury #Shorts'),
        ('premium home vs billionaire estate', 'Premium Home vs Billionaire Estate', 'THE SCALE IS HARD TO BELIEVE.', 'modern luxury house exterior|designer home living room|billionaire mansion aerial|grand estate landscaped grounds|luxury mansion swimming pool|estate driveway aerial|ultra luxury home at dusk', '#luxuryhomes #architecture #Shorts'),
        ('luxury gym vs private wellness retreat', 'Luxury Gym vs Private Wellness Retreat', 'WELLNESS CAN LOOK LIKE THIS.', 'premium fitness studio interior|luxury gym equipment|private wellness retreat pool|luxury spa treatment room|wellness resort garden|sauna spa luxury interior|private retreat mountain view', '#wellness #luxurylifestyle #Shorts'),
        ('premium wardrobe vs bespoke dressing suite', 'Premium Wardrobe vs Bespoke Dressing Suite', 'A CLOSET THAT FEELS LIKE A BOUTIQUE.', 'modern luxury wardrobe|designer walk in closet|luxury dressing room island|bespoke closet cabinetry|luxury shoe display wall|dressing room chandelier|boutique style closet', '#luxuryhomes #interiordesign #Shorts'),
        ('healthy habits vs unhealthy habits', 'Healthy Habits vs Unhealthy Habits: Daily Choices', 'SMALL HABITS SHAPE THE DAY.', 'balanced healthy breakfast|morning outdoor exercise|fresh fruit water routine|sugary fast food meal|late night phone in bed|sedentary desk lifestyle|healthy sleep bedroom', '#healthyhabits #lifestyle #Shorts'),
        ('premium apartment vs penthouse', 'Luxury Apartment vs Sky-High Penthouse', 'THE VIEW IS THE FLEX.', 'luxury apartment living room|high rise apartment balcony|penthouse skyline terrace|luxury penthouse interior|rooftop private pool|penthouse dining view|luxury skyscraper at dusk', '#penthouse #luxuryhomes #Shorts'),
        ('premium luggage vs private travel setup', 'Premium Luggage vs Ultra-Luxury Travel Setup', 'THE JOURNEY STARTS BEFORE TAKEOFF.', 'premium travel suitcase|luxury luggage detail|private jet airport lounge|chauffeur luxury car arrival|private jet stairs|luxury travel accessories|exclusive airport lounge', '#luxurytravel #design #Shorts'),
        ('premium jewellery vs rare high jewellery', 'Fine Jewellery vs Rare High Jewellery', 'CRAFTSMANSHIP IS THE DIFFERENCE.', 'fine jewellery gemstone closeup|luxury gold jewellery detail|high jewellery gemstone setting|jeweller hands craftsmanship|diamond necklace display|precious gemstone macro|high jewellery editorial', '#highjewellery #luxury #Shorts'),
        ('premium bedroom vs royal suite', 'Premium Bedroom vs Ultra-Luxury Royal Suite', 'THIS IS NOT AN ORDINARY BEDROOM.', 'premium hotel bedroom|luxury bedroom interior|grand royal suite bedroom|luxury suite marble bathroom|hotel suite panoramic view|luxury suite lounge|royal suite chandelier', '#luxuryhotels #interiordesign #Shorts'),
        ('regular garage vs hypercar gallery', 'Regular Garage vs a Hypercar Gallery', 'THE GARAGE BECOMES THE SHOWROOM.', 'modern home garage|luxury garage storage|glass supercar garage|hypercar collection display|luxury garage lighting|mansion car gallery|supercar showroom interior', '#luxurycars #luxuryhomes #Shorts'),
        ('standard resort vs private island', 'Luxury Resort vs Your Own Private Island', 'HOW PRIVATE CAN A GETAWAY GET?', 'luxury resort beach aerial|five star resort pool|private island aerial view|private island villa dock|luxury island beach house|private island infinity pool|tropical island sunset', '#privateretreat #luxurytravel #Shorts'),
        ('luxury yacht night lighting', 'The Lighting Details That Make Superyachts Glow at Night', 'A FLOATING CITY AFTER DARK', 'superyacht night lights|luxury yacht marina at night|yacht deck lighting|superyacht ocean dusk|yacht illuminated exterior|luxury marina evening|superyacht stern night', '#superyacht #luxury #Shorts'),
        ('dubai vs tokyo future cities', 'Dubai vs Tokyo: Two Visions of the Future', 'TWO CITIES. TWO FUTURES.', 'Dubai skyline night|Dubai futuristic architecture|Tokyo Shibuya crossing night|Tokyo neon skyline|Dubai luxury towers aerial|Tokyo futuristic city street|Dubai marina blue hour', '#Dubai #Tokyo #futurecities #Shorts'),
        ('new york vs dubai penthouses', 'New York Penthouse vs Dubai Sky Mansion', 'WHICH SKYLINE WOULD YOU CHOOSE?', 'Manhattan penthouse skyline view|New York luxury apartment interior|Dubai penthouse panoramic view|Dubai skyline infinity pool|New York rooftop terrace|Dubai luxury high rise interior|city penthouse at dusk', '#NewYork #Dubai #luxuryhomes #Shorts'),
        ('japan bullet train vs private jet', 'Japan Bullet Train vs Private Jet', 'TWO INCREDIBLE WAYS TO TRAVEL.', 'Japanese Shinkansen train platform|Shinkansen train landscape|private jet cabin interior|private jet airport exterior|Japan high speed rail interior|private jet luxury seating|modern airport travel scene', '#Japan #PrivateJet #traveltech #Shorts'),
        ('tokyo capsule hotel vs dubai suite', 'Tokyo Capsule Hotel vs Dubai Ultra-Luxury Suite', 'SLEEPING SMALL VS LIVING LARGE.', 'Tokyo capsule hotel interior|Japanese capsule sleeping pod|Dubai luxury hotel suite|Dubai hotel marble bathroom|Tokyo compact hotel room|luxury suite panoramic skyline|modern hotel room design', '#Tokyo #DubaiHotels #Shorts'),
        ('japan street fashion vs paris quiet luxury', 'Tokyo Streetwear vs Paris Quiet Luxury', 'TWO STYLE WORLDS. ONE FASHION SCENE.', 'Tokyo streetwear fashion district|Harajuku fashion street style|Paris quiet luxury fashion editorial|minimal tailored fashion outfit|Tokyo fashion storefront|Paris luxury boutique street|modern fashion editorial details', '#TokyoFashion #ParisStyle #Shorts'),
        ('singapore green skyline vs hong kong', 'Singapore Green Skyline vs Hong Kong Vertical City', 'TWO SKYLINES BUILT FOR DENSITY.', 'Singapore skyline green architecture|Gardens by the Bay aerial|Hong Kong dense skyscrapers aerial|Hong Kong vertical city night|Singapore modern waterfront towers|Hong Kong high rise residential blocks|Asian megacity skyline dusk', '#Singapore #HongKong #architecture #Shorts'),
        ('dubai supercars vs tokyo car culture', 'Dubai Supercars vs Tokyo Night Car Culture', 'TWO CAR SCENES AFTER DARK.', 'Dubai supercar street night|luxury supercar Dubai marina|Tokyo car meet night|Japanese sports cars urban night|Dubai luxury car lineup|Tokyo automotive neon street|Japanese car culture parking meet', '#DubaiCars #TokyoCars #Shorts'),
        ('japan smart homes vs billionaire estates', 'Japanese Smart Homes vs Billionaire Smart Estates', 'TECHNOLOGY OR SCALE?', 'Japanese smart home minimalist interior|modern Japanese home automation|billionaire smart mansion interior|luxury home control system|Japanese modern architecture garden|smart mansion lighting scene|automated luxury home interior', '#SmartHome #JapanDesign #Shorts'),
        ('saudi mega projects vs dubai skyline', 'Saudi Mega Projects vs Dubai Skyline', 'THE GULF IS REIMAGINING ITS FUTURE.', 'Saudi Arabia futuristic architecture project|Riyadh modern skyline|Dubai skyline aerial|Dubai futuristic towers|Saudi desert megaproject architecture|Gulf modern city development|Middle East architecture dusk', '#SaudiArabia #Dubai #megaprojects #Shorts'),
        ('japan minimalist design vs dubai maximal luxury', 'Japanese Minimalism vs Dubai Maximal Luxury', 'LESS IS MORE — OR MORE IS MORE?', 'Japanese minimalist architecture interior|Japanese zen modern home|Dubai luxury gold interior|Dubai grand hotel lobby|Japanese natural wood design detail|luxury marble chandelier interior|modern interior design contrast', '#JapanDesign #DubaiLuxury #Shorts'),
        ('japan ryokan vs futuristic tokyo hotel', 'Traditional Japanese Ryokan vs Futuristic Tokyo Hotel', 'OLD-WORLD CALM MEETS TOMORROW.', 'Japanese ryokan tatami room|traditional Japanese inn garden|Tokyo futuristic hotel interior|modern Japanese hotel room|Japanese onsen architecture|Tokyo hotel skyline view|Japanese minimalist hospitality design', '#JapanTravel #Tokyo #Shorts'),
        ('dubai desert resort vs swiss alpine retreat', 'Dubai Desert Resort vs Swiss Alpine Retreat', 'DESERT GLAMOUR OR MOUNTAIN SILENCE?', 'Dubai desert luxury resort|Dubai desert resort architecture|Swiss luxury alpine chalet|Swiss mountain resort infinity pool|desert villa sunset|Swiss chalet panoramic mountain view|luxury travel landscape', '#LuxuryTravel #Switzerland #Dubai #Shorts'),
        ('japan service robots vs luxury hospitality', 'Japan Service Robots vs Five-Star Hospitality', 'WHO WILL WELCOME YOU IN THE FUTURE?', 'Japan service robot in hotel|Japanese robotics service robot|luxury hotel concierge desk|modern hotel lobby|robot assistant public space Japan|five star hospitality interior|future hospitality technology', '#JapanTech #Hospitality #Shorts'),
    ]
    previous = {str(e.get('topic', '')).strip().lower() for e in state.get('entries', [])}
    previous.update(str(e.get('title', '')).strip().lower() for e in state.get('entries', []))
    # Pick the first unused angle in a deterministic rotation, so retries remain predictable.
    seed = today.date().toordinal()
    try:
        seed += int(os.environ.get('GITHUB_RUN_NUMBER', '0')) * 7
    except ValueError:
        pass
    start = seed % len(ideas)
    chosen = None
    for off in range(len(ideas)):
        candidate = ideas[(start + off) % len(ideas)]
        if candidate[0].lower() not in previous and candidate[1].lower() not in previous:
            chosen = candidate
            break
    if chosen is None:
        raise Fatal('All built-in luxury topics have already been used. Add fresh topics to stock_only_topic().')
    topic, title, hook, queries, hashtags = chosen
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
    # A previous dry/build-only run must not block a real upload. Only an already-uploaded
    # video blocks another public/private upload; dry mode may skip an existing built video.
    done = [e for e in state['entries'] if e.get('date') == day and (
        e.get('status', '').startswith('uploaded') or
        (a.mode == 'dry' and e.get('status', '') == 'built')
    )]
    if done and not a.force:
        log(f'Already made today\'s video ({done[0]["title"]}). Skipping.')
        return 0

    mode, theme = THEMES[a.weekday if a.weekday is not None else now.weekday()]
    log(f'Mode={a.mode}  stock-only theme: {theme}')
    try:
        t = stock_only_topic(now, theme, state)
        log('Gemini disabled: selecting an unused luxury angle from the stock-only topic library; photos from Wikimedia Commons.')
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
