# Flickverse APK Static Scan — 2026-10-10

## Scope
Scanned the user-provided `movie apk.zip` archive without executing the app or making authenticated network requests.

- Archive size: about 53.6 MB
- Archive entries: 3,103
- Total uncompressed size: about 147.8 MB
- No standalone movie/video media file was found in the archive during this scan.
- This is a strings/resource scan, not a full decompilation or runtime traffic capture.

## Findings

### Candidate service-related host strings
1. `https://moviein.ajfysu.com/` — appears in `classes9.dex`. It is a candidate app/service domain based on the hostname, but this scan does **not** show that it serves movie streams or that it is the API base URL.
2. `https://moviein.g8w6.com/error.png` — appears in `classes3.dex`; the only observed path is an error image, so this is not evidence of a video endpoint.
3. `https://5rjmpws5csezv.akamaized.net/livelist.json` — appears in `classes8.dex`. The path suggests a list/metadata resource, but the scan does not establish that it contains film stream URLs or is used for the title under investigation.

The user-supplied share URL includes `vod_id=74339693`, but there is no confirmed mapping from that ID to an accessible media URL in this static scan.

### Playback-related identifiers
The DEX string pools contain names including `vod_id`, `getVod_url`, `play_url`, `playable_download_url`, `m3u8`, and `mpd`. These are identifiers/format strings only; a string match alone does not identify the call site, endpoint, or actual response.

The APK contains `assets/pp_hlsProtected.dat`, `lib/arm64-v8a/libpp_hls.so`, and `lib/arm64-v8a/libjiagu_sdk_pp_hlsProtected.so` (and 32-bit counterparts). This indicates HLS/protected-playback-related components are packaged with the app, but does not prove what content is protected or how the app's exact playback flow is configured.

### Ad-network noise
Many other domains in the DEX pools belong to ad/mediation SDKs (for example AppLovin, Pangle, Bigo, and mediation endpoints). They should not be mistaken for the movie origin.

## Conclusion
**No working movie-stream URL or confirmed movie API endpoint was found.** The most promising string to inspect further is `moviein.ajfysu.com`, but it remains unverified. `moviein.g8w6.com/error.png` is only an observed error-image path; `5rjmpws5csezv.akamaized.net/livelist.json` is only an observed list path.

A proper next step for an authorized source is to obtain the app's documented/export API or inspect app-owned server configuration. A logged-in playback session may use server responses, signed URLs, or DRM/licensing; this static scan did not recover tokens or try to bypass access controls. The strings alone are insufficient to build a reliable downloader or MovieAutoPublisher source adapter.

## Reproducible observations
- `classes9.dex`: `https://moviein.ajfysu.com/`, `getVod_url`, `vod_id`, `play_url`, `playable_download_url`
- `classes3.dex`: `https://moviein.g8w6.com/error.png`
- `classes8.dex`: `https://5rjmpws5csezv.akamaized.net/livelist.json`
- `classes.dex` / other DEX files: standard media/player/DRM-library strings including HLS/DASH/Widevine terminology

## Limitations
This report is based on static string scanning; it does not establish domain ownership, server behavior, API authorization, licensing rights, or the contents of responses.
