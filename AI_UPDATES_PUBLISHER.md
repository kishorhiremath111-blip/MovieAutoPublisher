# VYROX DAILY — Photo + Text Shorts

This is a separate workflow and does not modify the existing MovieAutoPublisher workflow.

## Format
- Vertical 9:16, 720x1280, around 21 seconds.
- Three photo-led slides: a 1–3 second visual hook, why-it-matters context, and a quick takeaway.
- No voiceover. Uses a small, locally generated electronic sound bed; no external music file is downloaded.
- Pulls news from official feeds (AI/tech, science, health and international affairs), links the original source in the YouTube description, and skips previously published source URLs.
- Attempts to use the article's Open Graph image. If none is available, it creates a branded graphic background instead. Only use source images where the source's reuse terms permit it; automated metadata extraction is not a license grant.

## GitHub Actions
Workflow: **VYROX DAILY Auto Shorts**. Manual dispatch defaults to draft-only; set `publish=true` to publish. Scheduled runs publish publicly daily at 7:30 PM India time, after this branch is merged to the default branch and Actions are enabled.

Required repository secrets:
- `YOUTUBE_CLIENT_SECRET_B64`
- `YOUTUBE_TOKEN_B64`

The token must have YouTube Data API upload scope and be refreshable. If Google's OAuth consent app is in Testing mode, refresh tokens may expire; check the OAuth app publishing status.

## Limitations
- Feed availability and article images vary. The workflow stops if no new story is found rather than re-uploading a duplicate.
- The locally synthesized background sound is deliberately subtle, not a commercial song. To use popular music, add a licensed track or use YouTube's own Shorts music library manually.
- This workflow does not guarantee fully generated photo assets or unlimited free AI image generation.
- Review the first artifact before enabling scheduled public uploads. Public uploads only start after the PR is merged and required secrets are valid.
