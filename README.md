# Kids YouTube Auto (100% GitHub par, roz khud video + upload)

Roz: Gemini script -> Pollinations (flux) HD cartoon images -> edge-tts Hindi voice -> FFmpeg (zoom, fade, subtitles, music) -> YouTube Short.

## Files
- generate.py : poora system
- topics.json : roz ek topic (apne topics add karo)
- .github/workflows/daily.yml : roz ka schedule
- music/ : yahan royalty-free .mp3 daalo (optional, low volume me chalega)
- get_refresh_token.py : YouTube token nikalne ke liye (PC par ek baar)

## Setup
0. `daily.yml` (root me) ko GitHub repo me **`.github/workflows/daily.yml`** path par rakho.
1. GitHub par public repo banao aur ye saari files upload karo (.github folder ke saath).
2. Gemini key: aistudio.google.com/apikey -> secret `GEMINI_API_KEY`.
3. Pehle sirf test karna ho to bas step 2 kaafi hai (YouTube secrets baad me).
4. Actions tab -> "Daily Kids Video" -> Run workflow (dry_run = 1) -> Artifacts -> `video` se final.mp4 download karke dekho.

## YouTube upload setup
1. console.cloud.google.com -> naya project -> YouTube Data API v3 Enable.
2. OAuth consent screen configure karo aur app publish requirements complete karo.
3. Credentials -> OAuth client ID -> Desktop app -> JSON download.
4. `pip install google-auth-oauthlib` fir `python get_refresh_token.py`.
5. `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` ko GitHub Actions Secrets me daalo.
6. dry_run = 0 se upload test karo.

## Customize
- English: `VIDEO_LANGUAGE: "en"`
- Subtitles band: `SUBTITLES: "0"`
- Schedule cron UTC me hai; IST = UTC + 5:30
