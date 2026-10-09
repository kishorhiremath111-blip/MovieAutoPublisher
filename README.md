# MovieAutoPublisher — Human-Style Scene Edits

A scheduled publishing pipeline for **authorized movie, web-series and anime scene files**. It is intended for short, natural scene edits with the original clip audio, restrained on-screen text, and content-matched colors. It does not generate news-anchor videos or synthetic narration.

## Daily publishing goal

The GitHub Actions workflow is scheduled for **7:00 PM India time** (cron: 30 13 * * * UTC):
- YouTube: one long highlight compilation and one vertical Short.
- Facebook Page: one separate vertical Reel and 1–3 separate image cards.
- Every output should be based on a different source/topic for that day. The long video and Short must use distinct source files. The Reel must not reuse either source, and image-card topics must differ from all three.
- The editor keeps the original clip audio. No AI voice-over or generated spoken narration is used.
- Caption text is short, style-matched (anime/action/funny/cinematic/dark/clean), changes by source/day, and is placed in a safe area with restrained color. It must not cover faces or important action deliberately.
- Trend metadata can inform discovery and prioritization. It cannot guarantee views or virality.

The workflow fails honestly when it cannot produce the required distinct content or when Facebook Page credentials are missing. A green GitHub check alone is not proof that all content was published.

## Copyright and sourcing — required

Use only footage and still images that you own, have licensed for the planned uploads, or have explicit permission to edit and repost. **Editing a copyrighted scene, adding captions, changing colors, or using a short excerpt does not make it copyright-free.** No tool can guarantee that a third-party platform will never issue a copyright claim or block a video.

The pipeline does not download random social-media clips, bypass Content ID, or extract protected video from an APK. A movie streaming APK is not, by itself, a source-media license. The source files need to be available locally or from storage you control and are authorized to use.

## Configure source videos

Copy **metadata.example.json** to **metadata.json** and replace all example paths with real files. Add at least **two different authorized source videos** if you want both a long video and a Short that day. Each item must provide:
- A unique ID.
- Source, a local video path (for example input/videos/clip-a.mp4).
- Thumbnail, a local image path.
- Type: movie, series, or anime.
- licensed: true only after verifying the rights/permission.
- topic_id, a short ID for the exact scene/topic, not merely the overall franchise; reuse the same topic ID for media that covers the same subject.
- Optional caption_text or hook_text for your chosen short overlay line. Otherwise a style- and day-dependent caption is selected automatically.
- Required credit/license details in the description where applicable.

The daily processor makes date-specific outputs and avoids previously published scene windows for the same source within the configured no-repeat period. If it cannot find a sufficiently different unused window or a second distinct source, it stops rather than recycling yesterday's output.

### Social clip source manifest

**social_sources.json** is for separate, explicitly authorized short-form clips that may be used for the Facebook Reel and trend-scored Short candidate. Copy the structure in **social_sources.example.json** and update each source path, license status, topic ID, license/credit, category, and caption. The viral score gate is a ranking heuristic, not a promise of viral performance.

## Configure separate image posts

**image_sources.json** contains still image files used for 1–3 daily social image cards. Copy the structure in **image_sources.example.json** and supply actual local stills in **input/image_sources/**. Each image must be licensed/owned/authorized. Use a unique topic ID that differs from the day's video, Short and Reel topics. Cards are not silently replaced with news cards or frames from the day's video when no separate image is available.

The generic YouTube Data API upload flow supports video uploads and thumbnails; it does not provide a general API method for arbitrary standalone Community image posts. Facebook image publication requires a configured Facebook Page access token. If these platform/credential capabilities are unavailable, upload the generated image manually or configure a supported authorized integration.

## Credentials and setup

- YouTube OAuth: **YOUTUBE_CLIENT_SECRET_B64** and **YOUTUBE_TOKEN_B64** (GitHub Actions Secrets).
- Trend metadata: **YOUTUBE_API_KEY** (GitHub Actions Secrets; official YouTube Data API metadata only).
- Facebook Page: **FACEBOOK_PAGE_B64**, containing a base64-encoded JSON object with page_id, page_access_token and optional graph_api_version. The Page token is not configured yet, so Facebook cannot publish.
- Instagram metadata collection is optional and requires its own configured credentials.

Never commit raw credentials or send them in chat. Do not hardcode secrets into Python files.

## Local edit checks

The workflow installs FFmpeg and runs Python syntax checks. The uploader checks that published files have both audio and video streams and a valid duration. This is a structural media check, not a human review of whether a scene is funny, suitable, or likely to perform well. Review licensed source quality before adding it.

## Important limits

- This repository has no movie/anime clips in metadata.json, no authorized short clips in social_sources.json, and no stills in image_sources.json by default. Example manifests are templates only.
- The Movie.apk in a supplied ZIP is an app package, not ready-to-upload scene footage. Until real authorized source files and separate licensed stills are provided, the daily publishing workflow will stop instead of posting the old news fallback.
- The Facebook Page token must be added before Facebook Reels and image posts can upload.
- VN Editor is a mobile editor; this GitHub Actions workflow does not control the VN app directly.
- Daily posting depends on available unique source media, API quotas, platform review and credentials. It cannot be honestly guaranteed to run without interruption if any of those are missing.
