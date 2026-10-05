import bpy, bmesh, math
from mathutils import Vector

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (0.9, 0.92, 0.96, 1); bg.inputs[1].default_value = 0.35
    return sc

def mat(name, color, rough=0.4, metal=0.0, coat=0.0, emit=None, emit_s=0.0, transm=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    p.inputs['Coat Weight'].default_value = coat
    p.inputs['Transmission Weight'].default_value = transm
    if emit:
        p.inputs['Emission Color'].default_value = (*emit, 1); p.inputs['Emission Strength'].default_value = emit_s
    return m

def link(obj, m):
    obj.data.materials.clear(); obj.data.materials.append(m); return obj

def shade(obj, bevel=0.0, segs=3, smooth=True):
    if bevel:
        b = obj.modifiers.new('bev', 'BEVEL'); b.width = bevel; b.segments = segs; b.limit_method = 'ANGLE'
    if smooth:
        for p in obj.data.polygons: p.use_smooth = True
        obj.modifiers.new('wn', 'WEIGHTED_NORMAL')
    return obj

def extrude_profile(name, pts, width, y0=None):
    """pts: list of (x, z) side silhouette; extruded along Y, centred."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    h = width / 2
    a = [bm.verts.new((x, -h, z)) for x, z in pts]
    b = [bm.verts.new((x, h, z)) for x, z in pts]
    bm.faces.new(a[::-1]); bm.faces.new(b)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    return ob

def area_light(name, loc, target, size, power, color=(1,1,1)):
    l = bpy.data.lights.new(name, 'AREA'); l.size = size; l.energy = power; l.color = color
    o = bpy.data.objects.new(name, l); bpy.context.collection.objects.link(o); o.location = loc
    look_at(o, target); return o

def look_at(o, target):
    d = Vector(target) - o.location
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

def camera(loc, target, lens=50, ortho=None):
    c = bpy.data.cameras.new('cam'); c.lens = lens
    if ortho: c.type = 'ORTHO'; c.ortho_scale = ortho
    o = bpy.data.objects.new('cam', c); bpy.context.collection.objects.link(o); o.location = loc
    look_at(o, target); bpy.context.scene.camera = o; return o
