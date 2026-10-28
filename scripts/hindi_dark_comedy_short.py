#!/usr/bin/env python3
"""Render an original Hindi dark-comedy Short in GitHub Actions."""
import math, os, subprocess, asyncio
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import edge_tts

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "hindi_dark_comedy"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1080, 1920
FPS = 25
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
def font(size, bold=True):
    for p in FONT_CANDIDATES:
        if os.path.exists(p) and (not bold or "Bold" in p):
            return ImageFont.truetype(p, size)
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

SCENES = [
    ("BOSS KA MESSAGE", "रात के 2 बजे बॉस का मैसेज आया…", "कल से तुम हमारी फैमिली हो।"),
    ("DARK REALITY", "मैंने पूछा: सैलरी भी फैमिली वाली?", "उसने तुरंत Seen करके छोड़ दिया।"),
    ("AI KI ENTRY", "फिर मैंने AI से पूछा—", "भाई, नौकरी छोड़ दूँ क्या?"),
    ("AI KA JAWAAB", "AI बोला: पहले रिज़्यूमे अपडेट करो।", "मैं भी तुम्हारी तरह बेरोज़गार हो सकता हूँ।"),
    ("PLOT TWIST", "मैंने पूछा: तू इतना डार्क क्यों है?", "बोला: मेरी भी कोई छुट्टी नहीं।"),
    ("END CARD", "कॉर्पोरेट में सब परिवार हैं…", "बस विरासत में सिर्फ़ थकान मिलती है।"),
]
COLORS = [(4,8,22),(15,4,24),(3,13,28),(10,5,22),(18,5,20),(4,8,18)]
ACCENTS = [(0,225,255),(255,45,110),(122,80,255),(0,235,190),(255,100,45),(0,225,255)]

def make_scene(i, title, line1, line2):
    im = Image.new("RGB", (W,H))
    pix = im.load()
    top=COLORS[i]; accent=ACCENTS[i]
    for y in range(H):
        t=y/(H-1)
        for x in range(W):
            glow=max(0,1-math.sqrt(((x-W*(.72 if i%2 else .25))/(W*.8))**2+((y-H*.42)/(H*.7))**2))
            pix[x,y]=tuple(int(min(255,top[k]*(1-t*.18)+accent[k]*glow*.22)) for k in range(3))
    d=ImageDraw.Draw(im,"RGBA")
    # cinematic abstract city / office silhouettes
    for j in range(14):
        x=j*92-20; bh=220+(j*137+i*53)%520
        d.rounded_rectangle((x,H-480-bh,x+58,H-480),radius=8,fill=(3,6,14,200),outline=(*accent,70),width=2)
        for wy in range(H-450-bh,H-500,55):
            d.rectangle((x+15,wy,x+22,wy+12),fill=(*accent,100))
    # central cinematic character/robot silhouette, without central text
    cx=540; cy=720
    d.ellipse((cx-145,cy-170,cx+145,cy+120),fill=(4,7,15,245),outline=(*accent,220),width=8)
    d.rounded_rectangle((cx-190,cy+85,cx+190,cy+570),radius=90,fill=(4,7,15,245),outline=(*accent,200),width=8)
    d.ellipse((cx-90,cy-65,cx-25,cy+5),fill=(*accent,255))
    d.ellipse((cx+25,cy-65,cx+90,cy+5),fill=(*accent,255))
    d.arc((cx-70,cy+0,cx+70,cy+100),10,170,fill=(255,80,110,255),width=8)
    # small neon framing marks
    d.line((70,180,240,180),fill=(*accent,180),width=5); d.line((70,180,70,300),fill=(*accent,180),width=5)
    d.line((1010,180,840,180),fill=(*accent,180),width=5); d.line((1010,180,1010,300),fill=(*accent,180),width=5)
    # title near top only
    d.rounded_rectangle((70,230,1010,340),radius=26,fill=(0,0,0,150),outline=(*accent,180),width=2)
    d.text((W//2,285),title,font=font(48),fill=(255,255,255,255),anchor="mm",stroke_width=1,stroke_fill=(0,0,0,255))
    # captions strictly at bottom (lower third), never center
    d.rounded_rectangle((54,1400,1026,1780),radius=36,fill=(0,0,0,220),outline=(*accent,230),width=4)
    d.text((W//2,1515),line1,font=font(47),fill=(255,255,255,255),anchor="mm",align="center",stroke_width=1,stroke_fill=(0,0,0,255))
    d.text((W//2,1645),line2,font=font(44),fill=(*accent,255),anchor="mm",align="center",stroke_width=1,stroke_fill=(0,0,0,255))
    d.text((W//2,1840),"VYROX GEN X  •  HINDI DARK COMEDY",font=font(27),fill=(210,220,235,220),anchor="mm")
    # subtle vignette
    im=im.filter(ImageFilter.GaussianBlur(0.3))
    path=OUT/f"scene_{i+1:02d}.png"; im.save(path); return path

async def main():
    voice_text = " ".join([a+" "+b for _,a,b in SCENES])
    mp3=OUT/"hindi_voice.mp3"
    # Indian Hindi neural voice; voiceover is generated in Actions, not locally.
    communicate=edge_tts.Communicate(voice_text, voice="hi-IN-SwaraNeural", rate="+7%", volume="+0%")
    await communicate.save(str(mp3))
    scenes=[make_scene(i,*s) for i,s in enumerate(SCENES)]
    # One still per beat, slight motion, original ambient synth generated with FFmpeg.
    audio_len=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(mp3)],text=True).strip())
    per=audio_len/len(scenes)
    clips=[]
    for i,p in enumerate(scenes):
        clip=OUT/f"clip_{i+1:02d}.mp4"
        vf=f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},zoompan=z='min(zoom+0.0007,1.035)':d={math.ceil(per*FPS)}:s={W}x{H}:fps={FPS},format=yuv420p"
        subprocess.run(["ffmpeg","-y","-loop","1","-i",str(p),"-t",f"{per:.3f}","-vf",vf,"-an","-c:v","libx264","-preset","veryfast","-crf","21",str(clip)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        clips.append(clip)
    listing=OUT/"concat.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips))
    silent=OUT/"silent.mp4"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(listing),"-c","copy",str(silent)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    final=OUT/"VYROX_Hindi_Dark_Comedy.mp4"
    # generated dark synth bed under speech; no copyrighted song used
    subprocess.run(["ffmpeg","-y","-i",str(silent),"-i",str(mp3),"-f","lavfi","-i","sine=frequency=55:sample_rate=44100:duration="+str(audio_len),
        "-filter_complex","[1:a]volume=1.0[voice];[2:a]lowpass=f=120,volume=0.035[bed];[voice][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.92[a]",
        "-map","0:v:0","-map","[a]","-t",str(audio_len),"-c:v","copy","-c:a","aac","-b:a","192k","-shortest",str(final)],check=True)
    print(f"VIDEO_READY={final}")
    print(f"DURATION={audio_len:.2f}")
if __name__=="__main__":
    asyncio.run(main())
