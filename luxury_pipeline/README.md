# Luxury Shorts pipeline (MovieAutoPublisher ke andar, alag folder)

Roz ek luxury Short: topic dhundho -> fact-check -> video -> YouTube. Purane movie code ko haath nahi lagata.

## Roz ka rotation
Somvar billionaire news | Mangalvar supercars | Budhvar Dubai/mansion | Guruvar yachts-jets |
Shukravar watches | Shanivar morning routine (concept) | Ravivar chill party (concept).
News wale din real khabar + 2 sources + fact-check zaroori, warna video nahi banta.

## Workflow chalane ka tareeqa
- Scheduled (roz 09:00 aur 18:00 IST) **tab tak band hai** jab tak repo Variable `UPLOAD_MODE` nahi banta.
- Manual: Actions -> "Daily Luxury Short" -> Run workflow -> mode **dry** (sirf video banta hai, artifact me milta hai).
- Pehle dry, phir private, aur sab theek lage tab Variable `UPLOAD_MODE` = `public`.
- Fail ho to **Preflight** step ka text dekho: kaun sa secret/file/model missing hai wahin likha hota hai.

## Secrets: `GEMINI_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
## Optional Variables: `VIDEO_RES` (1080/4k), `GEMINI_IMAGE_SIZE` (1K/2K/4K), `GEMINI_TEXT_MODEL`, `GEMINI_IMAGE_MODEL`

## Music
`music/` me licensed modern tracks daalo (roz alag). Khaali ho to built-in modern music banta hai.
Attribution chahiye to `music/credits.txt` me likho.
