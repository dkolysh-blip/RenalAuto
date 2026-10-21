"""Спрайты стоянки из настоящих 3D-моделей (Sketchfab, CC BY): вид сверху, нос вверх, 8 цветов.

    python real_cars.py inspect <папка моделей> <папка превью>     # габариты, материалы, превью сверху
    python real_cars.py render  <папка моделей> <папка спрайтов> --s 48

Каждая модель — <папка>/<slug>/scene.gltf и meta.json (автор и лицензия, их выводим на сайте).
Нос, длина и материал кузова у моделей разные — они заданы в CARS ниже после осмотра превью.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import reset  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
what, src, dst = args[0], args[1], args[2]
opts = dict(zip(args[3::2], args[4::2]))
SAMPLES = int(opts.get("--s", 48))
ONLY = opts.get("--only")

# slug: (длина, м; поворот в градусах, чтобы нос смотрел вверх; подстроки имён материалов кузова)
CARS = {}
CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_cars.json")
if os.path.exists(CFG):
    CARS = json.load(open(CFG))


def load(slug):
    reset()
    bpy.ops.import_scene.gltf(filepath=os.path.join(src, slug, "scene.gltf"))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    lo = Vector((1e9, 1e9, 1e9)); hi = -lo
    for o in meshes:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    return meshes, lo, hi


def normalize(meshes, lo, hi, length, rot):
    """В центр, колёса на z = 0, длина по Y, нос вверх (+Y), масштаб под реальную длину."""
    size = hi - lo
    center = (lo + hi) / 2
    along_x = size.x > size.y
    k = length / max(size.x, size.y)
    m = (Matrix.Rotation(math.radians(rot + (90 if along_x else 0)), 4, "Z") @ Matrix.Scale(k, 4)
         @ Matrix.Translation(Vector((-center.x, -center.y, -lo.z))))
    roots = [o for o in bpy.context.scene.objects if o.parent is None]
    for o in roots:
        o.matrix_world = m @ o.matrix_world


def materials(meshes):
    area = {}
    for o in meshes:
        ms = o.data.materials
        sx = o.matrix_world.to_scale()
        s = abs(sx.x * sx.y * sx.z) ** (2 / 3)
        for p in o.data.polygons:
            if p.material_index < len(ms) and ms[p.material_index]:
                n = ms[p.material_index].name
                area[n] = area.get(n, 0) + p.area * s
    return sorted(area.items(), key=lambda kv: -kv[1])


def camera(scale, res):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    c = bpy.data.cameras.new("cam"); c.type = "ORTHO"; c.ortho_scale = scale; c.clip_end = 200
    o = bpy.data.objects.new("cam", c); bpy.context.collection.objects.link(o)
    o.location = (0, 0, 50); sc.camera = o


def light():
    l = bpy.data.lights.new("sun", "SUN"); l.energy = 3.2; l.angle = math.radians(25)
    o = bpy.data.objects.new("sun", l); bpy.context.collection.objects.link(o)
    w = bpy.context.scene.world.node_tree.nodes["Background"]
    w.inputs[0].default_value = (0.75, 0.8, 0.9, 1); w.inputs[1].default_value = 0.45  # слабее: крыша не отражает белое небо
    bpy.ops.mesh.primitive_plane_add(size=40)
    bpy.context.object.is_shadow_catcher = True


PAINTS = {
    "white": ((0.86, 0.87, 0.88), 0.0), "pearl": ((0.86, 0.83, 0.76), 0.2), "silver": ((0.6, 0.62, 0.64), 0.85),
    "grey": ((0.3, 0.31, 0.33), 0.7), "graphite": ((0.08, 0.085, 0.095), 0.6), "black": ((0.012, 0.012, 0.014), 0.2),
    "blue": ((0.03, 0.12, 0.42), 0.6), "red": ((0.55, 0.02, 0.02), 0.3),
}


def tint_glass():
    """Стёкла сверху — тёмные и непрозрачные, как на остальных спрайтах: сквозь них не видно белого салона."""
    for m in bpy.data.materials:
        if not m.use_nodes or not any(k in m.name.lower() for k in ("glass", "window", "windsmask")):
            continue
        p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not p or any(k in m.name.lower() for k in ("light", "lamp")):
            continue
        for l in list(p.inputs["Base Color"].links):
            m.node_tree.links.remove(l)
        p.inputs["Base Color"].default_value = (0.01, 0.014, 0.02, 1)
        p.inputs["Metallic"].default_value = 0.6
        p.inputs["Roughness"].default_value = 0.05
        p.inputs["Transmission Weight"].default_value = 0.0
        if "Alpha" in p.inputs:
            for l in list(p.inputs["Alpha"].links):
                m.node_tree.links.remove(l)
            p.inputs["Alpha"].default_value = 1.0


def paint(body_keys, color, metal):
    for m in bpy.data.materials:
        if not m.use_nodes or not any(k.lower() in m.name.lower() for k in body_keys):
            continue
        p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not p:
            continue
        for l in list(p.inputs["Base Color"].links):
            m.node_tree.links.remove(l)
        p.inputs["Base Color"].default_value = (*color, 1)
        p.inputs["Metallic"].default_value = metal
        p.inputs["Roughness"].default_value = 0.38
        if "Coat Weight" in p.inputs:
            p.inputs["Coat Weight"].default_value = 0.25


slugs = sorted(d for d in os.listdir(src) if os.path.exists(os.path.join(src, d, "scene.gltf")) and (what == "inspect" or d in CARS))
if ONLY:
    slugs = [s for s in slugs if s in ONLY.split(",")]
os.makedirs(dst, exist_ok=True)
for slug in slugs:
    cfg = CARS.get(slug, {"length": 4.8, "rot": 0, "body": []})
    meshes, lo, hi = load(slug)
    normalize(meshes, lo, hi, cfg["length"], cfg["rot"])
    if what == "inspect":
        print("##", slug, "size", tuple(round(v, 2) for v in (hi - lo)))
        for n, a in materials(meshes)[:10]:
            print("   ", round(a, 2), n)
        sc = bpy.context.scene; sc.cycles.samples = 16
        light(); camera(6.0, (160, 320))
        sc.render.filepath = os.path.join(dst, f"{slug}.png")
        bpy.ops.render.render(write_still=True)
        # вид спереди-сверху со стороны +Y: на превью должен быть перёд машины (фары, решётка)
        cam = sc.camera; cam.data.type = "PERSP"; cam.data.lens = 50
        cam.location = (0, 9, 3.2); cam.rotation_euler = (math.radians(72), 0, math.radians(180))
        sc.render.resolution_x, sc.render.resolution_y = 240, 160
        sc.render.filepath = os.path.join(dst, f"{slug}-front.png")
        bpy.ops.render.render(write_still=True)
    else:
        sc = bpy.context.scene; sc.cycles.samples = SAMPLES
        tint_glass()
        light(); camera(6.0, (64, 128))  # как у остальных спрайтов: 6 × 3 м
        # у моделей с одной запечённой текстурой кузов не перекрасить — рендерим их родной цвет
        for name, (color, metal) in (PAINTS.items() if cfg["body"] else [("native", (None, None))]):
            if cfg["body"]:
                paint(cfg["body"], color, metal)
            sc.render.filepath = os.path.join(dst, f"{slug}-{name}.png")
            bpy.ops.render.render(write_still=True)
