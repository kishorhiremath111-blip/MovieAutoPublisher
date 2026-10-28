#!/usr/bin/env python3
"""gemini_check.py - tells you EXACTLY why Gemini fails (stdlib only, prints no secrets).

Tests, with tiny requests: your key, which text models work, whether Google Search grounding
works, and whether image generation works. Costs a few paise at most.
Env: GEMINI_API_KEY (required); PEXELS_API_KEY (optional, real photos); optional GEMINI_TEXT_MODEL, GEMINI_IMAGE_MODEL, GEMINI_IMAGE_SIZE.
"""
import base64
import json
import os
import struct
import sys
import urllib.error
import urllib.request

API = 'https://generativelanguage.googleapis.com/v1beta'
KEY = os.environ.get('GEMINI_API_KEY', '').strip()
TEXT = [m for m in [os.environ.get('GEMINI_TEXT_MODEL', '').strip(), 'gemini-3.8-flash',
                    'gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.1-flash-lite',
                    'gemini-3.5-flash-lite'] if m]
IMAGE = [m for m in [os.environ.get('GEMINI_IMAGE_MODEL', '').strip(), 'gemini-3.1-flash-image',
                     'gemini-3.1-flash-image-preview', 'gemini-3.1-flash-lite-image',
                     'gemini-2.5-flash-image'] if m]
HINT = {
    429: 'QUOTA/RATE LIMIT. Free-tier limit reached, or billing is off for this feature '
         '(search grounding and image generation are often paid). Open https://ai.dev/rate-limit, '
         'check the project of this key, enable billing, or wait for the daily reset.',
    403: 'KEY NOT ALLOWED. Key restricted, API not enabled for its project, or billing required.',
    401: 'KEY INVALID. Make a new key in Google AI Studio and update the GEMINI_API_KEY secret.',
    404: 'MODEL NOT FOUND for this key. Use another model name.',
    400: 'BAD REQUEST. Usually the model does not support this feature (tool or image size).',
}


def call(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'x-goog-api-key': KEY}
    if data:
        headers['Content-Type'] = 'application/json'
    try:
        req = urllib.request.Request(url, data, headers)
        with urllib.request.urlopen(req, timeout=180) as r:
            return 200, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read() or b'{}').get('error', {})
        except ValueError:
            err = {}
        msg = ' '.join(str(err.get('message', '')).split())[:260]
        return e.code, {'status': err.get('status', ''), 'message': msg}
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, {'message': f'network error: {type(e).__name__}'}


def explain(code, info):
    return f'HTTP {code} {info.get("status", "")} | {info.get("message", "")}\n      -> {HINT.get(code, "see message above")}'


def png_size(raw):
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', raw[16:24])
    return None


def main():
    if not KEY:
        print('FAIL: GEMINI_API_KEY secret is EMPTY or missing in this repository.')
        return 1
    print('Key present: yes (value hidden)')
    code, data = call(f'{API}/models?pageSize=200')
    if code != 200:
        print('FAIL: cannot list models ->', explain(code, data))
        return 1
    names = {m['name'].split('/')[-1] for m in data.get('models', [])}
    print(f'Key works. Models visible: {len(names)}')
    shown = sorted(n for n in names if any(x in n for x in ('flash', 'pro', 'argon', 'image')))
    print('  relevant models:', ', '.join(shown)[:700])

    text_ok = search_ok = None
    for m in TEXT:
        if m not in names:
            print(f'[text] {m}: not available for this key')
            continue
        body = {'contents': [{'parts': [{'text': 'Reply with the single word OK.'}]}]}
        code, d = call(f'{API}/models/{m}:generateContent', body)
        if code != 200:
            print(f'[text] {m}: FAIL {explain(code, d)}')
            continue
        print(f'[text] {m}: works')
        text_ok = text_ok or m
        sbody = {'contents': [{'parts': [{'text': 'In one sentence: one luxury car news item from this week.'}]}],
                 'tools': [{'google_search': {}}]}
        code, d = call(f'{API}/models/{m}:generateContent', sbody)
        if code != 200:
            print(f'[search] {m}: FAIL {explain(code, d)}')
        else:
            chunks = ((d.get('candidates') or [{}])[0].get('groundingMetadata') or {}).get('groundingChunks', [])
            if chunks:
                print(f'[search] {m}: works ({len(chunks)} sources)')
                search_ok = search_ok or m
            else:
                print(f'[search] {m}: answered but returned NO sources (news mode would be rejected)')
        if text_ok and search_ok:
            break

    image_ok = None
    size = os.environ.get('GEMINI_IMAGE_SIZE', '').strip() or '1K'
    for m in IMAGE:
        if m not in names:
            print(f'[image] {m}: not available for this key')
            continue
        cfg = {'responseModalities': ['TEXT', 'IMAGE'], 'imageConfig': {'aspectRatio': '9:16', 'imageSize': size}}
        body = {'contents': [{'parts': [{'text': 'Photo of one gold coin on black velvet, no text.'}]}],
                'generationConfig': cfg}
        code, d = call(f'{API}/models/{m}:generateContent', body)
        if code == 400:
            cfg['imageConfig'].pop('imageSize')
            code, d = call(f'{API}/models/{m}:generateContent', body)
            if code == 200:
                print(f'[image] {m}: imageSize {size} NOT accepted; works without it (smaller images)')
        if code != 200:
            print(f'[image] {m}: FAIL {explain(code, d)}')
            continue
        raw = None
        for p in ((d.get('candidates') or [{}])[0].get('content') or {}).get('parts', []):
            if 'inlineData' in p:
                raw = base64.b64decode(p['inlineData']['data'])
        if not raw:
            print(f'[image] {m}: answered but returned NO image')
            continue
        dims = png_size(raw)
        print(f'[image] {m}: works, {len(raw) // 1024} KB' + (f', {dims[0]}x{dims[1]} px' if dims else ''))
        image_ok = m
        break

    pex = os.environ.get('PEXELS_API_KEY', '').strip()
    pex_ok = None
    if pex:
        try:
            req = urllib.request.Request('https://api.pexels.com/v1/search?query=dubai+skyline&orientation=portrait&per_page=3',
                                         headers={'Authorization': pex, 'User-Agent': 'LuxuryShorts/1.0'})
            with urllib.request.urlopen(req, timeout=60) as r:
                photos = json.loads(r.read()).get('photos', [])
            pex_ok = bool(photos)
            print(f'[pexels] works: {len(photos)} photos, first is {photos[0]["width"]}x{photos[0]["height"]}' if photos
                  else '[pexels] key works but returned no photos')
        except urllib.error.HTTPError as e:
            print(f'[pexels] FAIL HTTP {e.code} (key wrong or rate limit)')
        except (urllib.error.URLError, TimeoutError):
            print('[pexels] FAIL network error')
    else:
        print('[pexels] PEXELS_API_KEY not set (real stock photos off)')

    print('\n=== SUMMARY ===')
    print('text model   :', text_ok or 'NONE WORKS')
    print('google search:', search_ok or 'NOT WORKING (news days will fail)')
    print('image model  :', image_ok or 'NONE WORKS (ok if you use real stock photos)')
    print('real photos  :', 'Pexels works' if pex_ok else ('Pexels NOT working' if pex else 'not configured'))
    if text_ok and image_ok:
        print('Set variables if you want: GEMINI_TEXT_MODEL=%s  GEMINI_IMAGE_MODEL=%s' % (search_ok or text_ok, image_ok))
    return 0 if (text_ok and search_ok and (image_ok or pex_ok)) else 1


if __name__ == '__main__':
    sys.exit(main())
