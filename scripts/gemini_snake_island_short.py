#!/usr/bin/env python3
"""VYROX GEN X: Snake Island Hindi Short using Gemini-generated photorealistic visuals."""
import asyncio, os, subprocess, textwrap, time
from pathlib import Path
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
import edge_tts

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"output"/"snake_island"
OUT.mkdir(parents=True, exist_ok=True)
KEY=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not KEY:
    raise SystemExit("Missing GEMINI_API_KEY GitHub Actions secret. Add it in repository Settings > Secrets and variables > Actions.")
client=genai.Client(api_key=KEY)
SCENES=[
 ("HOOK","Bhai, ek aisi jagah hai jahan aam logon ka jaana allowed nahi hai…","Snake Island, Brazil — lekin iske baare mein viral stories mein kuch baatein badha-chadha kar bhi boli jaati hain."),
 ("ISLAND","Samundar ke beech ek chhota, ghana jungle wala island…","Yahan golden lancehead naam ka saanp milta hai, jo duniya mein isi island par naturally paaya jaata hai."),
 ("WHY RESTRICTED","Par kyun nahi ja sakte wahan?","Island protected hai, aur entry par restrictions hain. Yeh koi tourist spot nahi—research aur conservation ke rules follow hote hain."),
 ("REAL TWIST","Aur ek baat yaad rakhna…","Har viral claim sach nahi hota. Snake Island ki real story aur bhi interesting hai—Part 2 chahiye toh comment karo: SNAKE!")
]
PROMPTS=[
"Photorealistic documentary aerial photograph of Ilha da Queimada Grande, also called Snake Island, off the coast of Sao Paulo state, Brazil; small rugged Atlantic island covered in dense subtropical green forest, steep rocky coastline, turquoise deep ocean, overcast tropical daylight, long-lens nature documentary, authentic natural colors, extremely realistic photography, no people, no buildings, no text, vertical 9:16 composition. This is an AI-generated visualization, not a claim to be a real documentary photograph.",
"Photorealistic macro wildlife documentary photograph of a golden lancehead pit viper (Bothrops insularis) resting naturally on a damp forest branch among authentic Atlantic rainforest leaves, triangular head, realistic golden-yellow and brown scales, natural diffuse daylight, shallow depth of field, scientific wildlife photography, non-graphic, no human interaction, no text, vertical 9:16. Accurate species appearance, AI-generated visualization.",
"Photorealistic documentary view from a small research boat looking toward the dense green forest and rocky shoreline of Ilha da Queimada Grande, Brazil; moody sea, natural cloudy light, realistic ocean spray, cinematic but documentary-true colors, no people on island, no text, vertical 9:16. AI-generated visualization, not actual recorded footage.",
"Photorealistic wildlife documentary close-up of a golden lancehead viper partly hidden among leaf litter on the forest floor of a Brazilian Atlantic island, realistic snake anatomy and scale texture, green foliage, soft natural daylight, shallow depth of field, no attack, no blood, no text, vertical 9:16. AI-generated visualization."
]
def gen_image(prompt, out):
    # Gemini image generation model; fail loudly if API/model access is unavailable.
    for attempt in range(3):
        try:
            response=client.models.generate_content(
                model="gemini-2.5-flash-image",
                contents=[prompt],
                config=types.GenerateContentConfig(response_modalities=["IMAGE","TEXT"])
            )
            for part in response.parts:
                if getattr(part,"inline_data",None):
                    part.as_image().save(out)
                    return
            raise RuntimeError("Gemini returned no image bytes.")
        except Exception:
            if attempt==2: raise
            time.sleep(4*(attempt+1))
def font(size):
    for p in ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if os.path.exists(p): return ImageFont.truetype(p,size)
    return ImageFont.load_default()
def make_card(src, dst, title, line1, line2):
    im=Image.open(src).convert("RGB").resize((1080,1920))
    # subtle dark gradient behind readable lower-third captions
    overlay=Image.new("RGBA",im.size,(0,0,0,0)); d=ImageDraw.Draw(overlay)
    d.rectangle((0,0,1080,150),fill=(0,0,0,130))
    d.rectangle((35,1370,1045,1850),fill=(0,0,0,185),outline=(0,220,255,220),width=3)
    d.text((50,48),"VYROX GEN X  •  REAL PLACES",font=font(30),fill=(80,230,255,255))
    d.text((540,1435),title,font=font(42),fill=(255,220,55,255),anchor="mm",stroke_width=2,stroke_fill=(0,0,0,255))
    def wrap(s, maxchars=38):
        return textwrap.wrap(s,width=maxchars)
    y=1515
    for line in wrap(line1,38):
        d.text((540,y),line,font=font(36),fill=(255,255,255,255),anchor="mm",stroke_width=2,stroke_fill=(0,0,0,255)); y+=48
    y=max(y+8,1660)
    for line in wrap(line2,38):
        d.text((540,y),line,font=font(31),fill=(75,235,255,255),anchor="mm",stroke_width=2,stroke_fill=(0,0,0,255)); y+=43
    im=Image.alpha_composite(im.convert("RGBA"),overlay).convert("RGB")
    im.save(dst,quality=94)
async def main():
    raw=[]; cards=[]
    for i,prompt in enumerate(PROMPTS):
        img=OUT/f"gemini_scene_{i+1}.png"; gen_image(prompt,img); raw.append(img)
        card=OUT/f"scene_{i+1}.jpg"; make_card(img,card,*SCENES[i]); cards.append(card)
        print(f"Generated Gemini visual {i+1}/4")
    narration=("Bhai, ek aisi jagah hai jahan aam logon ka jaana allowed nahi hai… Snake Island, Brazil. "
    "Lekin iske baare mein viral stories mein kuch baatein badha-chadha kar bhi boli jaati hain. "
    "Samundar ke beech ek chhota, ghana jungle wala island. Yahan golden lancehead naam ka saanp milta hai, jo duniya mein isi island par naturally paaya jaata hai. "
    "Par kyun nahi ja sakte wahan? Island protected hai, aur entry par restrictions hain. Yeh koi tourist spot nahi—research aur conservation ke rules follow hote hain. "
    "Aur ek baat yaad rakhna: har viral claim sach nahi hota. Snake Island ki real story aur bhi interesting hai. Part 2 chahiye toh comment karo: Snake!")
    voice=OUT/"hindi_natural_voice.mp3"
    await edge_tts.Communicate(narration,voice="hi-IN-MadhurNeural",rate="+2%",volume="+0%").save(str(voice))
    dur=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(voice)],text=True).strip())
    seg=dur/len(cards); clips=[]
    for i,card in enumerate(cards):
        clip=OUT/f"clip_{i+1}.mp4"; frames=max(1,round(seg*25))
        vf=f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0005,1.04)':d={frames}:s=1080x1920:fps=25,format=yuv420p"
        subprocess.run(["ffmpeg","-y","-loop","1","-i",str(card),"-t",f"{seg:.3f}","-vf",vf,"-an","-c:v","libx264","-preset","veryfast","-crf","19",str(clip)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        clips.append(clip)
    concat=OUT/"concat.txt"; concat.write_text("".join(f"file '{x.as_posix()}'\n" for x in clips))
    silent=OUT/"visual.mp4"
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(silent)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    final=OUT/"VYROX_Snake_Island_Hindi_Test.mp4"
    # Original low ambient suspense bed plus narration; no commercial song copied.
    subprocess.run(["ffmpeg","-y","-i",str(silent),"-i",str(voice),"-f","lavfi","-i",f"sine=frequency=62:sample_rate=44100:duration={dur}","-filter_complex","[1:a]volume=1.0[v];[2:a]lowpass=f=220,volume=0.035,afade=t=in:st=0:d=2[b];[v][b]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.92[a]","-map","0:v:0","-map","[a]","-t",str(dur),"-c:v","copy","-c:a","aac","-b:a","192k","-shortest",str(final)],check=True)
    print(f"VIDEO_READY={final}")
    print(f"DURATION_SECONDS={dur:.1f}")
if __name__=="__main__": asyncio.run(main())
