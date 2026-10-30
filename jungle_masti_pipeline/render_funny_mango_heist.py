import bpy
import math
from mathutils import Vector
from pathlib import Path

ROOT = Path.home() / "JUNGLE_MASTI"
MODEL = ROOT / "animated" / "Monty_walk.glb"
OUTPUT = ROOT / "Jungle_Masti_Funny_Mango_Heist.mp4"
if not MODEL.exists():
    raise FileNotFoundError(f"Animated model missing: {MODEL}")

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
engines = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 360
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"
scene.render.ffmpeg.codec = "H264"
scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
scene.render.filepath = str(OUTPUT)
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "Medium High Contrast"

world = bpy.data.worlds.new("Jungle Sky") if not bpy.data.worlds else bpy.data.worlds[0]
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.12, 0.28, 0.42, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.8

def mat(name, color, roughness=0.8):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = roughness
    return m

grass = mat("Jungle grass", (0.055, 0.22, 0.075))
bark = mat("Tree bark", (0.19, 0.075, 0.035))
leaf = mat("Emerald leaves", (0.035, 0.28, 0.09))
lime = mat("Lime leaves", (0.18, 0.42, 0.06))
gold = mat("Golden mango", (1.0, 0.48, 0.025), 0.28)
red = mat("Mango blush", (0.9, 0.12, 0.025), 0.3)
white = mat("Caption white", (1, 1, 1), 0.4)

def sphere(name, loc, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o

def cylinder(name, loc, radius, depth, material):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=depth, location=loc)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    bevel = o.modifiers.new("Soft edges", "BEVEL")
    bevel.width = 0.1
    bevel.segments = 3
    o.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return o

bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.08))
bpy.context.object.data.materials.append(grass)

for x, y, h in [(-5, 2, 5), (-3.8, 4, 4.3), (4.8, 3.5, 5.5), (6, 1.5, 4.5), (0, 7, 6)]:
    cylinder("Jungle tree trunk", (x, y, h/2), 0.32, h, bark)
    sphere("Tree canopy", (x, y, h + 0.6), (1.45, 1.15, 1.25), leaf)
    sphere("Bright leaves", (x - 0.55, y - 0.12, h + 1.1), (0.9, 0.8, 0.8), lime)

cylinder("Mango pedestal", (2.8, 0.25, 0.28), 0.48, 0.55, bark)
mango = sphere("Legendary mango", (2.8, 0.25, 1.05), (0.42, 0.32, 0.58), gold)
mango.rotation_euler[1] = math.radians(-18)
sphere("Mango blush", (3.04, -0.02, 1.12), (0.12, 0.07, 0.3), red)
cylinder("Mango stem", (2.82, 0.25, 1.65), 0.045, 0.2, bark)

# Import Tripo's animated GLB
bpy.ops.import_scene.gltf(filepath=str(MODEL))
imported = list(bpy.context.selected_objects)
if not imported:
    raise RuntimeError("GLB imported but no character objects were selected.")
controller = bpy.data.objects.new("Monty motion controller", None)
scene.collection.objects.link(controller)
for obj in imported:
    matrix = obj.matrix_world.copy()
    obj.parent = controller
    obj.matrix_world = matrix

# Scale character to a consistent height
points = []
for obj in imported:
    if obj.type == "MESH":
        points.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])
if points:
    min_z = min(p.z for p in points)
    max_z = max(p.z for p in points)
    height = max(max_z - min_z, 0.001)
    factor = 2.4 / height
    controller.scale = (factor, factor, factor)
    controller.location.z = -min_z * factor

armatures = [o for o in imported if o.type == "ARMATURE"]
actions = list(bpy.data.actions)
if armatures and actions:
    armatures[0].animation_data_create()
    armatures[0].animation_data.action = actions[-1]
    for fc in actions[-1].fcurves:
        fc.modifiers.new("CYCLES")
else:
    print("WARNING: No imported armature/action; controller movement still renders.")

# Sneak to mango, freeze, then panic-run away
for frame, x in [(1, -4.0), (150, -1.2), (205, -1.2), (360, 5.0)]:
    controller.location.x = x
    controller.keyframe_insert(data_path="location", frame=frame)
if controller.animation_data and controller.animation_data.action:
    for fc in controller.animation_data.action.fcurves:
        for key in fc.keyframe_points:
            key.interpolation = "BEZIER"

# Mango squash-pop gag
for frame, scale in [(1, (0.42, 0.32, 0.58)), (185, (0.52, 0.26, 0.7)), (210, (0.42, 0.32, 0.58))]:
    mango.scale = scale
    mango.keyframe_insert(data_path="scale", frame=frame)

cam_data = bpy.data.cameras.new("Cinematic camera")
cam = bpy.data.objects.new("Cinematic camera", cam_data)
scene.collection.objects.link(cam)
cam.location = (0, -14, 5.2)
direction = Vector((0, 1, 1.55)) - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
cam_data.lens = 42
scene.camera = cam

def area_light(name, loc, energy, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (Vector((0, 0, 1.5)) - obj.location).to_track_quat("-Z", "Y").to_euler()

area_light("Warm key", (0, -6, 9), 1700, 7, (1.0, 0.78, 0.52))
area_light("Jungle fill", (-6, 1, 6), 1200, 6, (0.48, 0.72, 1.0))
area_light("Golden rim", (5, 5, 7), 1900, 5, (1.0, 0.55, 0.22))

def caption(body, start, end):
    curve = bpy.data.curves.new("Caption", "FONT")
    curve.body = body
    curve.size = 0.48
    obj = bpy.data.objects.new("Caption " + body, curve)
    scene.collection.objects.link(obj)
    obj.location = (-5.7, -5.2, 5.0)
    obj.rotation_euler = (math.radians(90), 0, 0)
    curve.materials.append(white)
    obj.hide_render = True
    obj.keyframe_insert(data_path="hide_render", frame=1)
    obj.keyframe_insert(data_path="hide_render", frame=start - 1)
    obj.hide_render = False
    obj.keyframe_insert(data_path="hide_render", frame=start)
    obj.keyframe_insert(data_path="hide_render", frame=end)
    obj.hide_render = True
    obj.keyframe_insert(data_path="hide_render", frame=end + 1)

caption("MONTY: Operation Mango begins!", 1, 105)
caption("MONTY: Nobody saw that... right?", 106, 205)
caption("MONTY: ABORT! ABORT!", 206, 360)

scene.render.image_settings.color_mode = "RGB"
scene.render.ffmpeg.audio_codec = "AAC"
scene.render.use_file_extension = True
scene.render.filepath = str(OUTPUT)
scene.frame_set(1)
print("Rendering funny cartoon video:", OUTPUT)
bpy.ops.render.render(animation=True)
if not OUTPUT.exists() or OUTPUT.stat().st_size == 0:
    raise RuntimeError("Render finished but MP4 output is missing.")
print("VIDEO_READY:", OUTPUT, OUTPUT.stat().st_size)
