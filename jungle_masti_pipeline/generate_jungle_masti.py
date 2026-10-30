#!/usr/bin/env python3
# Jungle Masti: Tripo 3D model -> auto-rig -> animation -> browser WebM recorder.
# Tripo generates animated GLB files, not a finished MP4. This script also creates a
# local Three.js viewer that can record the animated GLB as WebM in supported browsers.

import os, sys, time, json, getpass, subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

BASE = "https://openapi.tripo3d.ai/v3"
ROOT = Path.home() / "JUNGLE_MASTI"
CHAR_DIR = ROOT / "characters"
OUT_DIR = ROOT / "animated"
CHAR_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROMPT = (
    "A single adorable stylized 3D animated family-film baby monkey character, "
    "full body, standing upright on two legs in a neutral A-pose, arms slightly "
    "away from torso, legs separated, symmetrical humanoid anatomy, warm chestnut "
    "brown soft fur, cream beige face and belly, large expressive amber-brown eyes, "
    "rounded cheeks, small ears, friendly mischievous smile, long curved tail, "
    "clearly separated arms and legs, clean production-ready geometry, detailed "
    "PBR materials, cinematic character design, isolated neutral studio background. "
    "No props, no clothes, no text, no watermark, no extra characters."
)

SESSION = requests.Session()
API_KEY = None

def stop(message):
    print("\\n[STOP]", message)
    sys.exit(1)

def headers():
    return {"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"}

def parse_response(response):
    try:
        data = response.json()
    except Exception:
        stop(f"Non-JSON response (HTTP {response.status_code}): {response.text[:500]}")
    if not response.ok:
        stop(f"HTTP {response.status_code}: {json.dumps(data, ensure_ascii=False)[:1500]}")
    if data.get("code") not in (0, None):
        stop("Tripo API error: " + json.dumps(data, ensure_ascii=False)[:1500])
    return data.get("data", data)

def post_task(endpoint, payload):
    try:
        response = SESSION.post(BASE + endpoint, headers=headers(), json=payload, timeout=120)
    except requests.RequestException as exc:
        stop(f"Network error submitting {endpoint}: {exc}")
    data = parse_response(response)
    task_id = data.get("task_id")
    if not task_id:
        stop("API response has no task_id: " + json.dumps(data)[:1000])
    print("Task submitted:", task_id)
    return task_id

def wait_task(task_id, label, timeout_seconds=900):
    started = time.time()
    last = None
    while time.time() - started < timeout_seconds:
        try:
            response = SESSION.get(f"{BASE}/tasks/{task_id}", headers=headers(), timeout=60)
            data = parse_response(response)
        except requests.RequestException as exc:
            print("\\nTemporary status-check error:", exc)
            time.sleep(4)
            continue
        status = data.get("status", "unknown")
        progress = data.get("progress", 0)
        if status != last or progress:
            print(f"\\r{label}: {status} {progress}%", end="", flush=True)
            last = status
        if status == "success":
            print()
            return data
        if status in ("failed", "cancelled", "banned"):
            print()
            stop(f"{label} failed: " + json.dumps(data, ensure_ascii=False)[:1500])
        time.sleep(3)
    stop(f"{label} timed out. Task ID: {task_id}. Check Tripo task console.")

def download_file(url, destination):
    try:
        with SESSION.get(url, stream=True, timeout=180) as response:
            response.raise_for_status()
            with open(destination, "wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    except Exception as exc:
        stop(f"Download failed for {destination.name}: {exc}")
    if not destination.exists() or destination.stat().st_size == 0:
        stop("Downloaded file is empty: " + str(destination))
    print("Saved:", destination, f"({destination.stat().st_size / 1048576:.1f} MB)")

def generate_character():
    print("\\n[1/4] Generating Monty 3D character...")
    payload = {
        "prompt": PROMPT,
        "model": "v3.1-20260211",
        "texture": True,
        "pbr": True,
        "texture_quality": "detailed",
        "face_limit": 80000
    }
    task_id = post_task("/generation/text-to-model", payload)
    result = wait_task(task_id, "Character generation")
    model_url = result.get("output", {}).get("model_url")
    if not model_url:
        stop("Generation succeeded but output.model_url is missing.")
    original = CHAR_DIR / "Monty_original.glb"
    download_file(model_url, original)
    return task_id, original

def check_and_rig(source_task_id):
    print("\\n[2/4] Checking rig compatibility...")
    check_id = post_task("/animations/rig-check", {"input": source_task_id})
    check = wait_task(check_id, "Rig compatibility check")
    output = check.get("output", {})
    if output.get("riggable") is False:
        stop("Model is not riggable. Try a simpler upright A-pose character.")
    rig_type = output.get("rig_type") or "biped"
    print("Rig type:", rig_type)

    print("\\n[3/4] Auto-rigging Monty...")
    rig_payload = {
        "input": source_task_id,
        "model": "v3.0-20260909",
        "rig_type": rig_type,
        "spec": "tripo"
    }
    rig_id = post_task("/animations/rig", rig_payload)
    wait_task(rig_id, "Auto-rig")
    return rig_id

def animate(rig_task_id):
    print("\\n[4/4] Creating idle, walk and run animations...")
    presets = [
        ("idle", "preset:idle"),
        ("walk", "preset:walk"),
        ("run", "preset:run"),
    ]
    saved = []
    for label, preset in presets:
        print(f"\\nCreating {label} animation...")
        animation_id = post_task(
            "/animations/retarget",
            {"input": rig_task_id, "animation": preset}
        )
        result = wait_task(animation_id, f"{label.title()} animation")
        model_url = result.get("output", {}).get("model_url")
        if not model_url:
            stop(f"{label} animation succeeded but output.model_url is missing.")
        destination = OUT_DIR / f"Monty_{label}.glb"
        download_file(model_url, destination)
        saved.append(destination)
    return saved

def write_viewer():
    html = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Jungle Masti 3D Studio</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#10131b;color:#f5f7ff;font:15px system-ui}
header{padding:14px 16px;background:#191f2b;border-bottom:1px solid #30394a}
h1{font-size:18px;margin:0}p{color:#b7c1d4;font-size:13px;margin:5px 0 0}
main{padding:12px;max-width:900px;margin:auto}
#stage{height:54vh;min-height:300px;background:linear-gradient(#263b52,#101722);border-radius:14px;overflow:hidden}
.controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:12px}
button,.filelabel{border:0;border-radius:10px;padding:13px 10px;background:#34445d;color:white;font-weight:650;text-align:center}
button:disabled{opacity:.45}.primary{background:#147d65}.warn{background:#8c4c28}
input[type=file]{display:none}.status{padding:10px 2px;color:#b9c5d9;font-size:13px}
.note{background:#1a2230;padding:12px;border-radius:10px;color:#c8d2e2;font-size:12px;line-height:1.5;margin-top:12px}
</style></head><body>
<header><h1>JUNGLE MASTI 3D STUDIO</h1><p>Monty character animation viewer and WebM recorder</p></header>
<main><div id="stage"></div>
<div class="controls">
<label class="filelabel" for="modelFile">Choose animated GLB</label><input id="modelFile" type="file" accept=".glb,.gltf">
<button id="playBtn" disabled>Play animation</button><button id="stopBtn" disabled>Pause</button>
<button id="recordBtn" class="primary" disabled>Record video</button><button id="finishBtn" class="warn" disabled>Stop & save video</button>
</div>
<div id="status" class="status">Choose an animated GLB to start.</div>
<div class="note">This studio records WebM, not MP4. Import the WebM into VN and export MP4. For a 20-30 minute episode, record many short shots and edit them together. If browser recording is unsupported, use Android screen recorder.</div>
</main>
<script type="importmap">
{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}
</script>
<script type="module">
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
const stage=document.getElementById('stage'),status=document.getElementById('status');
const scene=new THREE.Scene();scene.background=new THREE.Color(0x263b52);scene.fog=new THREE.Fog(0x263b52,18,45);
const camera=new THREE.PerspectiveCamera(38,stage.clientWidth/stage.clientHeight,.1,1000);camera.position.set(3,2.2,5);
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setSize(stage.clientWidth,stage.clientHeight);
renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.15;stage.appendChild(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xd9ecff,0x35402d,2));
const key=new THREE.DirectionalLight(0xffe1bd,3);key.position.set(4,7,5);scene.add(key);
const rim=new THREE.DirectionalLight(0x75baff,1.8);rim.position.set(-5,3,-4);scene.add(rim);
const ground=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.MeshStandardMaterial({color:0x334b37,roughness:1}));
ground.rotation.x=-Math.PI/2;ground.position.y=-.02;scene.add(ground);
const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,1,0);controls.enableDamping=true;
const loader=new GLTFLoader();let mixer=null,clips=[],model=null,recorder=null,chunks=[];
const play=document.getElementById('playBtn'),pause=document.getElementById('stopBtn');
const record=document.getElementById('recordBtn'),finish=document.getElementById('finishBtn');
function say(t){status.textContent=t}
document.getElementById('modelFile').addEventListener('change',e=>{
 const file=e.target.files[0];if(!file)return;
 if(model)scene.remove(model);if(mixer){mixer.stopAllAction();mixer=null}
 const url=URL.createObjectURL(file);say('Loading '+file.name+' ...');
 loader.load(url,g=>{
  model=g.scene;scene.add(model);clips=g.animations||[];
  const box=new THREE.Box3().setFromObject(model),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());
  model.position.sub(center);model.position.y-=box.min.y;
  const max=Math.max(size.x,size.y,size.z)||2;camera.position.set(max*1.5,max,max*2);
  controls.target.set(0,size.y*.48,0);controls.update();mixer=new THREE.AnimationMixer(model);
  play.disabled=!clips.length;pause.disabled=!clips.length;record.disabled=false;
  say('Loaded '+file.name+' | clips: '+clips.length+(clips.length?' | '+clips.map(c=>c.name).join(', '):''));
  if(clips.length){mixer.clipAction(clips[0]).play();say('Playing '+clips[0].name)}
  URL.revokeObjectURL(url);
 },undefined,err=>say('GLB load error: '+err.message));
});
play.onclick=()=>{if(mixer&&clips.length){mixer.stopAllAction();mixer.clipAction(clips[0]).reset().play();say('Playing '+clips[0].name)}};
pause.onclick=()=>{if(mixer)mixer.stopAllAction();say('Animation paused')};
record.onclick=()=>{
 if(!renderer.domElement.captureStream||!window.MediaRecorder){say('Recording unsupported. Use Android screen recorder.');return}
 const stream=renderer.domElement.captureStream(30);chunks=[];
 let mime='video/webm;codecs=vp9';if(!MediaRecorder.isTypeSupported(mime))mime='video/webm';
 if(!MediaRecorder.isTypeSupported(mime)){say('WebM recording unsupported. Use Android screen recorder.');return}
 recorder=new MediaRecorder(stream,{mimeType:mime});
 recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
 recorder.onstop=()=>{const blob=new Blob(chunks,{type:'video/webm'}),a=document.createElement('a');
 a.href=URL.createObjectURL(blob);a.download='Jungle_Masti_Monty_Scene.webm';a.click();say('Saved Jungle_Masti_Monty_Scene.webm')};
 recorder.start();record.disabled=true;finish.disabled=false;say('Recording... tap Stop & save video when ready.');
};
finish.onclick=()=>{if(recorder&&recorder.state!=='inactive')recorder.stop();record.disabled=false;finish.disabled=true};
const clock=new THREE.Clock();function frame(){requestAnimationFrame(frame);if(mixer)mixer.update(Math.min(clock.getDelta(),.05));controls.update();renderer.render(scene,camera)}frame();
new ResizeObserver(()=>{const w=stage.clientWidth,h=stage.clientHeight;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h)}).observe(stage);
</script></body></html>'''
    viewer = ROOT / "Jungle_Masti_3D_Studio.html"
    viewer.write_text(html, encoding="utf-8")
    return viewer

def main():
    global API_KEY
    print("=" * 56)
    print("JUNGLE MASTI - TRIPO 3D ANIMATION PIPELINE")
    print("=" * 56)
    API_KEY = os.environ.get("TRIPO_API_KEY") or getpass.getpass("Tripo API key (hidden): ").strip()
    if not API_KEY:
        stop("API key missing.")
    print("\\nThis uses Tripo credits for model generation, rigging and animation.")
    print("It creates animated GLB files plus a browser WebM recorder, not a direct MP4.")
    if input("Continue? [y/N]: ").strip().lower() != "y":
        print("Cancelled; no generation request sent.")
        return
    source_task, original = generate_character()
    rig_task = check_and_rig(source_task)
    animated = animate(rig_task)
    viewer = write_viewer()
    print("\\nDONE! Files saved under:", ROOT)
    print("Original model:", original)
    print("Animated models:")
    for item in animated:
        print(" -", item)
    print("Viewer:", viewer)
    print("\\nTo open the studio:")
    print("cd ~/JUNGLE_MASTI && python -m http.server 8000")
    print("Then open Chrome: http://127.0.0.1:8000/Jungle_Masti_3D_Studio.html")
    print("Choose an animated GLB from ~/JUNGLE_MASTI/animated, then Record video.")
    print("The browser saves WebM; use VN to export MP4.")

if __name__ == "__main__":
    main()