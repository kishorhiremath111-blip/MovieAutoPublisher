"""Clean motivational Shorts audio: deep male voice + ONE finger-snap accent after hook + suitable background music.
No paper-scratch, no whoosh on every image change."""
import os, glob, random, subprocess

SR = 44100
SFX_DIR = os.path.join("work", "sfx")
MUSIC_VOL = float(os.environ.get("MUSIC_VOL", "0.18"))
STEREO = f"aformat=sample_rates={SR}:channel_layouts=stereo"

def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg fail: {p.stderr[-1200:]}")

def _synth_snap():
    os.makedirs(SFX_DIR, exist_ok=True)
    out = os.path.join(SFX_DIR, "finger_snap.wav")
    if os.path.exists(out):
        return out
    # Short, dry finger-snap style transient: no paper/scratch texture.
    _run([
        "ffmpeg","-y","-hide_banner","-loglevel","error",
        "-f","lavfi","-i",f"anoisesrc=d=0.11:c=white:r={SR}:a=0.9",
        "-af",f"highpass=f=1800,lowpass=f=9500,afade=t=out:st=0.045:d=0.065,volume=1.15,{STEREO}",
        out
    ])
    return out

def _synth_impact():
    os.makedirs(SFX_DIR, exist_ok=True)
    out=os.path.join(SFX_DIR,"impact.wav")
    if os.path.exists(out): return out
    _run([
        "ffmpeg","-y","-hide_banner","-loglevel","error",
        "-f","lavfi","-i",f"aevalsrc='0.7*sin(2*PI*62*t)*exp(-t*7)+0.3*sin(2*PI*95*t)*exp(-t*10)':d=0.55:s={SR}",
        "-af",f"afade=t=out:st=0.35:d=0.2,alimiter=limit=0.9,{STEREO}",out
    ])
    return out

def get_sfx(name):
    mine=[]
    for ext in ("mp3","wav","m4a","ogg"):
        mine += glob.glob(f"sfx/{name}*.{ext}")
    if mine:
        return random.choice(mine)
    return _synth_snap() if name=="snap" else _synth_impact()

def music_track(total):
    mine=[]
    for ext in ("mp3","m4a","wav","ogg"):
        mine += glob.glob(f"music/*.{ext}")
    if mine:
        t=random.choice(mine)
        print("background music:",t)
        return t,True

    # Soft emotional cinematic bed, generated locally; voice remains the focus.
    os.makedirs(SFX_DIR, exist_ok=True)
    out=os.path.join("work","background_music.wav")
    d=total+3
    expr_l="(0.16*sin(2*PI*55*t)+0.10*sin(2*PI*82.41*t)+0.08*sin(2*PI*110*t)+0.05*sin(2*PI*164.81*t))*(0.72+0.28*sin(2*PI*0.045*t))"
    expr_r="(0.16*sin(2*PI*55.2*t)+0.10*sin(2*PI*82.7*t)+0.08*sin(2*PI*110.4*t)+0.05*sin(2*PI*165.2*t))*(0.72+0.28*sin(2*PI*0.043*t+0.8))"
    _run([
        "ffmpeg","-y","-hide_banner","-loglevel","error",
        "-f","lavfi","-i",f"aevalsrc='{expr_l}|{expr_r}':d={d:.2f}:s={SR}",
        "-af","lowpass=f=1200,aecho=0.8:0.65:420|820:0.16|0.10",
        out
    ])
    print("background music: soft cinematic emotional bed")
    return out,False

def plan_events(scenes,timings,total):
    events=[]
    if not timings:
        return events

    # Exactly one satisfying snap immediately AFTER the hook ends.
    hook_end=max(0.05, timings[0]["end"]-0.20)
    events.append((get_sfx("snap"), hook_end, 1.0, None))

    # Only use additional effects when the script explicitly asks for impact.
    for i,s in enumerate(scenes[1:], start=1):
        tags=[t.strip().lower() for t in (s.get("sfx") or "").split(",") if t.strip()]
        if "impact" in tags:
            events.append((get_sfx("impact"), max(0.0,timings[i]["start"]), 0.55, None))
    return events

def mix_final(joined,events,total,out):
    music,user_music=music_track(total)
    cmd=["ffmpeg","-y","-hide_banner","-loglevel","error","-i",joined]
    if user_music:
        cmd += ["-stream_loop","-1"]
    cmd += ["-i",music]

    fc=[
        f"[0:a]highpass=f=70,equalizer=f=120:t=h:w=120:g=2.5,equalizer=f=2600:t=q:w=1.4:g=1.3,acompressor=threshold=0.12:ratio=2.4:attack=12:release=160,{STEREO},asplit=2[voice][voice_sc]",
        f"[1:a]{STEREO},atrim=0:{total+1:.2f},volume={MUSIC_VOL},afade=t=in:d=1.0,afade=t=out:st={max(total-2.0,0):.2f}:d=2.0[music]",
        "[music][voice_sc]sidechaincompress=threshold=0.035:ratio=12:attack=20:release=500[ducked]"
    ]
    labels=["[voice]","[ducked]"]

    for k,(path,start,gain,dur) in enumerate(events):
        idx=2+k
        cmd += ["-i",path]
        ms=max(0,int(start*1000))
        fc.append(f"[{idx}:a]{STEREO},volume={gain},adelay={ms}|{ms}[fx{k}]")
        labels.append(f"[fx{k}]")

    fc.append("".join(labels)+f"amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95,loudnorm=I=-15:TP=-1.5:LRA=8[a]")
    cmd += ["-filter_complex",";".join(fc),"-map","0:v","-map","[a]",
            "-c:v","copy","-c:a","aac","-b:a","256k","-ar","44100",
            "-t",f"{total:.2f}",out]
    _run(cmd)
