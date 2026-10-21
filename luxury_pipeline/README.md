# Isolated Luxury Shorts pipeline

This folder contains the original `luxury.py 1.zip` source as an encoded archive under `.bundle/`. The `Daily Luxury Short` GitHub Actions workflow validates and extracts that archive into `runtime/` before running it. This keeps all original MovieAutoPublisher source files and root dependencies untouched.

The workflow runs at 09:00 and 18:00 India time. The second scheduled run passes `--force` so the source pipeline can create a second Short for the same local date.

Required GitHub Actions secrets: `GEMINI_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN`. Manual workflow runs default to `dry`; scheduled runs default to `public` unless the repository variable `UPLOAD_MODE` overrides it. Run a manual `dry` test first, then verify a `private` upload before allowing scheduled public publishing.
