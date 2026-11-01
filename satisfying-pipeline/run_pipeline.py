#!/usr/bin/env python3
"""Render, quality-check, and publish one unique satisfying topic."""
import datetime, json, os, subprocess, sys
from pathlib import Path
import topics
ROOT=Path(__file__).resolve().parent
STATE=ROOT/"state"/"state.json"
HISTORY=ROOT/"state"/"used_topics.jsonl"
CONFIG=ROOT/"config.json"
def env_true(name):
    return os.getenv(name,"").strip().lower() in ("1","true","yes")
def load_json(path,default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
def save_state(st):
    STATE.parent.mkdir(exist_ok=True)
    tmp=STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st,indent=2),encoding="utf-8")
    tmp.replace(STATE)
def probe(path):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type","-of","json",str(path)],capture_output=True,text=True)
    info=json.loads(r.stdout or "{}")
    return {s.get("codec_type") for s in info.get("streams",[])},float(info.get("format",{}).get("duration",0) or 0)
def main():
    cfg=load_json(CONFIG,{})
    dry=env_true("DRY_RUN")
    st=load_json(STATE,{"counter":0,"last_upload_date":None,"uploads":0})
    today=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    if not dry and st.get("last_upload_date")==today:
        print("Aaj ka public Short pehle hi publish ho chuka hai. Skip.")
        return 0
    topic=topics.build_topic(st["counter"],cfg.get("target_seconds",28)); p=topic["params"]
    print("Topic #%d %s"%(topic["counter"],topic["topic_id"]))
    print("Title:",topic["title"])
    width,height=int(cfg.get("width",720)),int(cfg.get("height",1280))
    if os.getenv("RES")=="1080": width,height=1080,1920
    fps=int(cfg.get("fps",30)); out_dir=ROOT/"out"; out_dir.mkdir(parents=True,exist_ok=True)
    video=out_dir/(topic["topic_id"]+".mp4")
    from render_video import render_video
    render_video(p,video,width,height,fps,ROOT/"work")
    kinds,dur=probe(video)
    if not {"video","audio"}<=kinds or dur<10 or video.stat().st_size<200_000:
        raise RuntimeError("Quality check fail: kinds=%s dur=%.1f size=%d"%(kinds,dur,video.stat().st_size if video.exists() else 0))
    print("Quality check OK: %.1fs, %.1f MB"%(dur,video.stat().st_size/1e6))
    if dry:
        print("DRY RUN: upload nahi hua; topic consume nahi hua. Video:",video)
        return 0
    from upload_youtube import upload_video
    video_id=upload_video(video,topic["title"],topic["description"],topic["tags"],privacy="public",made_for_kids=cfg.get("made_for_kids",True),category_id=cfg.get("category_id","24"))
    print("PUBLIC SHORT UPLOADED: https://youtube.com/shorts/%s"%video_id)
    st["counter"]+=1; st["last_upload_date"]=today; st["uploads"]=st.get("uploads",0)+1
    st["last_video_id"]=video_id; st["last_topic_id"]=topic["topic_id"]
    save_state(st)
    HISTORY.parent.mkdir(parents=True,exist_ok=True)
    with HISTORY.open("a",encoding="utf-8") as f:
        f.write(json.dumps({"counter":topic["counter"],"topic_id":topic["topic_id"],"title":topic["title"],"video_id":video_id,"date":today})+"\n")
    video.unlink(missing_ok=True)
    print("Topic %s consumed; local MP4 deleted. Next topic counter=%d"%(topic["topic_id"],st["counter"]))
    return 0
if __name__=="__main__": sys.exit(main())
