# MovieAutoPublisher — Termux Processor

This project processes **licensed/owned/reusable** video files locally on Android/Termux. It does not download or bypass protected streams and does not promise copyright avoidance.

## Current features

- Movie / series / anime metadata
- Uses the supplied/original thumbnail file as the thumbnail base; no external thumbnail fetching
- Movie title + PART number overlay
- Series/anime Sxx Exx overlay
- `18+` overlay only when `adult: true` is explicitly set in metadata
- Video duration rule: <= 2 hours stays one video; > 2 hours becomes exactly 2 parts
- Creates one vertical Short from each processed part
- Optional automatic scene-change highlight selection for Shorts
- `edit_style`: `clean`, `funny`, or `dark` cosmetic presentation presets
- Optional manual censor boxes from metadata for supplied/licensed content
- Duplicate processing protection through `state/state.json`
- FFmpeg-based processing, Android/Termux friendly

### Important about scene selection

The highlight selector detects **visual scene changes**. It does not claim to understand whether a scene is funny, sexual, dramatic, or otherwise appropriate. For reliable semantic selection, use your own licensed metadata/timestamps. The `funny` and `dark` options are presentation styles, not content classifiers.

## Folder structure

- `input/videos/` — put licensed/owned MP4/MKV files here
- `input/thumbnails/` — put the exact thumbnail supplied with the content here
- `metadata.example.json` — example metadata
- `metadata.json` — your working metadata
- `output/` — generated videos/thumbnails
- `state/state.json` — processing history and queue

## Termux

```bash
pkg update -y
pkg install -y python ffmpeg git
cd ~/MovieAutoPublisher
python process.py --metadata metadata.json
```

Process one item:

```bash
python process.py --metadata metadata.json --id my-movie-001
```

## Editing styles

Use one of:

```json
"edit_style": "clean"
```

```json
"edit_style": "funny"
```

```json
"edit_style": "dark"
```

These only change presentation. They are not copyright-evasion transformations.

## Manual censoring

If a licensed video needs a known sensitive area blurred, add `censor_boxes` to its metadata. Coordinates are percentages of the frame:

```json
"censor_boxes": [
  {"start": 12.5, "end": 18.0, "x": 30, "y": 25, "w": 40, "h": 45}
]
```

This is intentionally manual/metadata-driven; the processor does not pretend to automatically identify sexual content.

## Upload integration

The processor creates a clean queue for a future official API uploader. YouTube uploads can be connected through the official YouTube Data API using OAuth, and Facebook publishing requires the appropriate Meta Page permissions/access token. Credentials are not embedded in this project.

The project is designed for licensed/reusable content only. Editing cannot guarantee or manufacture copyright clearance.


## Daily uploader queue

Check credential configuration:

```bash
python upload_queue.py --check
```

Preview the daily queue:

```bash
python upload_queue.py --queue
```

The uploader is intentionally credential-free until you authorize the YouTube channel and Facebook Page. Real tokens must never be placed in the repository or uploaded to GitHub.
