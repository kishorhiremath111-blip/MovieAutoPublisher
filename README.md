# MovieAutoPublisher — Human-Style Scene Edits

A scheduled publishing pipeline for **authorized movie, web-series and anime scene files**. It is intended for short, natural scene edits with the original clip audio, restrained on-screen text, and content-matched colors. It does not generate news-anchor videos or synthetic narration.

## Current scheduled mode

The scheduled GitHub Actions workflow attempts **one YouTube Short and one long video per day**, using two distinct, rights-cleared sources. It uses the existing video editor and YouTube OAuth uploader, selects a fresh rights-cleared local source, and records the returned YouTube video ID. Long-form publishing, Facebook Reels, and image-post modules remain in the repository but are not run by this scheduled job. The schedule remains 7:00 PM India time (GitHub Actions may start a little later).

## Daily publishing goal

The GitHub Actions workflow is scheduled for **7:00 PM India time** (cron: 30 13 * * * UTC):
- YouTube: one long highlight compilation and one vertical Short.
- Facebook Page: one separate vertical Reel and 1–3 separate image cards.
- Every output should be based on a different source/topic for that day. The long video and Short must use distinct source files. The Reel must not reuse either source, and image-card topics must differ from all three.
- Scene captions and text overlays are OFF. The editor preserves the selected source's original Hindi or English dialogue/audio and never guesses language from the title.
- Effects are mood-matched and restrained: action/energy gets a stronger grade and controlled sharpening; dark/thriller gets a darker grade; cinematic scenes get a softer grade. A short clip-edge fade is used instead of random flashes. Highlight timing ranks detected scene changes and audio activity.
- Optional music is selected by `music_mood` from local licensed tracks (`input/music/energy.mp3`, `funny.mp3`, `dark.mp3`, `cinematic.mp3`). If the matching file exists, music is mixed quietly and ducked under original dialogue. Missing tracks mean original scene audio only; the workflow never downloads commercial songs.
- Trend metadata can inform discovery and prioritization. It cannot guarantee views or virality.

The workflow fails honestly when it cannot produce the required distinct content or when Facebook Page credentials are missing. A green GitHub check alone is not proof that all content was published.

## Copyright and sourcing — required

Use only footage and still images that you own, have licensed for the planned uploads, or have explicit permission to edit and repost. **Editing a copyrighted scene, adding captions, changing colors, or using a short excerpt does not make it copyright-free.** No tool can guarantee that a third-party platform will never issue a copyright claim or block a video.

The pipeline does not download random social-media clips, bypass Content ID, or extract protected video from an APK. A movie streaming APK is not, by itself, a source-media license. The source files need to be available locally or from storage you control and are authorized to use.

## Configure source videos

Copy **metadata.example.json** to **metadata.json** and replace all example paths with real files. Add at least **two different authorized source videos with different topic IDs** if you want both a long video and a Short that day. To publish a Facebook Reel from movie metadata alone, add a third authorized source/topic; alternatively, add a separate licensed item to social_sources.json that passes the viral score gate. Each item must provide:
- A unique ID.
- Source, a local video path (for example input/videos/clip-a.mp4).
- Thumbnail, a local image path.
- Type: movie, series, or anime.
- licensed: true only after verifying the rights/permission.
- topic_id, a short ID for the exact scene/topic, not merely the overall franchise; reuse the same topic ID for media that covers the same subject.
- Optional caption_text or hook_text for your chosen short overlay line. Otherwise a style- and day-dependent caption is selected automatically.
- Required credit/license details in the description where applicable.
- `audio_language`: `"hi"` for a source file whose actual dialogue is Hindi, or `"en"` for English.
- `audio_language_verified`: `true` only after checking the actual audio/dialogue track yourself. The pipeline does not infer language from a title or generate/translate a dub. Add separately authorized Hindi-dub and English-dub files as separate metadata items if you have rights to both; the processor preserves the audio track in each selected file and rejects unverified/missing language labels.
- `music_mood`: `energy`, `funny`, `dark`, `cinematic`, or `editorial`. Supply the matching licensed local track from `config/config.json`; the tracks are not bundled automatically.

The daily processor makes date-specific outputs and avoids previously published scene windows for the same source within the configured no-repeat period. If it cannot find a sufficiently different unused window or a second distinct source, it stops rather than recycling yesterday's output.

### Social clip source manifest

**social_sources.json** is for separate, explicitly authorized short-form clips that may be used for the Facebook Reel and trend-scored Short candidate. Copy the structure in **social_sources.example.json** and update each source path, license status, topic ID, license/credit, category, and caption. The viral score gate is a ranking heuristic, not a promise of viral performance.

## Configure separate image posts

**image_sources.json** contains still image files used for 1–3 daily social image cards. Copy the structure in **image_sources.example.json** and supply actual local stills in **input/image_sources/**. Each image must be licensed/owned/authorized. Use a unique topic ID that differs from the day's video, Short and Reel topics. Cards are not silently replaced with news cards or frames from the day's video when no separate image is available.

The generic YouTube Data API upload flow supports video uploads and thumbnails; it does not provide a general API method for arbitrary standalone Community image posts. Facebook image publication requires a configured Facebook Page access token. If these platform/credential capabilities are unavailable, upload the generated image manually or configure a supported authorized integration.

## Optional trend-inspired original AI image

If you configure the paid OpenAI Images API, the daily image step can create **at most one** original concept-art poster from current YouTube pop-culture trend metadata. It does not copy the trending video's images or frames and prompts the model to avoid named characters, actor likenesses, franchise logos and existing posters. The final card discloses that it is original AI-generated concept art, not an official frame or endorsement. Licensed still-image cards remain supported, up to the daily 1–3 card target.

Set a GitHub Actions Secret named **OPENAI_API_KEY** to enable this feature. The key is optional; without it, the workflow uses only the separately authorized local still-image manifest and skips AI artwork. OpenAI API usage has separate API billing; a ChatGPT plan does not itself supply API credits. Keep the key private and never paste it into chat or source files.

## Credentials and setup

- YouTube OAuth: **YOUTUBE_CLIENT_SECRET_B64** and **YOUTUBE_TOKEN_B64** (GitHub Actions Secrets).
- Trend metadata: **YOUTUBE_API_KEY** (GitHub Actions Secrets; official YouTube Data API metadata only).
- Facebook Page: **FACEBOOK_PAGE_B64**, containing a base64-encoded JSON object with page_id, page_access_token and optional graph_api_version. The Page token is not configured yet, so Facebook cannot publish.
- Instagram metadata collection is optional and requires its own configured credentials.

Never commit raw credentials or send them in chat. Do not hardcode secrets into Python files.

## Local edit checks

The workflow installs FFmpeg, runs Python syntax checks, and collects metadata-only anime, web-series comedy, and dark-comedy trend candidates from the official YouTube Data API. The trend report is saved as a workflow artifact; it is not a downloader and does not copy trending videos. The uploader checks that published files have both audio and video streams and a valid duration. This is a structural media check, not a human review of whether a scene is funny, suitable, or likely to perform well. Review licensed source quality before adding it.

## Important limits

- This repository has no movie/anime clips in metadata.json, no authorized short clips in social_sources.json, and no stills in image_sources.json by default. Full daily output also needs at least one separate image source whose topic differs from the day’s video/Short/Reel. Example manifests are templates only.
- The Movie.apk in a supplied ZIP is an app package, not ready-to-upload scene footage. Until real authorized source files and separate licensed stills are provided, the daily publishing workflow will stop instead of posting the old news fallback.
- The Facebook Page token must be added before Facebook Reels and image posts can upload.
- VN Editor is a mobile editor; this GitHub Actions workflow does not control the VN app directly.
- Daily posting depends on available unique source media, API quotas, platform review and credentials. It cannot be honestly guaranteed to run without interruption if any of those are missing.
