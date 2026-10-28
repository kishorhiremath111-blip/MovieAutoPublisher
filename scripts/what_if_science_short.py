#!/usr/bin/env python3
"""VYROX GEN X: Hindi What-If science Short, rendered on GitHub Actions."""
import asyncio, math, os, subprocess, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import edge_tts

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "what_if_shorts"
OUT.mkdir(parents=True, exist_ok=True)
W, H, FPS = 1080, 1920, 25
FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def font(size, bold=True):
    for path in FONT_PATHS:
        if os.path.exists(path) and (not bold or "Bold" in path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# First episode: the abrupt-stop scenario is explicitly identified as hypothetical.
SCENES = [
    ("WHAT IF? #01", "सोचो… अगर पृथ्वी अचानक घूमना बंद कर दे?", "पहले ही पल में सब कुछ बदल जाएगा।"),
    ("1 SECOND LATER", "भूमध्य रेखा पर ज़मीन अभी लगभग 1,670 km/h से घूम रही है।", "रुकने पर चीज़ें अपनी गति से आगे बढ़ना चाहेंगी।"),
    ("OCEANS IN MOTION", "हवा और महासागर तुरंत नहीं रुकेंगे।", "तेज़ हवाएँ और विशाल लहरें तबाही मचा सकती हैं।"),
    ("THE BIG TWIST", "ये सिर्फ़ दिन-रात का मामला नहीं है।", "पृथ्वी की rotation मौसम, हवाओं और समुद्रों को भी प्रभावित करती है।"),
    ("REAL SCIENCE", "असल दुनिया में ऐसा अचानक रुकना बेहद अवास्तविक है।", "ये एक काल्पनिक thought experiment है—भविष्यवाणी नहीं।"),
    ("PART 2?", "और अगर चाँद अचानक गायब हो जाए तो?", "कमेंट करो: MOON — अगला What If यही होगा!"),
]
BG = [(3,8,25),(6,10,32),(4,12,35),(10,4,28),(4,14,24),(3,7,22)]
ACCENT = [(0,225,255),(255,92,80),(40,180,255),(180,100,255),(80,255,190),(0,225,255)]

def wrap_text(draw, text, fnt, max_width):
    words=text.split()
    lines=[]; cur=""
    for word in words:
        trial=(cur+" "+word).strip()
        if draw.textbbox((0,0),trial,font=fnt)[2] <= max_width:
            cur=trial
        else:
            if cur: lines.append(cur)
            cur=word
    if cur: lines.append(cur)
    return lines

def draw_centered_lines(draw, text, y, fnt, fill, max_width=860, line_gap=15):
    lines=wrap_text(draw,text,fnt,max_width)
    for line in lines:
        draw.text((W//2,y),line,font=fnt,fill=fill,anchor="mm",
                  stroke_width=2,stroke_fill=(0,0,0,255))
        y += fnt.size + line_gap

def make_scene(i, title, line1, line2):
    im=Image.new("RGB",(W,H))
    p=im.load(); top=BG[i]; ac=ACCENT[i]
    # cinematic gradient with atmospheric glow
    for y in range(H):
        t=y/(H-1)
        for x in range(W):
            g=max(0,1-math.sqrt(((x-W*(.25 if i%2==0 else .78))/(W*.8))**2+((y-H*.42)/(H*.72))**2))
            p[x,y]=tuple(int(min(255,top[k]*(1-t*.12)+ac[k]*g*.30)) for k in range(3))
    d=ImageDraw.Draw(im,"RGBA")
    # star field
    for n in range(130):
        x=(n*197+i*71)%W; y=(n*313+i*47)%H
        r=1+(n%3)
        d.ellipse((x-r,y-r,x+r,y+r),fill=(200,230,255,90+(n%4)*35))
    # scene-specific cinematic science illustration
    if i in (0,1,2,3,4):
        # Earth with blue atmosphere and continents
        cx,cy=540,780; radius=300
        d.ellipse((cx-radius-20,cy-radius-20,cx+radius+20,cy+radius+20),outline=(*ac,100),width=8)
        d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=(7,54,116,255),outline=(80,210,255,255),width=8)
        # stylized continents / cloud streaks
        d.polygon([(350,600),(410,545),(490,565),(515,625),(470,660),(450,730),(385,700)],fill=(65,177,120,240))
        d.polygon([(570,560),(650,580),(705,650),(675,720),(625,700),(600,650)],fill=(88,190,130,230))
        d.polygon([(500,780),(560,760),(620,815),(600,910),(545,950),(510,870)],fill=(70,160,115,230))
        for k in range(5):
            yy=610+k*65
            d.arc((cx-radius+25,yy-40,cx+radius-25,yy+80),190,345,fill=(170,235,255,90),width=5)
        if i in (1,2):
            # motion arrows to show inertia
            for yy in (650,780,910):
                d.line((170,yy,355,yy),fill=(*ac,230),width=10)
                d.polygon([(355,yy),(325,yy-20),(325,yy+20)],fill=(*ac,230))
                d.line((725,yy,910,yy),fill=(*ac,230),width=10)
                d.polygon([(910,yy),(880,yy-20),(880,yy+20)],fill=(*ac,230))
        if i==3:
            # ocean wave strokes
            for yy in (1030,1080,1130):
                d.arc((100,yy-50,980,yy+100),0,180,fill=(0,190,255,230),width=12)
    else:
        # moon for the next-episode tease
        cx,cy=540,800; r=270
        d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=(160,168,190,255),outline=(220,230,255,255),width=7)
        for x,y,rr in [(440,700,38),(600,640,24),(640,850,55),(470,910,30),(565,790,20)]:
            d.ellipse((x-rr,y-rr,x+rr,y+rr),fill=(105,115,140,150))
        d.ellipse((cx-r+100,cy-r+20,cx+r+40,cy+r+30),fill=(0,0,0,0),outline=(*ac,150),width=10)
    # top brand and chapter tag
    d.text((70,95),"VYROX GEN X",font=font(28),fill=(*ac,255))
    d.rounded_rectangle((65,175,1015,285),radius=28,fill=(0,0,0,150),outline=(*ac,180),width=3)
    d.text((W//2,230),title,font=font(45),fill=(255,255,255,255),anchor="mm",
           stroke_width=1,stroke_fill=(0,0,0,255))
    # lower-third subtitles only: main copy is intentionally below the middle
    d.rounded_rectangle((48,1390,1032,1788),radius=36,fill=(0,0,0,222),outline=(*ac,240),width=4)
    draw_centered_lines(d,line1,1480,font(43), (255,255,255,255), 860, 12)
    draw_centered_lines(d,line2,1640,font(39), (*ac,255), 860, 10)
    d.text((W//2,1840),"HYPOTHETICAL SCIENCE • PART 01",font=font(24),fill=(220,230,245,220),anchor="mm")
    im=im.filter(ImageFilter.GaussianBlur(.25))
    path=OUT/f"scene_{i+1:02d}.png"; im.save(path); return path

async def main():
    narration = (
      "सोचो, अगर पृथ्वी अचानक घूमना बंद कर दे? पहले ही पल में सब कुछ बदल जाएगा। "
      "भूमध्य रेखा पर ज़मीन अभी लगभग सोलह सौ सत्तर किलोमीटर प्रति घंटे की रफ़्तार से घूम रही है। "
      "रुकने पर हवा, पानी और चीज़ें अपनी गति से आगे बढ़ना चाहेंगी। "
      "हवा और महासागर तुरंत नहीं रुकेंगे। तेज़ हवाएँ और विशाल लहरें तबाही मचा सकती हैं। "
      "ये सिर्फ़ दिन और रात का मामला नहीं है। पृथ्वी की rotation मौसम, हवाओं और समुद्रों को भी प्रभावित करती है। "
      "असल दुनिया में ऐसा अचानक रुकना बेहद अवास्तविक है। ये एक काल्पनिक thought experiment है, भविष्यवाणी नहीं। "
      "और अगर चाँद अचानक गायब हो जाए तो? कमेंट करो Moon—अगला What If यही होगा!"
    )
    voice=OUT/"hindi_male_voice.mp3"
    await edge_tts.Communicate(narration,voice="hi-IN-MadhurNeural",rate="+8%",volume="+0%").save(str(voice))
    paths=[make_scene(i,*scene) for i,scene in enumerate(SCENES)]
    duration=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(voice)],text=True).strip())
    per=duration/len(paths); clips=[]
    for i,path in enumerate(paths):
        clip=OUT/f"clip_{i+1:02d}.mp4"; frames=math.ceil(per*FPS)
        vf=f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},zoompan=z='min(zoom+0.0006,1.03)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p"
        subprocess.run(["ffmpeg","-y","-loop","1","-i",str(path),"-t",f"{per:.3f}","-vf",vf,"-an","-c:v","libx264","-preset","veryfast","-crf","20",str(clip)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        clips.append(clip)
    concat=OUT/"concat.txt"; concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips))
    silent=OUT/"visuals.mp4"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(silent)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    final=OUT/"VYROX_What_If_Earth_Stops_Rotating_Hindi.mp4"
    # original, copyright-safe synthesized suspense bed, ducked below narration
    subprocess.run(["ffmpeg","-y","-i",str(silent),"-i",str(voice),"-f","lavfi","-i",f"sine=frequency=48:sample_rate=44100:duration={duration}",
      "-filter_complex","[1:a]volume=1.0[voice];[2:a]lowpass=f=180,volume=0.045,afade=t=in:st=0:d=1.5[bed];[voice][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.92[a]",
      "-map","0:v:0","-map","[a]","-t",str(duration),"-c:v","copy","-c:a","aac","-b:a","192k","-shortest",str(final)],check=True)
    print(f"VIDEO_READY={final}")
    print(f"DURATION={duration:.2f}")
if __name__=="__main__": asyncio.run(main())
