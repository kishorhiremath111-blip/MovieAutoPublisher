import bpy
import math
from mathutils import Vector
from pathlib import Path

ROOT = Path.home() / "JUNGLE_MASTI"
OUTPUT = ROOT / "Jungle_Masti_Funny_Mango_Heist.mp4"
ROOT.mkdir(parents=True, exist_ok=True)

# Clean scene
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials):
    pass

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in {x.identifier for x in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items} else "BLENDER_EEVEE"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 70
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 360
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "HIGH"
scene.render.ffmpeg.audio_codec = "AAC"
scene.render.filepath = str(OUTPUT)
scene.view_settings.look = "AgX - Medium High Contrast" if hasattr(scene.view_settings, "look") else "Medium High Contrast"

# ---------- Materials ----------
def mat(name, color, rough=0.55, metallic=0.0):
    m=bpy.data.materials.new(name)
    m.use_nodes=True
    bs=m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value=(*color,1)
    bs.inputs["Roughness"].default_value=rough
    bs.inputs["Metallic"].default_value=metallic
    return m

grass=mat("Rich jungle grass",(0.025,0.18,0.045),0.9)
bark=mat("Warm bark",(0.16,0.045,0.015),0.95)
leaf=mat("Glossy emerald leaf",(0.015,0.32,0.07),0.45)
lime=mat("Fresh lime leaf",(0.16,0.5,0.035),0.42)
fur=mat("Monty premium chestnut fur",(0.26,0.065,0.018),0.72)
tan=mat("Monty warm face",(0.78,0.44,0.20),0.72)
pink=mat("Ear pink",(0.55,0.12,0.08),0.7)
white=mat("Eye white",(1,0.98,0.88),0.3)
black=mat("Pupil",(0.008,0.004,0.002),0.18)
green=mat("Explorer vest",(0.01,0.22,0.055),0.5)
gold=mat("Mango gold",(1.0,0.36,0.008),0.28)
red=mat("Mango red",(0.9,0.04,0.01),0.35)

def smooth(o):
    if o.type=="MESH":
        for p in o.data.polygons: p.use_smooth=True
    return o

def sphere(name,loc,scale,material,parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, location=loc)
    o=bpy.context.object; o.name=name; o.scale=scale; o.data.materials.append(material); smooth(o)
    if parent: o.parent=parent
    return o

def cube(name,loc,scale,material,parent=None,bevel=0.12):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o=bpy.context.object; o.name=name; o.scale=scale; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(material)
    b=o.modifiers.new("Rounded soft edges","BEVEL"); b.width=bevel; b.segments=4
    smooth(o)
    if parent:o.parent=parent
    return o

def cyl(name,loc,radius,depth,material,parent=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=radius,depth=depth,location=loc)
    o=bpy.context.object;o.name=name;o.data.materials.append(material)
    b=o.modifiers.new("Soft bevel","BEVEL");b.width=0.08;b.segments=3
    if parent:o.parent=parent
    return o

# ---------- World and jungle ----------
world=bpy.data.worlds.new("Cinematic Jungle World")
scene.world=world; world.use_nodes=True
world.node_tree.nodes["Background"].inputs[0].default_value=(0.008,0.025,0.012,1)
world.node_tree.nodes["Background"].inputs[1].default_value=0.28

bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-0.1))
bpy.context.object.data.materials.append(grass)

for i,(x,y,h,s) in enumerate([(-7,3,6,1.3),(-4,5,5.5,1.1),(5,4,7,1.5),(7,1,5.5,1.2),(0,8,8,1.7),(-8,-1,5,1.1)]):
    cyl("Jungle trunk", (x,y,h/2),0.30*s,h,bark)
    for dx,dy,dz,sc in [(0,0,0.7,1.3),(-0.6,0.2,1.1,0.9),(0.65,-0.2,1.0,0.95)]:
        sphere("Layered jungle canopy",(x+dx,y+dy,h+dz),(sc*s,sc*s,sc*s),leaf if (i+int(dx*10))%2 else lime)

# Mango pedestal
cyl("Mango pedestal",(2.9,0.35,0.35),0.52,0.7,bark)
mango=sphere("Hero mango",(2.9,0.35,1.18),(0.5,0.38,0.68),gold)
mango.rotation_euler[1]=math.radians(-18)
sphere("Mango rosy cheek",(3.18,0.06,1.22),(0.14,0.08,0.34),red)

# ---------- Monty with separate animated body parts ----------
root=bpy.data.objects.new("MONTY_ROOT",None);scene.collection.objects.link(root)
root.location=(-3.8,0,0)

body=sphere("Monty body",(0,0,1.55),(0.65,0.52,0.82),fur,root)
sphere("Monty belly",(0,-0.49,1.5),(0.46,0.10,0.57),tan,root)
sphere("Monty vest",(0,-0.55,1.63),(0.52,0.08,0.55),green,root)

head=sphere("Monty head",(0,-0.02,2.72),(0.73,0.60,0.70),fur,root)
sphere("Monty muzzle",(0,-0.56,2.48),(0.42,0.15,0.28),tan,head)
sphere("Monty nose",(0,-0.71,2.59),(0.11,0.055,0.075),black,head)

eyes=[]; pupils=[]; lids=[]
for side in (-1,1):
    sphere("Monty ear",(side*0.67,-0.02,2.78),(0.23,0.17,0.28),fur,head)
    sphere("Monty inner ear",(side*0.69,-0.17,2.78),(0.13,0.04,0.17),pink,head)
    eye=sphere("Monty expressive eye",(side*0.27,-0.57,2.78),(0.16,0.07,0.21),white,head)
    pupil=sphere("Monty moving pupil",(side*0.27,-0.64,2.77),(0.075,0.035,0.105),black,head)
    lid=sphere("Monty blink lid",(side*0.27,-0.655,2.87),(0.17,0.025,0.04),fur,head)
    eyes.append(eye);pupils.append(pupil);lids.append(lid)

# mouth smile as dark flattened sphere
mouth=sphere("Monty smile",(0,-0.695,2.37),(0.23,0.025,0.055),black,head)

arms=[]; hands=[]
for side in (-1,1):
    pivot=bpy.data.objects.new("Monty arm pivot",None);scene.collection.objects.link(pivot);pivot.parent=root;pivot.location=(side*0.55,-0.02,1.93)
    arm=sphere("Monty animated arm",(0,0,-0.38),(0.20,0.22,0.55),fur,pivot)
    arm.rotation_euler[1]=side*math.radians(-20)
    hand=sphere("Monty animated hand",(side*0.12,-0.05,-0.92),(0.20,0.17,0.18),tan,pivot)
    arms.append(pivot);hands.append(hand)

legs=[]
for side in (-1,1):
    pivot=bpy.data.objects.new("Monty leg pivot",None);scene.collection.objects.link(pivot);pivot.parent=root;pivot.location=(side*0.28,0,0.98)
    sphere("Monty animated leg",(0,0,-0.32),(0.24,0.25,0.48),fur,pivot)
    sphere("Monty foot",(0,-0.16,-0.82),(0.30,0.40,0.17),tan,pivot)
    legs.append(pivot)

# Tail curve
curve=bpy.data.curves.new("Monty animated tail","CURVE");curve.dimensions="3D";curve.bevel_depth=0.09;curve.bevel_resolution=5
sp=curve.splines.new("BEZIER");sp.bezier_points.add(3)
for p,co in zip(sp.bezier_points,[(-0.45,0.32,1.35),(-1.05,0.38,1.05),(-1.45,0.30,1.52),(-1.25,0.3,1.95)]):
    p.co=co;p.handle_left_type="AUTO";p.handle_right_type="AUTO"
tail=bpy.data.objects.new("Monty tail",curve);scene.collection.objects.link(tail);curve.materials.append(fur);tail.parent=root

# ---------- Animation helpers ----------
def keys(obj,attr,values):
    for f,v in values:
        setattr(obj,attr,v);obj.keyframe_insert(data_path=attr,frame=f)

# Root sneak/run + body bounce
keys(root,"location",[(1,(-3.8,0,0)),(120,(-1.2,0,0)),(205,(-1.2,0,0)),(360,(4.9,0,0))])
for f,z in [(1,0),(18,0.10),(36,0),(54,0.10),(72,0),(90,0.10),(108,0),(126,0.10),(144,0),(162,0.08),(180,0),(198,0.12),(216,0),(234,0.16),(252,0),(270,0.18),(288,0),(306,0.15),(324,0),(342,0.12),(360,0)]:
    body.location.z=1.55+z;body.keyframe_insert(data_path="location",frame=f,index=2)

# Head look, surprise and panic
for f,rot in [(1,(0,0,0)),(80,(0,math.radians(8),math.radians(-5))),(150,(0,math.radians(-10),math.radians(6))),(205,(math.radians(-8),0,0)),(230,(math.radians(8),math.radians(12),0)),(360,(0,0,math.radians(-8)))]:
    head.rotation_euler=rot;head.keyframe_insert(data_path="rotation_euler",frame=f)

# Arm waves + running swings
for idx,arm in enumerate(arms):
    side=-1 if idx==0 else 1
    vals=[]
    for f in range(1,361,18):
        phase=math.sin((f/18.0)+(idx*math.pi))
        amp=0.35 if f<205 else 0.75
        vals.append((f,(math.radians(phase*amp*45),0,math.radians(side*phase*18))))
    keys(arm,"rotation_euler",vals)

# Legs walk/run
for idx,leg in enumerate(legs):
    phase0=idx*math.pi
    vals=[]
    for f in range(1,361,12):
        amp=18 if f<205 else 42
        a=math.sin(f/12.0+phase0)*amp
        vals.append((f,(math.radians(a),0,0)))
    keys(leg,"rotation_euler",vals)

# Eyes look around
for idx,p in enumerate(pupils):
    base=(-1 if idx==0 else 1)*0.27
    for f,dx,dz in [(1,0,0),(75,0.03,0.02),(150,-0.02,0.01),(205,0.02,-0.02),(235,-0.03,0.04),(360,0,0)]:
        p.location=(base+dx,-0.64,2.77+dz);p.keyframe_insert(data_path="location",frame=f)

# Blink by scaling lids vertically
for lid in lids:
    for f,sc in [(1,(1,1,0.2)),(58,(1,1,0.2)),(61,(1,1,4.5)),(64,(1,1,0.2)),(148,(1,1,0.2)),(151,(1,1,4.5)),(154,(1,1,0.2)),(232,(1,1,0.2)),(235,(1,1,4.5)),(238,(1,1,0.2))]:
        lid.scale=sc;lid.keyframe_insert(data_path="scale",frame=f)

# Mango funny wiggle
for f,a,s in [(1,0,1),(170,0,1),(185,math.radians(18),1.12),(200,math.radians(-18),0.92),(215,0,1),(360,0,1)]:
    mango.rotation_euler[2]=a;mango.scale=(0.5*s,0.38*s,0.68*s)
    mango.keyframe_insert(data_path="rotation_euler",frame=f);mango.keyframe_insert(data_path="scale",frame=f)

# Smooth interpolation
for obj in [root,body,head,*arms,*legs,*pupils,*lids,mango]:
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:kp.interpolation="BEZIER"

# ---------- Cinematic camera ----------
cam_data=bpy.data.cameras.new("Cinematic camera");cam=bpy.data.objects.new("Cinematic camera",cam_data);scene.collection.objects.link(cam)
scene.camera=cam;cam_data.lens=52
for f,loc,target in [(1,(-0.2,-14,5.0),(-1.2,0,1.8)),(150,(0.2,-12.5,4.2),(-0.4,0,1.9)),(205,(0.6,-10.8,4.4),(0.5,0,2.0)),(360,(1.5,-12.5,4.8),(2.0,0,1.9))]:
    cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat("-Z","Y").to_euler()
    cam.keyframe_insert(data_path="location",frame=f);cam.keyframe_insert(data_path="rotation_euler",frame=f)

# ---------- Premium lighting ----------
def area(name,loc,energy,size,color):
    data=bpy.data.lights.new(name,"AREA");data.energy=energy;data.shape="DISK";data.size=size;data.color=color
    o=bpy.data.objects.new(name,data);scene.collection.objects.link(o);o.location=loc
    o.rotation_euler=(Vector((0,0,1.8))-o.location).to_track_quat("-Z","Y").to_euler()

area("Warm key",(-3,-6,9),2200,7,(1.0,0.72,0.42))
area("Cool fill",(5,-1,6),1500,6,(0.35,0.65,1.0))
area("Golden rim",(5,5,8),2600,5,(1.0,0.35,0.08))

# Volumetric-ish mist cards
mist=mat("Soft mist",(0.18,0.35,0.22),1.0)
for y in (2.5,5.0):
    cube("Jungle atmosphere",(0,y,2.0),(8,0.04,1.8),mist,bevel=0.02)

# ---------- Title ----------
font_curve=bpy.data.curves.new("Opening title","FONT");font_curve.body="MONTY'S MANGO HEIST!";font_curve.align_x="CENTER";font_curve.size=0.65
title=bpy.data.objects.new("Opening title",font_curve);scene.collection.objects.link(title);title.location=(0,-5.0,4.7);title.rotation_euler=(math.radians(90),0,0);font_curve.materials.append(gold)
for f,scale in [(1,(0.1,0.1,0.1)),(18,(1.2,1.2,1.2)),(42,(1,1,1)),(72,(0.01,0.01,0.01))]:
    title.scale=scale;title.keyframe_insert(data_path="scale",frame=f)

scene.frame_set(1)
print("Rendering premium animated Jungle Masti cartoon:",OUTPUT)
bpy.ops.render.render(animation=True)
if not OUTPUT.exists() or OUTPUT.stat().st_size==0: raise RuntimeError("MP4 missing")
print("VIDEO_READY",OUTPUT,OUTPUT.stat().st_size)
