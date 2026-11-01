"""Pro-editor jaisa audio: synth sound effects + dark cinematic music pad + voice polish + ducking.
Sab FFmpeg se banta hai (koi download/key/copyright nahi). Tumhari apni files sfx/ aur music/ me hon to wahi use hoti hain."""
import os, glob, random, subprocess

SR = 44100
SFX_DIR = os.path.join("work", "sfx")
MUSIC_VOL = float(os.environ.get("MUSIC_VOL", "0.32"))
GAIN = {"whoosh": 0.45, "impact": 0.95, "riser": 0.55, "heartbeat": 0.55, "rain": 0.28}
AMBIENT = {"heartbeat", "rain"}
STEREO = f"aformat=sample_rates={SR}:channel_layouts=stereo"

def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg fail: {p.stderr[-1200:]}")

def _synth(name):
    os.makedirs(SFX_DIR, exist_ok=True)
    out = os.path.join(SFX_DIR, f"{name}.wav")
    if os.path.exists(out): return out
    f = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if name == "whoosh":
        _run(f + ["-f", "lavfi", "-i", f"anoisesrc=d=1.0:c=white:r={SR}:a=0.9", "-af",
                  "highpass=f=350,lowpass=f=6000,volume='pow(sin(PI*pow(t/1.0,0.75)),2)':eval=frame,"
                  f"aecho=0.8:0.5:35:0.2,{STEREO}", out])
    elif name == "impact":
        _run(f + ["-f", "lavfi", "-i", f"aevalsrc='0.9*sin(2*PI*(42+95*exp(-t*14))*t)*exp(-t*2.4)+0.5*sin(2*PI*30*t)*exp(-t*1.7)':d=2.4:s={SR}",
                  "-f", "lavfi", "-i", f"anoisesrc=d=2.4:c=brown:r={SR}:a=0.7", "-filter_complex",
                  "[1:a]volume='exp(-t*8)':eval=frame[n];[0:a][n]amix=inputs=2:normalize=0,"
                  f"aecho=0.8:0.6:110|260:0.25|0.15,alimiter=limit=0.95,{STEREO}", out])
    elif name == "riser":
        _run(f + ["-f", "lavfi", "-i", f"anoisesrc=d=3.2:c=pink:r={SR}:a=0.8", "-f", "lavfi", "-i",
                  f"aevalsrc='0.4*sin(2*PI*(180*t+(1500/(2*3.2))*t*t))':d=3.2:s={SR}", "-filter_complex",
                  "[0:a]highpass=f=500,volume='pow(t/3.2,2.2)':eval=frame[n];[1:a]volume='pow(t/3.2,2)':eval=frame[c];"
                  f"[n][c]amix=inputs=2:normalize=0,afade=t=out:st=3.15:d=0.05,{STEREO}", out])
    elif name == "heartbeat":
        _run(f + ["-f", "lavfi", "-i",
                  "aevalsrc='0.9*sin(2*PI*58*mod(t,0.9))*exp(-mod(t,0.9)*20)+0.7*gte(mod(t,0.9),0.27)*sin(2*PI*52*(mod(t,0.9)-0.27))*exp(-(mod(t,0.9)-0.27)*22)'"
                  f":d=20:s={SR}", "-af", f"lowpass=f=300,{STEREO}", out])
    elif name == "rain":
        _run(f + ["-f", "lavfi", "-i", f"anoisesrc=d=20:c=pink:r={SR}:a=0.8", "-af",
                  f"highpass=f=800,lowpass=f=9000,tremolo=f=0.3:d=0.15,{STEREO}", out])
    else: raise ValueError(name)
    return out

def get_sfx(name):
    mine=[]
    for ext in ("mp3","wav","m4a","ogg"): mine += glob.glob(f"sfx/{name}*.{ext}")
    return random.choice(mine) if mine else _synth(name)

def music_track(total):
    mine=[]
    for ext in ("mp3","m4a","wav"): mine += glob.glob(f"music/*.{ext}")
    if mine:
        t=random.choice(mine); print("music:",t); return t,True
    os.makedirs(SFX_DIR, exist_ok=True)
    out=os.path.join("work","music_pad.wav"); d=total+4
    left=(" (0.22*sin(2*PI*55*t)+0.16*sin(2*PI*55.4*t)+0.14*sin(2*PI*110*t)+0.10*sin(2*PI*164.81*t)+0.07*sin(2*PI*220.5*t)+0.05*sin(2*PI*261.63*t))*(0.7+0.3*sin(2*PI*0.07*t))")
    right=(" (0.22*sin(2*PI*55.5*t)+0.16*sin(2*PI*55*t)+0.14*sin(2*PI*110.4*t)+0.10*sin(2*PI*165.4*t)+0.07*sin(2*PI*221*t)+0.05*sin(2*PI*262.2*t))*(0.7+0.3*sin(2*PI*0.06*t+1))")
    _run(["ffmpeg","-y","-hide_banner","-loglevel","error","-f","lavfi","-i",f"aevalsrc='{left}|{right}':d={d:.1f}:s={SR}","-af","lowpass=f=900,aecho=0.8:0.8:500|1000:0.3|0.2",out])
    print("music: synth dark pad (apni music/ file daalo to behtar)")
    return out,False

def plan_events(scenes,timings,total):
    ev=[]; n=len(scenes)
    for i,s in enumerate(scenes):
        start=timings[i]["start"]; dur=timings[i]["end"]-start
        tags=[t.strip().lower() for t in (s.get("sfx") or "").split(",") if t.strip()]
        if not tags: tags=["impact"] if i==0 else (["riser","impact"] if i==n-1 and n>2 else ["whoosh"])
        if "none" in tags: continue
        for tg in tags:
            if tg not in GAIN: continue
            if tg=="riser": ev.append((get_sfx("riser"),max(0.0,start-3.2),GAIN["riser"],None))
            elif tg in AMBIENT: ev.append((get_sfx(tg),start,GAIN[tg],dur))
            elif tg=="whoosh": ev.append((get_sfx("whoosh"),max(0.0,start-0.12),GAIN["whoosh"],None))
            else: ev.append((get_sfx("impact"),max(0.0,start-0.02),GAIN["impact"]*(0.75 if i==0 else 1.0),None))
    return ev

def mix_final(joined,events,total,out):
    music,user_music=music_track(total)
    cmd=["ffmpeg","-y","-hide_banner","-loglevel","error","-i",joined]
    if user_music: cmd += ["-stream_loop","-1"]
    cmd += ["-i",music]
    fc=[f"[0:a]highpass=f=70,equalizer=f=120:t=h:w=100:g=3,equalizer=f=3500:t=q:w=1.5:g=2,acompressor=threshold=0.1:ratio=3:attack=5:release=90,aecho=0.8:0.6:45|110:0.14|0.08,{STEREO},asplit=2[v1][v2]",
        f"[1:a]{STEREO},atrim=0:{total+1:.2f},volume={MUSIC_VOL},afade=t=in:d=1.5,afade=t=out:st={max(total-2.5,0):.2f}:d=2.5[m]",
        "[m][v2]sidechaincompress=threshold=0.03:ratio=9:attack=15:release=450:makeup=1[md]"]
    labels=["[v1]","[md]"]
    for k,(path,start,gain,dur) in enumerate(events):
        idx=2+k; cmd += ["-i",path]; ms=max(0,int(start*1000)); trim=""
        if dur: trim=f"atrim=0:{dur:.2f},afade=t=in:d=0.5,afade=t=out:st={max(dur-0.7,0):.2f}:d=0.7,"
        fc.append(f"[{idx}:a]{STEREO},{trim}volume={gain},adelay={ms}|{ms}[s{k}]"); labels.append(f"[s{k}]")
    fc.append("".join(labels)+f"amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0,afade=t=out:st={max(total-1.2,0):.2f}:d=1.2,alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    cmd += ["-filter_complex",";".join(fc),"-map","0:v","-map","[a]","-c:v","copy","-c:a","aac","-b:a","256k","-ar","44100","-t",f"{total:.2f}",out]
    _run(cmd)
