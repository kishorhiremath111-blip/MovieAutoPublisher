#!/usr/bin/env python3
"""Original news-card/news-video generator from public RSS headlines.

It summarizes/frames headlines into original graphics. It does NOT download or
repost third-party news footage. Rights-cleared media can be placed in
input/news_media/ and used explicitly by the operator.
"""
import argparse, hashlib, json, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import subprocess

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config' / 'config.json'
STATE = ROOT / 'state' / 'state.json'
OUT = ROOT / 'output' / 'news'
BRAND_DIR = ROOT / 'input' / 'brand_assets'
MUSIC_DIR = ROOT / 'input' / 'music'

DEFAULT_FEEDS = {
    'world': 'https://news.google.com/rss/search?q=' + urllib.parse.quote('world when:1d') + '&hl=en-IN&gl=IN&ceid=IN:en',
    'ai': 'https://news.google.com/rss/search?q=' + urllib.parse.quote('artificial intelligence AI when:1d') + '&hl=en-IN&gl=IN&ceid=IN:en',
    'india': 'https://news.google.com/rss/search?q=' + urllib.parse.quote('India when:1d') + '&hl=en-IN&gl=IN&ceid=IN:en',
    'health': 'https://news.google.com/rss/search?q=' + urllib.parse.quote('health medical science when:1d') + '&hl=en-IN&gl=IN&ceid=IN:en',
    'technology': 'https://news.google.com/rss/search?q=' + urllib.parse.quote('technology gadgets cybersecurity when:1d') + '&hl=en-IN&gl=IN&ceid=IN:en',
    'science': 'https://news.google.com/rss/search?q=' + urllib.parse.quote('science space climate research when:1d') + '&hl=en-IN&gl=IN&ceid=IN:en',
    'anime': 'https://news.google.com/rss/search?q=' + urllib.parse.quote('anime manga when:1d') + '&hl=en-IN&gl=IN&ceid=IN:en',
    'entertainment': 'https://news.google.com/rss/search?q=' + urllib.parse.quote('entertainment anime movies when:1d') + '&hl=en-IN&gl=IN&ceid=IN:en',
}


def load(path, default):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'MovieAutoPublisher/Pro-News/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(text):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text or '')).strip()


def feed_items(category, url):
    root = ET.fromstring(fetch(url))
    out = []
    for item in root.findall('.//item'):
        title = clean(item.findtext('title'))
        link = clean(item.findtext('link'))
        desc = clean(item.findtext('description'))
        pub = clean(item.findtext('pubDate'))
        if title and link:
            out.append({'category': category, 'title': title, 'description': desc[:700], 'link': link, 'published': pub})
    return out


def font(size, bold=False):
    candidates = ['/system/fonts/Roboto-Bold.ttf' if bold else '/system/fonts/Roboto-Regular.ttf',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for p in candidates:
        if Path(p).exists(): return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def wrap(draw, text, fnt, width):
    words = text.split(); lines=[]; line=''
    for w in words:
        test=(line+' '+w).strip()
        if draw.textbbox((0,0),test,font=fnt)[2] <= width: line=test
        else:
            if line: lines.append(line)
            line=w
    if line: lines.append(line)
    return lines


def commentary(category, title):
    if category in ('ai','technology'): return 'Channel take: Tech update ka real impact features se zyada privacy, safety, cost aur daily life par depend karta hai.'
    if category == 'science': return 'Channel take: Science story ko headline se nahi, evidence, researchers aur follow-up results se judge karna better hai.'
    if category == 'anime': return 'Channel take: Anime update me official announcement aur studio/source ko priority dena sabse reliable hai.'
    if category == 'ai': return 'Channel take: AI news ko sirf hype se nahi, real-world impact aur privacy/safety angle se dekhna chahiye.'
    if category == 'health': return 'Channel take: Health news me headline se zyada source, evidence aur expert guidance important hai. Is post ko medical advice na samjhein.'
    if category == 'india': return 'Channel take: Is update ka real impact aage ke official announcements aur ground-level developments se clear hoga.'
    if category == 'entertainment': return 'Channel take: Entertainment me trend fast move karta hai, isliye original source aur official announcement ko priority dena best hai.'
    return 'Channel take: Story develop ho rahi ho sakti hai—confirmed facts aur official updates ko priority dena sabse important hai.'



def commons_image(item, out):
    """Find a rights-cleared real-world image on Wikimedia Commons.
    Only files whose machine-readable license is CC BY/CC BY-SA/CC0/Public Domain
    are accepted; otherwise the generator falls back to an original graphic.
    """
    query = item.get('title','')
    api = ('https://commons.wikimedia.org/w/api.php?action=query&generator=search'
           '&gsrsearch=' + urllib.parse.quote(query[:180]) +
           '&gsrnamespace=6&gsrlimit=5&prop=imageinfo'
           '&iiprop=url|extmetadata&iiurlwidth=1400&format=json')
    try:
        data=json.loads(fetch(api, timeout=20).decode('utf-8'))
    except Exception:
        return None
    pages=data.get('query',{}).get('pages',{})
    allowed=('cc by','cc by-sa','cc0','public domain','pd-')
    for page in pages.values():
        info=(page.get('imageinfo') or [{}])[0]
        meta=info.get('extmetadata') or {}
        lic=clean(meta.get('LicenseShortName',{}).get('value','')).lower()
        if not any(x in lic for x in allowed):
            continue
        url=info.get('thumburl') or info.get('url')
        if not url:
            continue
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'MovieAutoPublisher/Pro-News/1.0'})
            with urllib.request.urlopen(req,timeout=30) as r:
                raw=r.read()
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(raw)
            artist=clean(meta.get('Artist',{}).get('value','')) or 'Unknown author'
            license_name=clean(meta.get('LicenseShortName',{}).get('value','')) or lic
            desc_url='https://commons.wikimedia.org/wiki/File:' + urllib.parse.quote(page.get('title','').replace('File:','').replace(' ','_'))
            return {'path':out,'artist':artist,'license':license_name,'page':desc_url}
        except Exception:
            continue
    return None


def brand_logo():
    if not BRAND_DIR.exists(): return None
    imgs=[p for p in BRAND_DIR.iterdir() if p.is_file() and p.suffix.lower() in {'.png','.jpg','.jpeg','.webp'}]
    return sorted(imgs,key=lambda p:p.stat().st_size,reverse=True)[0] if imgs else None


def make_card(item, out, real_image=None):
    W,H=1080,1350
    if real_image and real_image.exists():
        try:
            src=Image.open(real_image).convert('RGB')
            src.thumbnail((W,H))
            im=Image.new('RGB',(W,H),(10,10,12))
            im.paste(src,((W-src.width)//2,(H-src.height)//2))
            im=ImageEnhance.Contrast(im).enhance(1.05)
            im=ImageEnhance.Brightness(im).enhance(0.82)
        except Exception:
            im=Image.new('RGB',(W,H),(10,10,12))
    else:
        im=Image.new('RGB',(W,H),(10,10,12))
    d=ImageDraw.Draw(im)
    # Original abstract visual; no third-party image scraping.
    for y in range(520,H):
        shade=int(18 + 45*(y-520)/(H-520)); d.line((0,y,W,y),fill=(shade,shade,shade+4))
    # abstract news globe / signal motif
    cx,cy=540,930
    for r in (250,190,130,70): d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(90,90,95),width=3)
    for x in range(260,821,80): d.line((x,680,x,1180),fill=(45,45,50),width=2)
    d.rectangle((0,0,W,560),fill=(0,0,0))
    cat=item['category'].upper()
    d.text((55,45),'LATEST UPDATE',font=font(30,True),fill=(255,255,255))
    d.text((55,95),cat,font=font(25,True),fill=(190,190,190))
    y=155
    for line in wrap(d,item['title'],font(56,True),960)[:6]:
        d.text((55,y),line,font=font(56,True),fill='white',stroke_width=1,stroke_fill='black'); y+=67
    d.rectangle((55,500,1025,505),fill=(255,255,255))
    take=commentary(item['category'],item['title'])
    yy=1135
    for line in wrap(d,take,font(27,False),920)[:3]:
        d.text((55,yy),line,font=font(27),fill=(235,235,235)); yy+=38
    d.text((55,1260),'Source: Google News RSS • Verify with the original report',font=font(22),fill=(160,160,160))
    logo=brand_logo()
    if logo:
        try:
            lg=Image.open(logo).convert('RGBA'); lg.thumbnail((170,170))
            im.paste(lg,(W-lg.width-45,H-lg.height-35),lg)
        except Exception: pass
    out.parent.mkdir(parents=True,exist_ok=True); im.save(out,quality=94,optimize=True)


def pick_music(item):
    if not MUSIC_DIR.exists(): return None
    tracks=[p for p in MUSIC_DIR.iterdir() if p.is_file() and p.suffix.lower() in {'.mp3','.m4a','.wav','.aac'}]
    if not tracks: return None
    key=(item.get('category','')+'|'+item.get('title','')).encode()
    return sorted(tracks)[int(hashlib.sha256(key).hexdigest(),16)%len(tracks)]


def make_video(card, out, item):
    # Original motion card; no third-party footage is downloaded.
    textfile = out.parent / (out.stem + '.txt')
    textfile.write_text(item['title'],encoding='utf-8')
    music=pick_music(item)
    cmd=['ffmpeg','-y','-loop','1','-i',str(card)]
    if music:
        cmd += ['-stream_loop','-1','-i',str(music),'-t','30','-vf','zoompan=z=1.02:d=750:s=1080x1920:fps=25,format=yuv420p','-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','veryfast','-b:v','2500k','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(out)]
    else:
        cmd += ['-t','30','-vf','zoompan=z=1.02:d=750:s=1080x1920:fps=25,format=yuv420p','-an','-c:v','libx264','-preset','veryfast','-b:v','2500k','-movflags','+faststart',str(out)]
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def generate(limit=2):
    state=load(STATE,{'news':[]})
    seen={x.get('fingerprint') for x in state.get('news',[])}
    items=[]
    for cat,url in DEFAULT_FEEDS.items():
        try: items.extend(feed_items(cat,url)[:8])
        except Exception as e: print('Feed failed',cat,e)
    # deterministic, fresh-first, de-duped
    fresh=[]
    for x in items:
        fp=hashlib.sha256((x['title']+'|'+x['link']).encode()).hexdigest()
        if fp in seen: continue
        x['fingerprint']=fp; fresh.append(x)
    # Instagram trend metadata is used only as a topic signal. Third-party media is not reposted.
    try:
        ig=load(ROOT/'state'/'instagram_trends.json',{'items':[]})
        for row in ig.get('items',[])[:20]:
            cap=clean(row.get('caption',''))
            if cap:
                fresh.append({'category':'instagram-trend','title':cap.split('\n')[0][:180],'description':cap[:700],'link':row.get('permalink',''),'published':row.get('timestamp',''),'fingerprint':hashlib.sha256((row.get('id','')+'|'+cap).encode()).hexdigest(),'instagram_trend':True})
    except Exception:
        pass
    if not fresh: raise SystemExit('No fresh RSS/Instagram items found.')
    today=time.strftime('%Y-%m-%d'); work=OUT/today
    made=0
    for item in fresh:
        if made>=limit: break
        slug=re.sub(r'[^A-Za-z0-9]+','_',item['title'])[:50].strip('_') or 'news'
        base=work/f'{slug}_{made+1}'
        card=base.with_suffix('.jpg'); video=base.with_suffix('.mp4')
        source_image=work/f'{slug}_{made+1}_source.jpg'
        media=commons_image(item,source_image) if not item.get('instagram_trend') else None
        make_card(item,card,media['path'] if media else None)
        make_video(card,video,item)
        if media:
            item['media_license']=media['license']
            item['media_artist']=media['artist']
            item['media_source']=media['page']
        record={**item,'date':today,'image':str(card.relative_to(ROOT)),'video':str(video.relative_to(ROOT)),'caption':item['title']+'\n\n'+commentary(item['category'],item['title'])+'\n\nSource: '+item['link']+
            (('\n\nImage credit: '+item.get('media_artist','')+' — '+item.get('media_license','')+
              '\nImage source: '+item.get('media_source','')) if item.get('media_source') else
             '\n\nVisual: original generated card (no reusable news photo found).'),'status':'ready','created_at':int(time.time())}
        state.setdefault('news',[]).append(record); made+=1
        print('NEWS READY:',record['video'])
        if media: print('NEWS IMAGE:', media['page'], media['license'])
    save(STATE,state); print(f'News generated: {made}/{limit}')


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--daily',action='store_true'); ap.add_argument('--limit',type=int,default=2)
    a=ap.parse_args()
    if a.daily: generate(max(1,min(5,a.limit)))
    else: ap.print_help()

if __name__=='__main__': main()
