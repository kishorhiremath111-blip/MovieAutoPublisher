#!/usr/bin/env python3
"""One-time patcher for MovieAutoPublisher. Safe to run twice (already-applied fixes are skipped).

Fixes:
  1. trend_engine.py       - channel stats HTTP 400 (batch channel ids in groups of 50)
  2. process.py            - caption emoji-strip regex that also deleted capital letters and digits
  3. process.py            - one invalid metadata item no longer aborts the whole daily run
  4. process.py            - Shorts now render with the demo-style layout (demo_style.py)
  5. uploaders/youtube.py  - clear error instead of a 90-minute hang when the OAuth token is dead in CI
  6. uploaders/youtube.py  - retry transient 5xx errors during upload
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
problems = []


def read(rel):
    path = ROOT / rel
    if not path.is_file():
        problems.append(f"missing file: {rel}")
        return None
    return path.read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")


def patch(rel, text, old, new, label, count=1):
    """Replace `old` with `new` exactly `count` times; skip if `new` is already present."""
    if text is None:
        return None
    if new in text:
        print(f"SKIP (already applied): {label}")
        return text
    found = text.count(old)
    if found != count:
        problems.append(f"{label}: expected {count} match(es) in {rel}, found {found}")
        return text
    print(f"OK: {label}")
    return text.replace(old, new)


# ---------------------------------------------------------------- trend_engine.py
NEW_CHANNEL_STATS = '''def channel_stats(api_key, channel_ids):
    """Fetch channel subscriber counts in batches of 50 ids (API limit; more gives HTTP 400)."""
    ids = sorted(str(x) for x in channel_ids if x)
    result = {}
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        url = 'https://www.googleapis.com/youtube/v3/channels?' + urllib.parse.urlencode({
            'part': 'statistics,snippet',
            'id': ','.join(batch),
            'maxResults': 50,
            'key': api_key,
        })
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'MovieAutoPublisher/Trend-Discovery/1.0'}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            print(f'Channel stats batch {start // 50 + 1} failed: {exc}')
            continue
        for item in data.get('items', []):
            result[item['id']] = {
                'title': item.get('snippet', {}).get('title', ''),
                'subscribers': int(item.get('statistics', {}).get('subscriberCount', 0) or 0),
            }
    return result


'''

text = read("trend_engine.py")
if text is not None:
    if "for start in range(0, len(ids), 50)" in text:
        print("SKIP (already applied): trend_engine channel_stats batching")
    else:
        a = text.find("def channel_stats(")
        b = text.find("def normalize(")
        if a == -1 or b == -1 or b < a:
            problems.append("trend_engine.py: could not locate channel_stats()/normalize()")
        else:
            text = text[:a] + NEW_CHANNEL_STATS + text[b:]
            write("trend_engine.py", text)
            print("OK: trend_engine channel_stats batching")

# ---------------------------------------------------------------- process.py
text = read("process.py")
OLD_RE = r'r"[\\U0001F300-\\U0001FAFF\\U00002600-\\U000027BF]"'
NEW_RE = r'"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]"'
text = patch("process.py", text, OLD_RE, NEW_RE, "process.py emoji regex (2 places)", count=2)

OLD_VALIDATE = "        source, thumb = validate_item(item)\n"
NEW_VALIDATE = (
    "        try:\n"
    "            source, thumb = validate_item(item)\n"
    "        except (RuntimeError, FileNotFoundError, KeyError) as exc:\n"
    "            print(f'SKIP {source_id}: {exc}')\n"
    "            continue\n"
)
text = patch("process.py", text, OLD_VALIDATE, NEW_VALIDATE, "process.py skip invalid items")

OLD_SHORT = (
    "    if cfg.get('pro_edit_enabled', True):\n"
    "        profile = choose_profile(item, duration=target_len, short=True)\n"
)
NEW_SHORT = (
    "    if cfg.get('demo_style_enabled', True):\n"
    "        from demo_style import build_edit\n"
    "        demo_caption = item.get('_daily_caption') or caption_line(item, 'short')\n"
    "        build_edit(video, out, [(start, start + target_len)], demo_caption, root=ROOT)\n"
    "        mix_short_music(out, item, cfg)\n"
    "        return out, {'start': start, 'end': start + target_len, 'score': score}\n"
) + OLD_SHORT
text = patch("process.py", text, OLD_SHORT, NEW_SHORT, "process.py demo-style Shorts")
if text is not None:
    write("process.py", text)

# ---------------------------------------------------------------- uploaders/youtube.py
text = read("uploaders/youtube.py")
text = patch(
    "uploaders/youtube.py", text,
    "import json\nimport time\nimport subprocess\n",
    "import json\nimport os\nimport sys\nimport time\nimport subprocess\n",
    "youtube.py imports",
)
text = patch(
    "uploaders/youtube.py", text,
    "            creds.refresh(Request())\n",
    "            try:\n"
    "                creds.refresh(Request())\n"
    "            except Exception as exc:\n"
    "                raise RuntimeError(\n"
    "                    f'YouTube token refresh failed ({exc}). Re-authorize and update the '\n"
    "                    'YOUTUBE_TOKEN_B64 secret. If the Google OAuth app is in Testing mode, '\n"
    "                    'refresh tokens expire after 7 days: publish the app to Production.'\n"
    "                ) from exc\n",
    "youtube.py token refresh message",
)
text = patch(
    "uploaders/youtube.py", text,
    "        else:\n            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)\n",
    "        else:\n"
    "            if os.getenv('GITHUB_ACTIONS') == 'true' or not sys.stdin.isatty():\n"
    "                raise RuntimeError(\n"
    "                    'YouTube token is invalid and cannot be refreshed in CI. '\n"
    "                    'Re-authorize locally and update the YOUTUBE_TOKEN_B64 secret.'\n"
    "                )\n"
    "            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)\n",
    "youtube.py no browser flow in CI",
)
text = patch(
    "uploaders/youtube.py", text,
    "    response = None\n    while response is None:\n        _, response = request.next_chunk()\n",
    "    response = None\n"
    "    retries = 0\n"
    "    while response is None:\n"
    "        try:\n"
    "            _, response = request.next_chunk()\n"
    "        except HttpError as exc:\n"
    "            if exc.resp.status in (500, 502, 503, 504) and retries < 5:\n"
    "                retries += 1\n"
    "                time.sleep(2 ** retries)\n"
    "                continue\n"
    "            raise\n",
    "youtube.py upload retry",
)
if text is not None:
    write("uploaders/youtube.py", text)

if problems:
    print("\nPROBLEMS (nothing below was half-applied silently):")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("\nAll fixes applied.")
