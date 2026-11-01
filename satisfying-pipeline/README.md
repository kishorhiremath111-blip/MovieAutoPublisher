# Satisfying 3D Shorts: daily auto pipeline

Roz 1 naya satisfying 3D Short banta hai aur YouTube par upload hota hai. Koi GPU nahi chahiye, GitHub Actions ke free CPU par chalta hai.

## Kaise kaam karta hai

1. `state/state.json` ka counter agla topic chunta hai (`topics.py`).
2. Topic = scene + palette + shape + material + BPM + camera + density + background. Total **6,912,000** alag combinations hain.
3. `renderer/scenes.js` (three.js) 3D scene banata hai, headless Chromium frame-by-frame screenshot leta hai.
4. `audio.py` bubble pop / tick / plink / soft beat ki awaaz banata hai (koi copyrighted music nahi).
5. ffmpeg video + audio jodta hai, quality check hota hai, YouTube par upload.
6. **Upload success hone par hi** topic "use ho gaya" mark hota hai: counter aage badhta hai, `state/used_topics.jsonl` me entry jaati hai, aur video file delete ho jaati hai. Upload fail ho to wahi topic agli baar dobara try hota hai. Ek topic kabhi do baar nahi aata.

6 scenes: Ripple Wave, Domino Spiral, Jar Fill, Endless Tunnel, Bubble Pop Wall, Helix Dance.

## Setup (phone se bhi ho jata hai)

1. GitHub par naya repo banao (ya MovieAutoPublisher se alag repo, taaki wo workflow na bigde).
2. Is zip ke saare files repo me upload karo. Dhyan do: workflow file ka path `.github/workflows/daily.yml` hona chahiye. Agar phone se dot-folder upload nahi hota to GitHub web me **Add file > Create new file** kholo, naam me `.github/workflows/daily.yml` likho aur `daily.yml` ka content paste karo. Zip me root par `daily.yml` ki ek copy isi kaam ke liye rakhi hai; baad me use delete kar sakte ho.
3. Repo **Settings > Secrets and variables > Actions** me ye 2 secrets daalo (wahi values jo MovieAutoPublisher me hain):
   - `YOUTUBE_CLIENT_SECRET_B64`
   - `YOUTUBE_TOKEN_B64`
4. Repo **Settings > Actions > General > Workflow permissions** me **Read and write permissions** chuno (state commit ke liye zaroori).
5. **Actions > Daily Satisfying Video > Run workflow**. Manual run me `dry_run` default **true** hai: sirf video banega, upload nahi hoga. Run khatam hone par neeche **Artifacts** se `satisfying-test-output` download karke video dekho.
6. Video pasand aaye to dobara Run workflow karo aur `dry_run` ka tick hatao. Uske baad roz apne aap chalega (6:00 PM IST, `daily.yml` me cron badal sakte ho).

## Pehle ye dhyan me rakho

- **Pehla dry run asli test hai.** Maine code ke saare hisse (topic engine, audio, ffmpeg, scene logic) alag alag test kiye, lekin yahan browser nahi tha, isliye asli WebGL render GitHub par pehli baar chalega. Kuch bigde to `work/ffmpeg.log` aur Actions ka log dekho.
- **Render time:** CPU par 720x1280, 30 fps, ~28 sec ka video lagbhag 5 se 20 minute leta hai. Timeout 150 minute rakha hai.
- **Quality:** ye clean, rangeen, ASMR-type 3D animation hai. Motu Patlu jaisa character-wala cartoon nahi hai.
- **Made for kids:** `config.json` me `made_for_kids` default `true` hai kyunki channel bacchon ke liye hai. Ye tumhari zimmedari ka declaration hai. Isse comments aur kuch features band hote hain. Apne channel ke hisaab se khud tay karo.
- **Variety:** 6.9 million combinations hain, lekin kai combinations dekhne me ek jaise lagenge (jaise sirf BPM ya background alag). Asli visual variety scenes aur palettes se aati hai.
- YouTube repetitive / mass-produced content par monetization rok sakta hai. Thoda-thoda apna touch (naye scenes, alag thumbnails, kabhi kabhi voice) rakhna achha rahega.
- OAuth app "Testing" mode me ho to token 7 din me expire hota hai. Use Production me publish karo.

## Local test (Termux nahi, PC par)

```
pip install -r requirements.txt
python -m playwright install chromium
python topics.py --preview 10        # pehle 10 topics dekho
DRY_RUN=true python run_pipeline.py  # video out/ me banega
```

## Files

| File | Kaam |
|---|---|
| `daily.yml` / `.github/workflows/daily.yml` | roz chalane wala workflow |
| `run_pipeline.py` | poora flow: topic, render, upload, topic hatao |
| `topics.py` | 6.9M topics ka engine, kabhi repeat nahi |
| `renderer/scene.html`, `renderer/scenes.js` | 3D scenes (three.js) |
| `render_video.py` | frame-by-frame render + ffmpeg |
| `audio.py` | ASMR-type awaaz |
| `upload_youtube.py` | YouTube upload (official API) |
| `config.json` | size, fps, privacy, made_for_kids |
| `state/` | counter aur use ho chuke topics ki list |
