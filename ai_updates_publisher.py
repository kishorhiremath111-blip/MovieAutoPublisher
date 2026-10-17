#!/usr/bin/env python3
"""VYROX DAILY: image-led, no-voice news Shorts with source attribution."""
import argparse, html, json, os, re, subprocess, sys, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "ai_updates"
STATE = ROOT / "state" / "ai_updates_seen.json"
W, H = 720, 1280
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VYROXDaily/1.0)"}
FEEDS = [
 ("TECH", "Google AI Blog", "https://blog.google/technology/ai/rss/"),
 ("AI", "OpenAI News", "https://openai.com/news/rss.xml"),
 ("SCIENCE", "NASA News", "https://www.nasa.gov/feed/"),
 ("HEALTH", "WHO News", "https://www.who.int/rss-feeds/news-english.xml"),
 ("WORLD", "UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
 ("TECH", "Android Developers Blog", "https://android-developers.googleblog.com/feeds/posts/default?alt=rss"),
]
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def clean(v):
 return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", v or ""))).strip()

def parse_feed(category, source, url):
 try:
  r=requests.get(url,headers=HEADERS,timeout=20); r.raise_for_status()
  root=ET.fromstring(r.content); rows=[]
  for item in root.findall(".//item")[:25]:
   title=clean(item.findtext("title")); link=clean(item.findtext("link")); desc=clean(item.findtext("description")); pub=clean(item.findtext("pubDate"))
   if title and link.startswith("https://"):
    rows.append({"category":category,"source":source,"title":title,"link":link,"summary":desc[:800],"published":pub})
  ns={"a":"http://www.w3.org/2005/Atom"}
  for e in root.findall(".//a:entry",ns)[:25]:
   title=clean(e.findtext("a:title",default="",namespaces=ns)); le=e.find("a:link",ns); link=le.attrib.get("href","") if le is not None else ""
   de=e.find("a:summary",ns)
   if de is None: de=e.find("a:content",ns)
   desc=clean(" ".join(de.itertext())) if de is not None else ""
   pub=clean(e.findtext("a:updated",default="",namespaces=ns))
   if title and link.startswith("https://"):
    rows.append({"category":category,"source":source,"title":title,"link":link,"summary":desc[:800],"published":pub})
  return rows
 except Exception as e:
  print(f"Feed unavailable {source}: {e}"); return []

def seen_links():
 try: return set(json.loads(STATE.read_text()).get("links",[]))
 except Exception: return set()

def choose():
 all_rows=[]
 for c,s,u in FEEDS: all_rows += parse_feed(c,s,u)
 seen=seen_links()
 # feed order is usually newest-first; don't invent facts or reuse a story
 fresh=[x for x in all_rows if x["link"] not in seen]
 if not fresh: raise RuntimeError("No unseen source story found. Skipping safely rather than reposting.")
 return fresh[0]

def font(path,size): return ImageFont.truetype(path,size)
def wrap(draw,text,f,maxw):
 out=[]; line=""
 for word in text.split():
  cand=(line+" "+word).strip()
  if draw.textbbox((0,0),cand,font=f)[2] <= maxw: line=cand
  else:
   if line: out.append(line)
   line=word
 if line: out.append(line)
 return out

def get_image(url):
 try:
  r=requests.get(url,headers=HEADERS,timeout=20); r.raise_for_status()
  if "image" not in r.headers.get("content-type","").lower(): return None
  p=OUT/"source_photo.jpg"; p.write_bytes(r.content)
  im=Image.open(p).convert("RGB")
  if im.width<320 or im.height<220: return None
  return im
 except Exception as e:
  print("Article photo unavailable:",e); return None

def article_image(url):
 try:
  r=requests.get(url,headers=HEADERS,timeout=20); r.raise_for_status()
  from html.parser import HTMLParser
  class Meta(HTMLParser):
   def __init__(self): super().__init__(); self.img=None
   def handle_starttag(self,tag,attrs):
    a=dict(attrs)
    if tag.lower()=="meta" and (a.get("property") in ("og:image","twitter:image") or a.get("name") in ("og:image","twitter:image")) and a.get("content","").startswith("https://") and not self.img: self.img=a["content"]
  p=Meta(); p.feed(r.text); return p.img
 except Exception as e:
  print("Image metadata unavailable:",e); return None

def commons_image(query):
 # Fallback to Wikimedia Commons only when an image has an explicit reuse-friendly license.
 try:
  r=requests.get("https://commons.wikimedia.org/w/api.php",params={
   "action":"query","generator":"search","gsrsearch":query,"gsrnamespace":6,
   "gsrlimit":10,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1400,"format":"json"
  },headers=HEADERS,timeout=20); r.raise_for_status()
  for page in r.json().get("query",{}).get("pages",{}).values():
   info=(page.get("imageinfo") or [{}])[0]; meta=info.get("extmetadata",{})
   license_name=clean(meta.get("LicenseShortName",{}).get("value","")).lower()
   if not any(x in license_name for x in ("cc0","public domain","cc by","cc-by","cc by-sa","cc-by-sa")): continue
   url=info.get("thumburl") or info.get("url")
   if url and url.startswith("https://"):
    return {"url":url,"license":license_name,"creator":clean(meta.get("Artist",{}).get("value",""))[:180],
            "page":"https://commons.wikimedia.org/wiki/"+page.get("title","").replace(" ","_")}
 except Exception as e: print("Commons image search unavailable:",e)
 return None

def fit_crop(im,size):
 tw,th=size; ratio=max(tw/im.width,th/im.height)
 im=im.resize((int(im.width*ratio),int(im.height*ratio)),Image.Resampling.LANCZOS)
 x=(im.width-tw)//2; y=(im.height-th)//2
 return im.crop((x,y,x+tw,y+th))

def make_slide(story, image, index, total):
 if image is None:
  image=Image.new("RGB",(W,H),(8,18,42))
  d=ImageDraw.Draw(image)
  for y in range(H):
   t=y/H; d.line((0,y,W,y),fill=(int(8+5*t),int(20+16*t),int(45+45*t)))
  d.ellipse((380,-100,850,380),fill=(15,67,130))
 else: image=fit_crop(image,(W,H)).filter(ImageFilter.GaussianBlur(0.3))
 # cinematic dark gradient for readable text
 overlay=Image.new("RGBA",(W,H),(0,0,0,0)); od=ImageDraw.Draw(overlay)
 for y in range(240,H):
  alpha=int(20+190*((y-240)/(H-240))**1.5)
  od.line((0,y,W,y),fill=(2,8,22,alpha))
 image=image.convert("RGBA"); image.alpha_composite(overlay); d=ImageDraw.Draw(image)
 d.rounded_rectangle((34,38,380,95),radius=18,fill=(0,14,34,225),outline=(0,211,255,255),width=2)
 d.text((52,51),"VYROX DAILY  /  "+story["category"],font=font(BOLD,21),fill=(255,255,255,255))
 if index==0:
  d.rounded_rectangle((36,760,684,1110),radius=24,fill=(4,12,28,225),outline=(0,207,255,240),width=3)
  d.text((62,790),"THE UPDATE",font=font(BOLD,22),fill=(0,220,255,255))
  lines=wrap(d,story["title"].upper(),font(BOLD,38),580)[:5]; y=838
  for line in lines: d.text((62,y),line,font=font(BOLD,38),fill="white",stroke_width=1,stroke_fill=(0,0,0)); y+=48
 else:
  d.rounded_rectangle((36,790,684,1110),radius=24,fill=(4,12,28,228),outline=(0,207,255,240),width=3)
  label=["WHY IT MATTERS","WHAT TO KNOW","THE BIG PICTURE","STAY INFORMED"][min(index-1,3)]
  d.text((62,820),label,font=font(BOLD,24),fill=(0,220,255,255))
  txt=story["summary"] or "Read the original report for the full details."
  txt=re.sub(r"\\s+"," ",txt)[:260]
  y=870
  for line in wrap(d,txt,font(REG,25),580)[:6]:
   d.text((62,y),line,font=font(REG,25),fill=(240,245,255,255)); y+=36
 d.text((42,1160),f"PHOTO + TEXT  •  {index+1}/{total}",font=font(BOLD,19),fill=(225,240,255,255))
 d.text((42,1200),"FACTS. PHOTOS. QUICK UPDATES.",font=font(BOLD,17),fill=(0,220,255,255))
 return image.convert("RGB")


def run(cmd): print("+"," ".join(map(str,cmd))); subprocess.run(cmd,check=True)

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--publish",action="store_true"); args=ap.parse_args()
 OUT.mkdir(parents=True,exist_ok=True)
 story=choose()
 photo_url=article_image(story["link"]); photo=get_image(photo_url) if photo_url else None
 image_credit="Article image (reuse permission not verified)" if photo is not None else "No article image found"
 commons=None
 if photo is None:
  commons=commons_image(" ".join(story["title"].split()[:7])+" "+story["category"])
  if commons:
   photo=get_image(commons["url"])
   if photo is not None: image_credit=f"Photo: {commons['page']} | License: {commons['license']} | Creator: {commons['creator']}"
 if photo is None: image_credit="Original branded graphic fallback; no external photo used"
 # One natural article photo per Short. The same photo is used throughout;
 # only the headline/detail overlay changes after the opening hook.
 hook=OUT/"hook.png"; detail=OUT/"detail.png"
 make_slide(story,photo,0,2).save(hook)
 make_slide(story,photo,1,2).save(detail)
 segments=[]
 for i,(p,duration) in enumerate([(hook,3),(detail,32)]):
  seg=OUT/f"segment_{i+1}.mp4"; segments.append(seg)
  run(["ffmpeg","-y","-loop","1","-i",str(p),"-t",str(duration),"-vf",f"scale=720:1280,zoompan=z='min(zoom+0.00045,1.035)':d={duration*25}:s=720x1280:fps=25,format=yuv420p","-r","25","-an","-c:v","libx264","-preset","veryfast","-crf","23",str(seg)])
 concat=OUT/"concat.txt"; concat.write_text("".join(f"file '{p.resolve()}'\n" for p in segments))
 silent=OUT/"silent.mp4"
 run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(silent)])
 video=OUT/"vyrox_daily_short.mp4"
 # Original subtle synthesized background audio; no voice and no downloaded song.
 run(["ffmpeg","-y","-i",str(silent),"-f","lavfi","-i","sine=frequency=110:duration=35:sample_rate=44100","-f","lavfi","-i","sine=frequency=164.81:duration=35:sample_rate=44100","-filter_complex","[1:a]volume=0.035,afade=t=in:st=0:d=1,afade=t=out:st=32:d=3[a1];[2:a]volume=0.02,afade=t=in:st=0:d=1,afade=t=out:st=18:d=2[a2];[a1][a2]amix=inputs=2:duration=longest,lowpass=f=900[a]","-map","0:v","-map","[a]","-c:v","copy","-c:a","aac","-b:a","96k","-shortest","-movflags","+faststart",str(video)])
 date=datetime.now(timezone.utc).strftime("%Y-%m-%d")
 title=(story["title"][:75].rstrip()+" | VYROX DAILY #Shorts")
 description=(f"{story['category']} update from {story['source']}.\n\nSummary: {story['summary'][:900]}\n\nOriginal source (read for full context): {story['link']}\n\nImages and text edited by VYROX DAILY. {image_credit}\nText edited by VYROX DAILY. Background sound is generated for this video.\n#Shorts #TechNews #AI #WorldNews #Science")
 meta={"title":title,"description":description,"source":story["link"],"category":story["category"],"date":date,"video":str(video),"image_credit":image_credit,"image_license":commons if commons else None,"duration_seconds":35}
 (OUT/"upload_metadata.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False))
 print("DRAFT_READY:",video)
 if args.publish:
  if os.getenv("GITHUB_ACTIONS")=="true":
   import base64
   creds=ROOT/"credentials"; creds.mkdir(exist_ok=True)
   for secret,target in [("YOUTUBE_CLIENT_SECRET_B64",creds/"client_secret.json"),("YOUTUBE_TOKEN_B64",creds/"token.json")]:
    value=os.getenv(secret,"").strip()
    if not value: raise RuntimeError(f"Missing GitHub Actions secret: {secret}")
    target.write_bytes(base64.b64decode(value,validate=True)); target.chmod(0o600)
  sys.path.insert(0,str(ROOT))
  from uploaders.youtube import upload_video
  video_id=upload_video(str(video),title,description,tags=["VYROX DAILY",story["category"],"Tech News","AI","Shorts"],privacy="public")
  print("YOUTUBE_UPLOAD_SUCCESS: https://youtube.com/shorts/"+video_id)
  seen=list(seen_links()); seen.append(story["link"]); STATE.parent.mkdir(parents=True,exist_ok=True)
  STATE.write_text(json.dumps({"links":seen[-500:]},indent=2),encoding="utf-8")
 else: print("DRAFT_ONLY: no upload attempted.")
if __name__=="__main__": main()
