# VYROX GEN X — AI, Science & Anime Updates

This mode is focused on only three update categories: **AI**, **SCIENCE**, and **ANIME**.

## What the GitHub workflow does
- Fetches recent items from configured RSS feeds and rejects undated or older-than-14-days items.
- Selects an unseen story and builds a vertical 1080×1920 Short with hook, story details, source slide, voiceover, original visual design, and generated ambient audio.
- If the GitHub Actions secret `OPENAI_API_KEY` is configured, it requests a fresh original story-specific illustration from OpenAI Images. If that is unavailable, it tries a reusable source image with license metadata, then creates original in-project procedural artwork.
- Produces a video, metadata JSON, and preview PNG as a GitHub Actions artifact.
- Upload remains off by default. For a manual run, select **Actions → VYROX GEN X — AI Science Anime Shorts → Run workflow**, choose AI/SCIENCE/ANIME, and leave `publish=false` for a draft. Set `publish=true` only when you want to attempt YouTube upload. The publisher still blocks upload if its quality, rights, or score checks fail.
- YouTube privacy defaults to **private** unless the repository variable `VYROX_PRIVACY` is deliberately set to `unlisted` or `public`.

## Enable fresh AI images
In GitHub, open **Settings → Secrets and variables → Actions → New repository secret** and add `OPENAI_API_KEY` with your own OpenAI API key. Keep it secret; never paste it into code or chat. Image generation may incur API charges. If the secret is missing or image generation fails, the workflow falls back to a reusable licensed image, then original procedural artwork.

## Image policy
AI-generated visuals are illustrations, not photographs of the reported event. The script keeps source attribution for the story and does not claim the artwork documents the event.

## Current limitations
- The pipeline summarizes the selected feed story; a single RSS source is not independent corroboration. Verify factual claims before public posting.
- A high score is a ranking heuristic, not a guarantee of virality.
- Scheduled workflows run only from the repository's default branch. The branch workflow can be tested manually before any merge.
- This project does not download or reupload anime episode clips. Anime coverage is news/announcements, using source-attributed summaries and original visuals.
