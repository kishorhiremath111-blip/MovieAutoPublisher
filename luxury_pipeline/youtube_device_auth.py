#!/usr/bin/env python3
"""One-time helper: get a YouTube refresh token on your phone (no browser on the device needed).

1. Google Cloud Console -> create project -> enable "YouTube Data API v3".
2. OAuth consent screen: add yourself as test user, then PUBLISH the app ("In production"),
   otherwise the token stops working after 7 days.
3. Credentials -> Create OAuth client ID -> type "TVs and Limited Input devices".
4. Run this file, paste the client id/secret, open the link, enter the code, approve.
The token is printed ONLY on your screen. Put it in GitHub secret YOUTUBE_REFRESH_TOKEN.
Never paste it in chat or commit it.
Untested here: if Google rejects the scope, use the desktop flow on a laptop instead.
"""
import getpass
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SCOPE = 'https://www.googleapis.com/auth/youtube'


def post(url, data):
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b'{}')


cid = input('Client ID: ').strip()
secret = getpass.getpass('Client secret (hidden): ').strip()
dev = post('https://oauth2.googleapis.com/device/code', {'client_id': cid, 'scope': SCOPE})
if 'device_code' not in dev:
    sys.exit(f'Google refused: {dev.get("error_description") or dev.get("error")}')
print(f'\nOpen: {dev["verification_url"]}\nEnter code: {dev["user_code"]}\n')
deadline = time.time() + dev.get('expires_in', 600)
while time.time() < deadline:
    time.sleep(dev.get('interval', 5))
    tok = post('https://oauth2.googleapis.com/token', {
        'client_id': cid, 'client_secret': secret, 'device_code': dev['device_code'],
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'})
    if 'refresh_token' in tok:
        print('\nYOUTUBE_REFRESH_TOKEN =', tok['refresh_token'])
        print('Save it as a GitHub secret now. Do not share it.')
        break
    if tok.get('error') not in ('authorization_pending', 'slow_down'):
        sys.exit(f'Failed: {tok.get("error_description") or tok.get("error")}')
else:
    sys.exit('Timed out. Run again.')
