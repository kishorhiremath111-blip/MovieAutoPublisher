# MovieAutoPublisher Pro

Automation toolkit for **licensed/owned/authorized** video content.

## Daily content pipeline

1. Process an authorized source video.
2. Detect duration and split videos longer than 2 hours into exactly 2 parts.
3. Rank scene/highlight candidates using visual scene changes and audio activity.
4. Build a professional highlight compilation and one vertical Short.
5. Create exactly **2 original daily image cards** from source frames using `image_posts.py`.
6. Queue YouTube long/Short uploads.
7. Optionally publish the 2 image cards to a configured Facebook Page.

The image generator does **not** scrape random web images. It uses frames from the supplied authorized video and adds original text/layout treatment.

## Daily image commands

Generate two cards:

```bash
python upload_queue.py --daily-images
```

Publish up to two ready cards to a Facebook Page:

```bash
python upload_queue.py --facebook-images
```

Facebook credentials stay local in `credentials/facebook_page.json`.

## Content styles

The image generator adapts copy to movie, series, and anime content. It can produce moment, mood, anime, series and dark-comedy style cards. It does not claim that a scene is objectively viral; it ranks/frames content from the supplied source.

For health/wellness posts, use separately authored, factual copy. Do not automatically invent medical claims or diagnoses.

## YouTube image posts

The current YouTube Data API supports video uploads and video thumbnails, but it does not provide a general public API method for publishing a standalone Community image post. Therefore this project generates the image assets and can publish them to a configured Facebook Page; YouTube image/community publishing remains a manual/platform-supported step unless Google exposes an applicable API for the channel.

## Credentials

Never commit `credentials/client_secret.json`, `credentials/token.json`, or `credentials/facebook_page.json`.

## News engine

`news_engine.py` fetches fresh public RSS headlines and creates original vertical news cards/videos with a black headline panel, category label, channel-take text, and source link. It does **not** download or repost third-party news footage. For news footage, only use media you own or have explicit reuse rights for.

Generate two fresh news videos/cards:

```bash
python upload_queue.py --news
```

Upload up to two generated news videos to YouTube:

```bash
python upload_queue.py --news-upload
```

News is generated from configurable RSS feeds and deduplicated in `state/state.json`. “Breaking”/“viral” status is not guaranteed; feeds can lag and stories can change, so the source link is included for verification. Health posts use cautious wording and are not medical advice.

## 24/7 cloud mode

`cloud_runner.py` is a cloud-safe entry point. `.github/workflows/daily-publisher.yml`
runs once per day and can be started manually from GitHub Actions. It generates two
original news cards/videos, publishes eligible news videos, generates the daily image
cards, and processes only licensed content already present in the workspace.

### Important storage note
GitHub Actions runners are temporary. Large movie/video source files should **not** be
stored in the Git repository. For production, place licensed source media in a private
object-storage bucket and add a small download/sync step before `cloud_runner.py`.
The current workflow deliberately does not scrape or download movies/anime from
third-party sites.

### Secrets
Use the names in `cloud-secrets.example`. Keep OAuth client secrets and tokens in
GitHub Actions Secrets, never in Git. The workflow does not print secret values.
