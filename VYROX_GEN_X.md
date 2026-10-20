# VYROX GEN X — AI, Science & Anime Updates

This mode is focused on only three update categories: **AI**, **SCIENCE**, and **ANIME**.

## What the GitHub workflow does
- Fetches recent items from configured RSS feeds and rejects undated or older-than-14-days items.
- Selects an unseen story and builds a vertical 1080×1920 Short with hook, story details, source slide, voiceover, original visual design, and generated ambient audio.
- Uses a reusable source image when a suitable asset with license metadata is found. If none is available, it creates original in-project visual artwork instead of pretending a generic picture is a real event photo.
- Produces a video, metadata JSON, and preview PNG as a GitHub Actions artifact.
- Upload remains off by default. For a manual run, select **Actions → VYROX GEN X — AI Science Anime Shorts → Run workflow**, choose AI/SCIENCE/ANIME, and leave `publish=false` for a draft. Set `publish=true` only when you want to attempt YouTube upload. The publisher still blocks upload if its quality, rights, or score checks fail.
- YouTube privacy defaults to **private** unless the repository variable `VYROX_PRIVACY` is deliberately set to `unlisted` or `public`.

## Image policy
The pipeline creates original graphic art with its own visual design and uses licensed real images when available. It does not guarantee a photorealistic generative-AI image on every run; the in-project fallback is original procedural artwork. Do not claim a generated visual is a photograph of the event.

## Current limitations
- The pipeline summarizes the selected feed story; a single RSS source is not independent corroboration. Verify factual claims before public posting.
- A high score is a ranking heuristic, not a guarantee of virality.
- Scheduled workflows run only from the repository's default branch. The branch workflow can be tested manually before any merge.
- This project does not download or reupload anime episode clips. Anime coverage is news/announcements, using source-attributed summaries and original visuals.
