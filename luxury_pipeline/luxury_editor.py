#!/usr/bin/env python3
"""luxury_editor.py - luxury-lifestyle Shorts editor (images -> 9:16 video + music).

What it does
  * Image 1 carries the ONE hook text. No other text anywhere in the video.
  * Scene types: "full" (one image) and "stack" (two images, top + bottom).
  * Smooth cross-transitions, slow zoom/pan on every image, light cinematic grade.
  * Music: your own file, or an original synthesized cinematic score (no rights issue).
  * Output: 2160x3840 (4K) or 1080x1920, H.264 + AAC, loudness-normalized.

Usage
  python luxury_editor.py --init                  # writes sample_project.json
  python luxury_editor.py project.json -o short.mp4 [--res 4k|1080] [--music file.mp3]

Project file (paths are relative to the project file):
  {"hook": "A NEW GIANT RISES OVER DUBAI", "music": "auto",
   "scenes": [
     {"type": "full",  "image": "hook.jpg", "seconds": 4.5},
     {"type": "stack", "top": "owner.jpg", "bottom": "tower.jpg", "seconds": 5},
     {"type": "full",  "prompt": "Burj Khalifa at golden hour", "seconds": 4}]}
A scene may use "search" (real stock photo, uses Wikimedia Commons (no API key required)) or "prompt" (or "top_prompt"/"bottom_prompt") instead of a file: the image is
then generated with Gemini (needs GEMINI_API_KEY). Real people: use a licensed photo you
supply; never generate a real person's face and present it as real.
Hook text: Latin letters only (English / Roman Hinglish).
"""
import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FPS, SR = 30, 48000
W, H = 2160, 3840
MUSIC_STYLE = 'modern'
IMAGE_SOURCE = 'stock'         # stock-only: never use Gemini-generated images
CREDITS = {'stock': [], 'ai_count': 0}
USED_FILE = Path(__file__).resolve().parent / 'state' / 'used_images.json'
UA = 'LuxuryShorts/1.0'
GOLD = (232, 194, 90, 255)
TRANSITIONS = ['fade', 'smoothup', 'dissolve', 'smoothleft', 'zoomin', 'fadeblack']
MOTIONS = ['in', 'out', 'panr', 'panl']
FONTS = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
         '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf', '/system/fonts/Roboto-Bold.ttf',
         '/system/fonts/DroidSans-Bold.ttf', '/Library/Fonts/Arial Bold.ttf',
         'C:/Windows/Fonts/arialbd.ttf']
STYLE = ('Photorealistic, shot on a full-frame camera, 35mm lens, dramatic cinematic lighting, '
         'dark moody luxury look, natural textures, sharp focus, high dynamic range, looks like '
         'a real photograph, not an illustration. No text, no letters, no watermark, no logos, '
         'no real person\'s face.')
SAMPLE = {
    'hook': 'A NEW GIANT RISES OVER DUBAI', 'music': 'auto',
    'scenes': [
        {'type': 'full', 'image': 'hook.jpg', 'seconds': 4.5},
        {'type': 'stack', 'top': 'owner.jpg', 'bottom': 'tower1.jpg', 'seconds': 5},
        {'type': 'full', 'image': 'tower2.jpg', 'seconds': 4.5},
        {'type': 'stack', 'top': 'tower3.jpg', 'bottom': 'tower4.jpg', 'seconds': 5},
        {'type': 'full', 'prompt': 'Burj Khalifa at golden hour, aerial', 'seconds': 4.5}]}


def die(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    sys.exit(1)


def set_res(res):
    global W, H
    W, H = {'4k': (2160, 3840), '1080': (1080, 1920)}[res]


# ---------------- images ----------------
def prepare_tile(src, dst, w, h):
    im = ImageOps.exif_transpose(Image.open(src)).convert('RGB')
    scale = max(w / im.width, h / im.height)
    if scale > 1.05:
        print(f'  note: {Path(src).name} is {im.width}x{im.height}, upscaled x{scale:.1f} '
              f'(sharper source = sharper video)')
    im = ImageOps.fit(im, (w, h), Image.LANCZOS)
    if scale > 1.2:
        im = im.filter(ImageFilter.UnsharpMask(radius=2.0, percent=65, threshold=3))
    im.save(dst, 'PNG')


def load_font(size, custom):
    for p in ([custom] if custom else []) + FONTS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    die('No bold font found. Pass --font /path/to/Bold.ttf')


def make_hook_png(text, dst, font_path, y_frac=0.40):
    k = W / 2160
    text = ' '.join(text.upper().split())
    if not text:
        die('Hook text is empty.')
    probe = ImageDraw.Draw(Image.new('RGBA', (8, 8)))
    max_w, size = int(W * 0.84), int(190 * k)
    while size >= int(90 * k):
        font = load_font(size, font_path)
        lines, cur = [], ''
        for word in text.split():
            trial = f'{cur} {word}'.strip()
            if probe.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                lines.append(cur) if cur else None
                cur = word
        lines.append(cur)
        if len(lines) <= 5 and all(probe.textlength(l, font=font) <= max_w for l in lines):
            break
        size -= int(10 * k)
    else:
        die('Hook is too long. Use about 12 words or fewer.')
    stroke, line_h = max(3, size // 28), int(size * 1.22)
    block = line_h * len(lines)
    top = int(H * y_frac) - block // 2
    pad = int(260 * k)
    b0, b1 = max(0, top - pad), min(H, top + block + pad)
    col = Image.new('L', (1, H), 0)
    for y in range(b0, b1):
        t = (y - b0) / (b1 - b0)
        col.putpixel((0, y), int(175 * min(1.0, min(t, 1 - t) * 2 * 2.2)))
    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ov.putalpha(col.resize((W, H)))
    d = ImageDraw.Draw(ov)
    for i, line in enumerate(lines):
        d.text(((W - d.textlength(line, font=font)) / 2, top + i * line_h), line, font=font,
               fill=GOLD, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    ov.save(dst, 'PNG')
    return lines


def gemini_key():
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        die('GEMINI_API_KEY is not set. Put it in an environment variable or a GitHub '
            'secret. Never paste it in chat or in code.')
    return key


def check_gemini():
    """Lists the image models this API key can really use (nothing is generated)."""
    req = urllib.request.Request(
        'https://generativelanguage.googleapis.com/v1beta/models?pageSize=200',
        headers={'x-goog-api-key': gemini_key()})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            models = json.loads(r.read()).get('models', [])
    except urllib.error.HTTPError as e:
        die(f'Gemini rejected the key (HTTP {e.code}). Check the key in Google AI Studio.')
    names = [m['name'].split('/')[-1] for m in models
             if 'image' in m['name'] and 'generateContent' in m.get('supportedGenerationMethods', [])]
    if not names:
        die('This key has no image-generation model available.')
    print('Image models available for your key:')
    for n in names:
        print('  ', n)
    print('Set one with:  export GEMINI_IMAGE_MODEL=<name>')


IMAGE_MODELS = ['gemini-3.1-flash-image', 'gemini-3.1-flash-image-preview',
                'gemini-3.1-flash-lite-image', 'gemini-2.5-flash-image']
_IMG = {'model': None}


def gen_image(prompt, dst, ratio):
    key = gemini_key()
    env_model = os.environ.get('GEMINI_IMAGE_MODEL')
    models = [env_model] if env_model else ([_IMG['model']] if _IMG['model'] else IMAGE_MODELS)
    data, missing, quota_hits = None, 0, 0
    for model in models:
        size = os.environ.get('GEMINI_IMAGE_SIZE') or ('4K' if model.startswith('gemini-3') else '')
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
        for attempt in range(4):
            cfg = {'responseModalities': ['TEXT', 'IMAGE'], 'imageConfig': {'aspectRatio': ratio}}
            if size:
                cfg['imageConfig']['imageSize'] = size
            body = json.dumps({'contents': [{'parts': [{'text': f'{prompt}. {STYLE}'}]}],
                               'generationConfig': cfg}).encode()
            try:
                req = urllib.request.Request(url, body, {'Content-Type': 'application/json',
                                                         'x-goog-api-key': key})
                with urllib.request.urlopen(req, timeout=240) as r:
                    data = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    print(f'  note: image model "{model}" not available, trying the next one')
                    missing += 1
                    break
                if e.code == 400 and size:
                    print(f'  note: "{model}" refused imageSize {size}; retrying without it '
                          f'(image will be smaller)')
                    size = ''
                    continue
                try:
                    j = json.loads(e.read() or b'{}').get('error', {})
                    detail = ' '.join(str(j.get('message', '')).split())[:300]
                except Exception:
                    detail = ''
                if e.code == 429:
                    print(f'  note: image model "{model}" quota is used up ({detail[:90]}); trying the next one')
                    quota_hits += 1
                    break
                if e.code in (400, 401, 403):
                    die(f'Gemini image API rejected the request (HTTP {e.code}) on "{model}": '
                        f'{detail}. Run the "Gemini check" workflow / --check-gemini.')
                time.sleep(2 ** attempt)
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** attempt)
        if data:
            if _IMG['model'] != model:
                print(f'  using image model: {model}')
            _IMG['model'] = model
            break
    if not data and quota_hits:
        die(f'Gemini image QUOTA/BILLING limit (HTTP 429) on {quota_hits} model(s). Image generation often '
            f'needs billing. Use real photos instead: set PEXELS_API_KEY and IMAGE_SOURCE=stock. '
            f'Limits: https://ai.dev/rate-limit')
    if not data and missing:
        die('None of the image models exist for this key: ' + ', '.join(models) +
            '. Run --check-gemini and set GEMINI_IMAGE_MODEL.')
    for part in ((data or {}).get('candidates') or [{}])[0].get('content', {}).get('parts', []):
        if 'inlineData' in part:
            Path(dst).write_bytes(base64.b64decode(part['inlineData']['data']))
            return
    die(f'No image returned for prompt "{prompt[:50]}". Nothing was faked.')



# ---------------- real photos (Pexels, free licence) ----------------
def load_used():
    try:
        return set(json.loads(USED_FILE.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return set()


def save_used(ids):
    try:
        USED_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = USED_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(sorted(ids)[-3000:]), encoding='utf-8')
        tmp.replace(USED_FILE)
    except OSError:
        pass


def commons_get(url, raw=False):
    """Query/download licensed Commons media with conservative rate-limit retries."""
    for attempt in range(5):
        try:
            headers = {'User-Agent': UA + ' (licensed stock-photo video pipeline)'}
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                body = r.read()
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as ex:
            if ex.code in (401, 403):
                die('Wikimedia Commons denied the request (HTTP %d). Check API access.' % ex.code)
            if ex.code == 429:
                retry_after = ex.headers.get('Retry-After', '')
                try:
                    wait = max(5, min(45, int(retry_after)))
                except (TypeError, ValueError):
                    wait = min(30, 5 * (attempt + 1))
                print(f'  Wikimedia Commons rate-limited this request; waiting {wait}s (retry {attempt + 1}/5).')
                if attempt == 4:
                    print('  Commons rate limit persisted after retries; this photo candidate is skipped.')
                    return None
                time.sleep(wait)
                continue
            if ex.code < 500 or attempt == 4:
                print(f'  Commons request failed with HTTP {ex.code}; skipping this candidate.')
                return None
        except (urllib.error.URLError, TimeoutError) as ex:
            if attempt == 4:
                print(f'  Commons network request failed ({type(ex).__name__}); skipping this candidate.')
                return None
        time.sleep(min(16, 2 ** attempt))
    return None


def fetch_stock(query, dst, w, h):
    """Download a fresh, freely licensed raster photo from Wikimedia Commons.

    Search the exact scene first, then broaden the query so one sparse search
    result does not fail the entire video build.
    """
    target = w / h
    big = W > 1080
    used = load_used()

    # Keep the exact visual intent first; use broader, related searches only
    # when Commons has no suitable unused result for the original phrase.
    queries = [query]
    qlow = query.lower()
    fallback_map = {
        'luxury bedroom design': ['modern bedroom interior', 'luxury home interior', 'bedroom interior design'],
        'luxury mansion exterior': ['modern mansion house', 'luxury house architecture', 'modern villa exterior'],
        'modern mansion living room': ['modern luxury living room', 'designer living room interior', 'modern home interior'],
        'luxury staircase interior': ['modern staircase architecture', 'luxury home staircase', 'interior staircase design'],
        'marble mansion interior': ['marble interior architecture', 'luxury interior design', 'modern house interior'],
        'infinity pool mansion': ['luxury infinity pool house', 'modern villa swimming pool', 'luxury resort pool'],
        'premium hotel lobby': ['luxury hotel interior', 'modern hotel lobby', 'designer hotel interior'],
    }
    queries.extend(fallback_map.get(qlow, []))
    # Do not substitute unrelated generic architecture photos for a specific scene.
    # If the exact scene has no fresh unused licensed photo, fail clearly instead of padding with mismatches.

    seen_ids = set()
    for search_query in queries:
        params = {
            'action': 'query', 'generator': 'search',
            'gsrsearch': 'filetype:bitmap ' + search_query,
            'gsrnamespace': 6, 'gsrlimit': 20, 'gsrwhat': 'text',
            'prop': 'imageinfo', 'iiprop': 'url|size|mime|extmetadata',
            'iiurlwidth': 2400 if big else 1500, 'format': 'json'
        }
        url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(params)
        data = commons_get(url) or {}
        pages = list((data.get('query') or {}).get('pages', {}).values())
        candidates = []
        for page in pages:
            info = (page.get('imageinfo') or [{}])[0]
            mime = info.get('mime', '')
            if mime not in ('image/jpeg', 'image/png', 'image/webp', 'image/tiff'):
                continue
            ident = str(page.get('pageid') or page.get('title') or '')
            if not ident or ident in used or ident in seen_ids:
                continue
            seen_ids.add(ident)
            if (info.get('width', 0) or 0) < 900 or (info.get('height', 0) or 0) < 600:
                continue
            ratio = info.get('width', 1) / max(info.get('height', 1), 1)
            asp = abs(math.log(max(ratio, 0.01) / target))
            short = min(info.get('width', 0) / w, info.get('height', 0) / h)
            candidates.append((short < (1.0 if big else 0.8), round(asp, 2),
                               -(info.get('width', 0) * info.get('height', 0)),
                               ident, page, info))
        for _, _, _, ident, page, info in sorted(candidates)[:8]:
            meta = info.get('extmetadata') or {}
            def meta_value(k):
                return str((meta.get(k) or {}).get('value', '')).strip()
            license_name = meta_value('LicenseShortName')
            license_url = meta_value('LicenseUrl')
            artist = meta_value('Artist') or meta_value('Credit') or 'Unknown author'
            artist = re.sub(r'<[^>]+>', '', artist).strip()
            if not license_name or not license_url:
                continue
            download_url = info.get('thumburl') or info.get('url')
            if not download_url:
                continue
            raw = commons_get(download_url, raw=True)
            try:
                Image.open(__import__('io').BytesIO(raw or b'')).verify()
            except Exception:
                continue
            Path(dst).write_bytes(raw)
            used.add(ident)
            save_used(used)
            page_url = 'https://commons.wikimedia.org/wiki/' + urllib.parse.quote(page.get('title', '').replace(' ', '_'))
            CREDITS['stock'].append({
                'id': ident, 'url': page_url, 'photographer': artist,
                'credit': f'Photo: {artist}; source: Wikimedia Commons; license: {license_name} ({license_url})'
            })
            print(f'  licensed photo: "{search_query}" -> Wikimedia Commons ({license_name})')
            if search_query != query:
                print(f'  fallback search used for scene "{query}"')
            return True
    print(f'  no suitable unused freely licensed Commons photo found for "{query}" after {len(queries)} searches')
    return False

def get_tile(s, key, typ, dst, w, h, n):
    sk = 'search' if key == 'image' else f'{key}_search'
    pk = 'prompt' if key == 'image' else f'{key}_prompt'
    order = {'stock': ['stock'], 'gemini': ['gemini'], 'auto': ['stock', 'gemini']}[IMAGE_SOURCE]
    why = []
    for src in order:
        if src == 'stock':
            if not s.get(sk):
                why.append(f'no "{sk}" given')
            elif fetch_stock(s[sk], dst, w, h):
                return
            else:
                why.append(f'no unused photo found for "{s[sk]}"')
        else:
            if not s.get(pk):
                why.append(f'no "{pk}" given')
            elif not os.environ.get('GEMINI_API_KEY', '').strip():
                why.append('GEMINI_API_KEY missing')
            else:
                print(f'  generating {key} for scene {n} with AI...')
                gen_image(s[pk], dst, '9:16' if typ == 'full' else '1:1')
                CREDITS['ai_count'] += 1
                return
    die(f'Scene {n} ({key}): no image could be made. Mode "{IMAGE_SOURCE}": ' + '; '.join(why))


# ---------------- music ----------------
def synth_score(total, hits, path):
    """Original cinematic score: evolving pad, sub, soft downbeats, plucks, risers + impacts."""
    n = int(total * SR)
    t = np.arange(n) / SR
    L, R = np.zeros(n), np.zeros(n)
    rng = np.random.default_rng(11)
    mtof = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    bpm = 84
    beat = 60 / bpm
    chord_len = 8 * beat
    chords = [(57, 60, 64), (53, 57, 60), (60, 64, 67), (55, 59, 62)]
    k = 0
    while k * chord_len < total:
        s0 = k * chord_len
        a, b = int(s0 * SR), min(n, int((s0 + chord_len + 1.5) * SR))
        tt = t[a:b]
        ramp = np.minimum(1.0, np.minimum((tt - s0) / 1.4, (s0 + chord_len + 1.5 - tt) / 1.4))
        w = np.sin(np.clip(ramp, 0, 1) * np.pi / 2) ** 2
        chord = chords[k % 4]
        for note in chord + (chord[0] - 12,):
            f = mtof(note)
            for h in range(1, 6):
                amp = 0.11 / h ** 1.3
                L[a:b] += w * amp * np.sin(2 * np.pi * f * 1.0012 * h * tt)
                R[a:b] += w * amp * np.sin(2 * np.pi * f * 0.9988 * h * tt + 0.7)
        sub = w * 0.30 * np.sin(2 * np.pi * mtof(chord[0] - 24) * tt)
        L[a:b] += sub
        R[a:b] += sub
        # soft plucked arpeggio
        for j in range(16):
            ts = s0 + j * beat / 2
            if ts >= total:
                break
            note = chord[[0, 1, 2, 1][j % 4]] + 12
            i0 = int(ts * SR)
            i1 = min(n, i0 + int(0.9 * SR))
            tp = np.arange(i1 - i0) / SR
            env = np.minimum(1, tp / 0.006) * np.exp(-tp * 4.5)
            tone = env * 0.05 * (np.sin(2 * np.pi * mtof(note) * tp) +
                                 0.4 * np.sin(2 * np.pi * mtof(note) * 2 * tp))
            L[i0:i1] += tone * (0.7 + 0.3 * (j % 2))
            R[i0:i1] += tone * (1.0 - 0.3 * (j % 2))
        k += 1

    def boom(at, gain):
        i0 = int(at * SR)
        if i0 >= n:
            return
        i1 = min(n, i0 + int(1.6 * SR))
        tp = np.arange(i1 - i0) / SR
        phase = 2 * np.pi * (38 * tp + 55 * (1 - np.exp(-14 * tp)) / 14)
        sig = np.sin(phase) * np.exp(-tp * 3.2) * gain
        sig += rng.standard_normal(i1 - i0) * np.exp(-tp * 18) * gain * 0.25
        L[i0:i1] += sig
        R[i0:i1] += sig

    def riser(end, dur=1.3):
        i0, i1 = max(0, int((end - dur) * SR)), min(n, int(end * SR))
        if i1 - i0 < 10:
            return
        tp = np.arange(i1 - i0) / SR
        env = (tp / max(tp[-1], 1e-6)) ** 2.2
        for ch in (L, R):
            noise = np.convolve(rng.standard_normal(i1 - i0), np.ones(6) / 6, 'same')
            sweep = np.sin(2 * np.pi * (220 * tp + 380 * tp ** 2))
            ch[i0:i1] += env * (0.16 * noise + 0.06 * sweep)

    # hook impact: a hit with a long tail on the very first frame
    boom(0.05, 0.55)
    for h in hits:
        riser(h)
        boom(h, 0.42)
    beats = np.arange(0, total, 4 * beat)
    for bt in beats:                                    # gentle downbeat pulse
        i0 = int(bt * SR)
        i1 = min(n, i0 + int(0.4 * SR))
        tp = np.arange(i1 - i0) / SR
        ph = 2 * np.pi * (48 * tp + 50 * (1 - np.exp(-22 * tp)) / 22)
        pulse = np.sin(ph) * np.exp(-tp * 8) * 0.16
        L[i0:i1] += pulse
        R[i0:i1] += pulse
    for ch in (L, R):
        ch *= np.minimum(1, t / 0.4) * np.minimum(1, (total - t) / 2.5)
    peak = max(np.abs(L).max(), np.abs(R).max(), 1e-6)
    out = np.tanh(np.stack([L, R], 1) / peak * 1.1) * 0.89
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((out * 32767).astype('<i2').tobytes())



def _put(buf, arr, at, gain=1.0):
    i0 = int(at * SR)
    if 0 <= i0 < len(buf):
        i1 = min(len(buf), i0 + len(arr))
        buf[i0:i1] += arr[:i1 - i0] * gain


def synth_modern(total, hits, path, bpm=108):
    """Original modern-luxury groove: deep-house/lounge drums, rolling bass, soft electric-piano
    stabs, warm pad, sidechain pump, risers + impacts on every transition. Rights-free."""
    n = int(total * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(5)
    beat = 60 / bpm
    mtof = lambda m: 440.0 * 2 ** ((m - 69) / 12)

    def hp_noise(m):
        x = rng.standard_normal(m)
        return x - np.convolve(x, np.ones(10) / 10, 'same')

    tk = np.arange(int(0.5 * SR)) / SR
    kick_s = np.sin(2 * np.pi * (50 * tk + 80 * (1 - np.exp(-28 * tk)) / 28)) * np.exp(-tk * 8.5)
    th = np.arange(int(0.10 * SR)) / SR
    hat_s = hp_noise(len(th)) * np.exp(-th * 70)
    to = np.arange(int(0.30 * SR)) / SR
    ohat_s = hp_noise(len(to)) * np.exp(-to * 16)
    clap_s = hp_noise(len(to)) * (np.exp(-to * 70) + 0.8 * (to > 0.011) * np.exp(-np.maximum(to - 0.011, 0) * 70)
                                  + 0.7 * (to > 0.022) * np.exp(-np.maximum(to - 0.022, 0) * 18))
    gate, drums = np.zeros(n), np.zeros(n)
    start, idx, bt = 2.2, 0, 2.2                     # drums enter after the hook lands
    while bt < total:
        _put(drums, kick_s, bt, 0.75)
        _put(gate, np.exp(-tk[:int(0.3 * SR)] * 7), bt)
        if idx % 4 in (1, 3):
            _put(drums, clap_s, bt, 0.16)
        _put(drums, ohat_s, bt + beat / 2, 0.07)
        _put(drums, hat_s, bt + beat * 0.25, 0.03)
        _put(drums, hat_s, bt + beat * 0.75, 0.03)
        bt += beat
        idx += 1
    gate = np.clip(gate, 0, 1)

    L, R = np.zeros(n), np.zeros(n)
    chords = [(57, 60, 64, 67), (53, 57, 60, 64), (60, 64, 67, 71), (55, 59, 62, 65)]
    bar = 4 * beat
    chord_len = 2 * bar
    k = 0
    while k * chord_len < total:
        s0 = k * chord_len
        chord = chords[k % 4]
        a, b = int(s0 * SR), min(n, int((s0 + chord_len + 1.0) * SR))
        tt = t[a:b]
        w = np.sin(np.clip(np.minimum((tt - s0) / 1.0, (s0 + chord_len + 1.0 - tt) / 1.0), 0, 1)
                   * np.pi / 2) ** 2
        for note in chord:
            f = mtof(note)
            for h in (1, 2, 3):
                L[a:b] += w * (0.05 / h) * np.sin(2 * np.pi * f * 1.002 * h * tt)
                R[a:b] += w * (0.05 / h) * np.sin(2 * np.pi * f * 0.998 * h * tt + 0.5)
        for bar_i in range(2):
            b0 = s0 + bar_i * bar
            tp = np.arange(int(0.7 * SR)) / SR
            env = np.minimum(1, tp / 0.004) * np.exp(-tp * 5.5)
            tone = sum(np.sin(2 * np.pi * mtof(m + 12) * tp) +
                       0.45 * np.sin(2 * np.pi * mtof(m + 12) * 2 * tp) * np.exp(-tp * 8)
                       for m in chord) * env * 0.028
            for off, pan in ((0.5, 0.7), (2.0, 1.0), (3.5, 0.5)):
                _put(L, tone, b0 + off * beat, pan)
                _put(R, tone, b0 + off * beat, 1.2 - pan)
            tb = np.arange(int(0.4 * SR)) / SR
            f = mtof(chord[0] - 24)
            bass = (np.sin(2 * np.pi * f * tb) + 0.35 * np.sin(2 * np.pi * f * 2 * tb)) \
                * np.minimum(1, tb / 0.005) * np.exp(-tb * 4.5) * 0.30
            for off in (0.0, 0.75, 1.5, 2.5, 3.25):
                if b0 + off * beat >= start:
                    _put(L, bass, b0 + off * beat)
                    _put(R, bass, b0 + off * beat)
        k += 1
    duck = 1 - 0.55 * gate                            # sidechain pump
    L *= duck
    R *= duck
    L += drums
    R += drums

    def boom(at, gain):
        i0 = int(at * SR)
        if i0 >= n:
            return
        tp = np.arange(min(n, i0 + int(1.6 * SR)) - i0) / SR
        sig = np.sin(2 * np.pi * (38 * tp + 55 * (1 - np.exp(-14 * tp)) / 14)) * np.exp(-tp * 3.2) * gain
        sig += rng.standard_normal(len(tp)) * np.exp(-tp * 18) * gain * 0.25
        L[i0:i0 + len(tp)] += sig
        R[i0:i0 + len(tp)] += sig

    def riser(end, dur=1.3):
        i0, i1 = max(0, int((end - dur) * SR)), min(n, int(end * SR))
        if i1 - i0 < 10:
            return
        tp = np.arange(i1 - i0) / SR
        env = (tp / max(tp[-1], 1e-6)) ** 2.2
        for ch in (L, R):
            noise = np.convolve(rng.standard_normal(i1 - i0), np.ones(6) / 6, 'same')
            ch[i0:i1] += env * (0.14 * noise + 0.05 * np.sin(2 * np.pi * (220 * tp + 380 * tp ** 2)))

    boom(0.05, 0.55)
    for h in hits:
        riser(h)
        boom(h, 0.40)
    for ch in (L, R):
        ch *= np.minimum(1, t / 0.3) * np.minimum(1, (total - t) / 2.5)
    peak = max(np.abs(L).max(), np.abs(R).max(), 1e-6)
    out = np.tanh(np.stack([L, R], 1) / peak * 1.15) * 0.89
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((out * 32767).astype('<i2').tobytes())


def make_music(total, hits, path):
    (synth_modern if MUSIC_STYLE == 'modern' else synth_score)(total, hits, path)


# ---------------- video ----------------
def motion(kind, n):
    c = ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)")
    return {'in': (f'1+0.08*on/{n}',) + c, 'out': (f'1.08-0.08*on/{n}',) + c,
            'panr': ('1.1', f'(iw-iw/zoom)*(0.15+0.7*on/{n})', c[1]),
            'panl': ('1.1', f'(iw-iw/zoom)*(0.85-0.7*on/{n})', c[1])}[kind]


def zp(idx, kind, n, w, h):
    z, x, y = motion(kind, n)
    return f"[{idx}:v]zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={FPS},setsar=1"


def render(scenes, hook_png, music, out, fade, crf, preset, grade):
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    idx, parts, lens = 0, [], []
    for i, sc in enumerate(scenes):
        n = round(sc['seconds'] * FPS)
        lens.append(sc['seconds'])
        for p in sc['tiles']:
            cmd += ['-i', str(p)]
        if sc['type'] == 'full':
            parts.append(f"{zp(idx, MOTIONS[i % 4], n, W, H)},format=yuv420p[s{i}]")
            idx += 1
        else:
            half, seam = H // 2, max(3, round(6 * W / 2160))
            parts.append(f"{zp(idx, MOTIONS[i % 4], n, W, half)}[a{i}]")
            parts.append(f"{zp(idx + 1, MOTIONS[(i + 2) % 4], n, W, half)}[b{i}]")
            parts.append(f"[a{i}][b{i}]vstack=inputs=2,drawbox=x=0:y={half - seam // 2}:w={W}"
                         f":h={seam}:color=0xE8C25A@0.85:t=fill,format=yuv420p[s{i}]")
            idx += 2
    cmd += ['-loop', '1', '-framerate', str(FPS), '-t', f'{lens[0]}', '-i', str(hook_png)]
    hk = idx
    idx += 1
    parts.append(f'[{hk}:v]format=rgba,fade=t=in:st=0.35:d=0.7:alpha=1[hk]')
    parts.append('[s0][hk]overlay=0:0:format=auto,format=yuv420p[c0]')
    hits, acc = [], lens[0]
    for i in range(1, len(scenes)):
        off = acc - i * fade
        hits.append(off + fade / 2)
        tr = TRANSITIONS[(i - 1) % len(TRANSITIONS)]
        parts.append(f'[c{i - 1}][s{i}]xfade=transition={tr}:duration={fade}:offset={off:.3f}[c{i}]')
        acc += lens[i]
    total = acc - (len(scenes) - 1) * fade
    last = f'c{len(scenes) - 1}'
    if grade:
        parts.append(f'[{last}]eq=contrast=1.05:saturation=1.10:gamma=0.98,vignette=PI/7[vout]')
    else:
        parts.append(f'[{last}]null[vout]')
    if music == 'auto':
        wav = Path(out).with_suffix('.score.wav')
        make_music(total, hits, wav)
        cmd += ['-i', str(wav)]
    elif music:
        cmd += ['-stream_loop', '-1', '-i', str(music)]
    if music:
        parts.append(f'[{idx}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.4,'
                     f'afade=t=out:st={total - 2:.3f}:d=2,loudnorm=I=-16:TP=-1.5:LRA=11,'
                     f'aresample={SR}[aout]')
    cmd += ['-filter_complex', ';'.join(parts), '-map', '[vout]']
    cmd += ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k'] if music else ['-an']
    cmd += ['-t', f'{total:.3f}', '-c:v', 'libx264', '-preset', preset, '-crf', str(crf),
            '-profile:v', 'high', '-level', '5.1' if W > 1080 else '4.2', '-pix_fmt', 'yuv420p',
            '-r', str(FPS), '-movflags', '+faststart', str(out)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if music == 'auto':
        wav.unlink(missing_ok=True)
    if res.returncode:
        die('ffmpeg failed:\n' + res.stderr[-1800:])
    return total


def verify(out, want_audio):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'stream=codec_type,width,height:format=duration', '-of', 'json',
                        str(out)], capture_output=True, text=True)
    info = json.loads(r.stdout or '{}')
    vs = [s for s in info.get('streams', []) if s['codec_type'] == 'video']
    has_a = any(s['codec_type'] == 'audio' for s in info.get('streams', []))
    if not vs or (vs[0]['width'], vs[0]['height']) != (W, H):
        die(f'Unexpected video size: {vs}')
    if want_audio and not has_a:
        die('Music was requested but the output has no audio.')
    dur = float(info['format']['duration'])
    print(f'OK: {out}  {W}x{H}  {dur:.1f}s  audio={"yes" if has_a else "no"}  '
          f'{Path(out).stat().st_size / 1e6:.1f} MB')
    if dur > 59:
        print('  note: over 59s. Shorts under 60s are safest.')


def main():
    ap = argparse.ArgumentParser(description='Luxury Shorts editor.')
    ap.add_argument('project', nargs='?')
    ap.add_argument('--init', action='store_true', help='write sample_project.json')
    ap.add_argument('--check-gemini', action='store_true', help='list usable image models')
    ap.add_argument('-o', '--out', default='short.mp4')
    ap.add_argument('--res', choices=['4k', '1080'], default='4k')
    ap.add_argument('--music', help='your own licensed music file (overrides project)')
    ap.add_argument('--no-music', action='store_true')
    ap.add_argument('--music-style', choices=['modern', 'cinematic'],
                    help='auto-music style (default modern)')
    ap.add_argument('--fade', type=float, default=0.7, help='transition seconds')
    ap.add_argument('--crf', type=int, default=17)
    ap.add_argument('--preset', default='medium')
    ap.add_argument('--no-grade', action='store_true')
    ap.add_argument('--font')
    a = ap.parse_args()
    if a.init:
        Path('sample_project.json').write_text(json.dumps(SAMPLE, indent=2), encoding='utf-8')
        print('Wrote sample_project.json')
        return
    if a.check_gemini:
        check_gemini()
        return
    if not a.project:
        die('Give a project.json (or use --init).')
    for tool in ('ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            die(f'{tool} not found. Install ffmpeg.')
    set_res(a.res)
    pj = Path(a.project)
    proj = json.loads(pj.read_text(encoding='utf-8'))
    base, scenes_in = pj.parent, proj.get('scenes', [])
    if not 3 <= len(scenes_in) <= 14:
        die('Use 3 to 14 scenes.')
    hook = proj.get('hook', '').strip()
    if not hook:
        die('Project needs a "hook".')
    global MUSIC_STYLE, IMAGE_SOURCE
    IMAGE_SOURCE = 'stock'  # enforced stock-only mode; never call Gemini image generation
    if IMAGE_SOURCE not in ('auto', 'stock', 'gemini'):
        die('IMAGE_SOURCE must be auto, stock or gemini.')
    MUSIC_STYLE = a.music_style or proj.get('music_style', 'modern')
    music = None if a.no_music else (a.music or proj.get('music'))
    if music and music != 'auto':
        music = (base / music) if not Path(music).is_absolute() else Path(music)
        if not Path(music).exists():
            die(f'Music file not found: {music}')

    work = Path(tempfile.mkdtemp(prefix='lux_'))
    try:
        print('Preparing images...')
        scenes = []
        for i, s in enumerate(scenes_in):
            typ = s.get('type', 'full')
            if typ not in ('full', 'stack'):
                die(f'Scene {i + 1}: type must be "full" or "stack".')
            keys = ['image'] if typ == 'full' else ['top', 'bottom']
            tiles = []
            for key in keys:
                tw, th = (W, H) if typ == 'full' else (W, H // 2)
                dst = work / f's{i}_{key}.png'
                if s.get(key):
                    src = base / s[key]
                    if not src.exists():
                        die(f'Scene {i + 1}: image not found: {src}')
                else:
                    src = work / f'src_s{i}_{key}.png'
                    get_tile(s, key, typ, src, tw, th, i + 1)
                prepare_tile(src, dst, tw, th)
                tiles.append(dst)
            scenes.append({'type': typ, 'tiles': tiles,
                           'seconds': max(a.fade + 1.5, float(s.get('seconds', 4.5)))})
        print('Hook:', ' / '.join(make_hook_png(hook, work / 'hook.png', a.font, float(proj.get('hook_y', 0.40)))))
        print(f'Rendering {a.res} (4K takes a while)...')
        render(scenes, work / 'hook.png', music, a.out, a.fade, a.crf, a.preset,
               not a.no_grade)
        verify(a.out, bool(music))
        Path(a.out).with_suffix('.credits.json').write_text(json.dumps(CREDITS), encoding='utf-8')
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
