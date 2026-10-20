"""Графика сцены «Порт» для лендинга /port: вид сверху на терминал, машины и судно.

    python port.py yard wide   --s 64 --out yard-wide.png     # 2400×1120, подложка десктопа
    python port.py yard narrow --s 64 --out yard-narrow.png   # 720×1300, подложка телефона
    python port.py yard wide --s 128 --night 1 --out yard-wide-night.png   # ночные версии (фонари, огни кранов)
    python port.py cars        --s 48 --out cars/             # спрайты машин: 4 кузова × 8 цветов
    python port.py ship        --s 64 --out ship.png
    python port_export.py                                     # → renalauto/static/port/*.webp

Подложка строится в координатах сцены из renalauto/static/port.js (1 единица Blender = 1 px сцены,
y сцены вниз = −y Blender): дороги, места и причал совпадают с маршрутами машин.
Если меняете раскладку в port.js — поменяйте и константы WIDE / NARROW здесь.
"""

import math
import os
import random
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from car import loft, superellipse, interp  # noqa: E402
from common import mat, reset  # noqa: E402

random.seed(7)
args = sys.argv[1:]
what = args[0] if args else "yard"
opts = dict(zip(args[1::2], args[2::2])) if what != "yard" else dict(zip(args[2::2], args[3::2]))
SAMPLES = int(opts.get("--s", 48))
NIGHT = opts.get("--night") == "1"  # ночная подложка: фонари, огни кранов, луна

# --- раскладки (те же числа, что в port.js) -------------------------------------------
# широкая: две зоны по 4 ряда × 14 мест; ряд = (центр мест, его проезд)
WIDE = dict(W=1600, H=760, road=56, aisles=[214, 394], rows=[(164, 214), (266, 214), (344, 394), (446, 394)],
            apron=540, quay=600, zones=[30, 810], zone_w=760, cols=14, pitch=50)
NARROW = dict(W=360, H=650, lane=180, quay=556, zones=[56, 304], rows=7, pitch=30)
SUN_DIR = (math.radians(38), 0, math.radians(-35))  # тени ложатся вправо-вниз


def sun(strength=3.0):
    l = bpy.data.lights.new("sun", "SUN")
    l.energy = strength
    l.angle = math.radians(1.2)
    o = bpy.data.objects.new("sun", l)
    bpy.context.collection.objects.link(o)
    o.rotation_euler = SUN_DIR
    return o


def sky(color=(0.62, 0.72, 0.86), strength=0.35):
    bg = bpy.context.scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*color, 1)
    bg.inputs[1].default_value = strength


def top_camera(cx, cy, scale, z=2000):
    c = bpy.data.cameras.new("cam")
    c.type = "ORTHO"
    c.ortho_scale = scale
    c.clip_end = z * 2
    o = bpy.data.objects.new("cam", c)
    bpy.context.collection.objects.link(o)
    o.location = (cx, cy, z)
    bpy.context.scene.camera = o
    return o


# --- материалы -------------------------------------------------------------------------

def noisy(name, c1, c2, scale=0.05, rough=0.85, bump=0.15, detail=8.0, stains=False):
    """Асфальт/бетон: два тона по шуму + мелкий рельеф."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = rough
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c2, 1)
    nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    color = ramp.outputs["Color"]
    if stains:  # тёмные пятна масла и следы — асфальт перестаёт быть однотонным
        sn = nt.nodes.new("ShaderNodeTexNoise")
        sn.inputs["Scale"].default_value = scale * 0.35
        sn.inputs["Detail"].default_value = 4
        nt.links.new(tc.outputs["Object"], sn.inputs["Vector"])
        mask = nt.nodes.new("ShaderNodeValToRGB")
        mask.color_ramp.elements[0].position = 0.62
        mask.color_ramp.elements[1].position = 0.72
        nt.links.new(sn.outputs["Fac"], mask.inputs["Fac"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["B"].default_value = (0.55, 0.55, 0.56, 1)
        nt.links.new(mask.outputs["Color"], mix.inputs["Factor"])
        nt.links.new(color, mix.inputs["A"])
        color = mix.outputs["Result"]
    nt.links.new(color, p.inputs["Base Color"])
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = scale * 40
    nt.links.new(tc.outputs["Object"], fine.inputs["Vector"])
    bn = nt.nodes.new("ShaderNodeBump")
    bn.inputs["Strength"].default_value = bump
    nt.links.new(fine.outputs["Fac"], bn.inputs["Height"])
    nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    return m


def water_mat():
    m = bpy.data.materials.new("water")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.12
    p.inputs["Specular IOR Level"].default_value = 0.6
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1, 3.2, 1)  # волны вытянуты вдоль причала
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    wv = nt.nodes.new("ShaderNodeTexNoise")
    wv.inputs["Scale"].default_value = 0.05
    wv.inputs["Detail"].default_value = 8
    wv.inputs["Distortion"].default_value = 1.5
    nt.links.new(mp.outputs["Vector"], wv.inputs["Vector"])
    bn = nt.nodes.new("ShaderNodeBump")
    bn.inputs["Strength"].default_value = 0.7
    nt.links.new(wv.outputs["Fac"], bn.inputs["Height"])
    nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.01, 0.045, 0.075, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.05, 0.16, 0.2, 1)
    # рябь в цвете: светлые гребни волн
    nt.links.new(wv.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    return m


def hazard_mat():
    m = bpy.data.materials.new("hazard")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = 0.6
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_profile = "SAW"
    wave.inputs["Scale"].default_value = 0.06
    wave.bands_direction = "DIAGONAL"
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].color = (0.75, 0.52, 0.04, 1)
    ramp.color_ramp.elements[1].position = 0.5
    ramp.color_ramp.elements[1].color = (0.02, 0.02, 0.022, 1)
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    return m


def corrugated(name, color):
    """Крыша контейнера: цвет + рифление поперёк."""
    m = mat(name, color, rough=0.55)
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 18
    nt.links.new(tc.outputs["Generated"], wave.inputs["Vector"])
    bn = nt.nodes.new("ShaderNodeBump")
    bn.inputs["Strength"].default_value = 0.25
    nt.links.new(wave.outputs["Fac"], bn.inputs["Height"])
    nt.links.new(bn.outputs["Normal"], p.inputs["Normal"])
    return m


# --- геометрия в координатах сцены ----------------------------------------------------

def box(x0, y0, x1, y1, z0, z1, m, bevel=0.0, rot=0.0):
    """Прямоугольник сцены (x вправо, y вниз) высотой z0..z1."""
    bpy.ops.mesh.primitive_cube_add(location=((x0 + x1) / 2, -(y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object
    o.scale = (abs(x1 - x0) / 2, abs(y1 - y0) / 2, max(z1 - z0, 0.01) / 2)
    o.rotation_euler.z = rot
    o.data.materials.append(m)
    if bevel:
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        b = o.modifiers.new("b", "BEVEL")
        b.width = bevel
        b.segments = 2
    return o


def paint_line(x0, y0, x1, y1, w, m, z=0.5):
    """Разметка лежит поверх всех покрытий (они не выше 0,4)."""
    if x0 == x1:
        return box(x0 - w / 2, y0, x0 + w / 2, y1, 0.42, z, m)
    return box(x0, y0 - w / 2, x1, y0 + w / 2, 0.42, z, m)


def dashes(x0, y0, x1, y1, m, dash=14, gap=12, w=1.6):
    if y0 == y1:
        x = x0
        while x < x1:
            paint_line(x, y0, min(x + dash, x1), y0, w, m)
            x += dash + gap
    else:
        y = y0
        while y < y1:
            paint_line(x0, y, x0, min(y + dash, y1), w, m)
            y += dash + gap


CONTAINER_COLORS = [(0.55, 0.05, 0.03), (0.06, 0.2, 0.45), (0.75, 0.42, 0.05), (0.12, 0.32, 0.18), (0.55, 0.56, 0.58),
                    (0.08, 0.36, 0.48), (0.42, 0.12, 0.06), (0.75, 0.75, 0.73)]
_container_mats = []


def container(cx, cy, length, vertical=False, tiers=1):
    if not _container_mats:
        _container_mats.extend(corrugated(f"cont{i}", c) for i, c in enumerate(CONTAINER_COLORS))
    w = 22
    hx, hy = (w / 2, length / 2) if vertical else (length / 2, w / 2)
    box(cx - hx, cy - hy, cx + hx, cy + hy, 0, 24 * tiers, random.choice(_container_mats), bevel=0.6)


_glow = {}


def glow(color=(1, 0.82, 0.55), strength=40):
    key = (color, strength)
    if key not in _glow:
        _glow[key] = mat(f"glow{len(_glow)}", color, rough=0.3, emit=color, emit_s=strength)
    return _glow[key]


def light_pole(x, y, m_pole, m_lamp, h=110):
    bpy.ops.mesh.primitive_cylinder_add(radius=1.4, depth=h, location=(x, -y, h / 2))
    bpy.context.object.data.materials.append(m_pole)
    box(x - 6, y - 2.5, x + 6, y + 2.5, h - 2, h + 2, glow() if NIGHT else m_lamp)
    if NIGHT:
        l = bpy.data.lights.new("lamp", "SPOT")
        l.energy = 9e5 * (h / 110) ** 2
        l.color = (1, 0.84, 0.62)
        l.spot_size = math.radians(115)
        l.spot_blend = 0.6
        l.shadow_soft_size = 4
        o = bpy.data.objects.new("lamp", l)
        bpy.context.collection.objects.link(o)
        o.location = (x, -y, h - 4)


def beacon(x, y, z, color=(1, 0.08, 0.04)):
    """Сигнальный огонь (краны, судно): ночью светится."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2.2, location=(x, -y, z))
    bpy.context.object.data.materials.append(glow(color, 60) if NIGHT else mat("beacon", (0.5, 0.05, 0.03)))


def poly(points, z, m):
    """Плоский многоугольник разметки (точки сцены)."""
    me = bpy.data.meshes.new("poly")
    me.from_pydata([(px, -py, z) for px, py in points], [], [list(range(len(points)))])
    o = bpy.data.objects.new("poly", me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(m)
    return o


def disc(cx, cy, r, z, m, a0=0.0, a1=2 * math.pi, n=48):
    pts = [(cx, cy)] if a1 - a0 < 2 * math.pi - 1e-6 else []
    pts += [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy - r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    return poly(pts, z, m)


def star(cx, cy, r, z, m, rot=0.0):
    pts = []
    for i in range(10):
        a = math.pi / 2 + rot + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.38
        pts.append((cx + rr * math.cos(a), cy - rr * math.sin(a)))
    return poly(pts, z, m)


def painted_flags(kr_x, cn_x, y):
    """Флаги Кореи и Китая краской на асфальте зон (слегка выцветшие)."""
    w, h = 64, 42
    white = mat("flag_white", (0.62, 0.62, 0.6), rough=0.8)
    red = mat("flag_red", (0.45, 0.04, 0.04), rough=0.8)
    blue = mat("flag_blue", (0.03, 0.1, 0.32), rough=0.8)
    black = mat("flag_black", (0.02, 0.02, 0.02), rough=0.8)
    yellow = mat("flag_yellow", (0.62, 0.48, 0.05), rough=0.8)
    # Корея: белое поле, тхэгук (красный верх, синий низ), четыре триграммы
    poly([(kr_x, y), (kr_x + w, y), (kr_x + w, y + h), (kr_x, y + h)], 0.44, white)
    cx, cy, r = kr_x + w / 2, y + h / 2, 10.5
    disc(cx, cy, r, 0.46, red, 0, math.pi)
    disc(cx, cy, r, 0.46, blue, math.pi, 2 * math.pi)
    disc(cx - r / 2, cy, r / 2, 0.48, red)
    disc(cx + r / 2, cy, r / 2, 0.48, blue)
    for sx, sy, ang in ((-1, -1, -0.98), (1, -1, 0.98), (-1, 1, 0.98), (1, 1, -0.98)):
        bx, by = cx + sx * 21, cy + sy * 12
        for k in range(3):
            o = box(bx - 5, by - 0.9 + (k - 1) * 2.8, bx + 5, by + 0.9 + (k - 1) * 2.8, 0.45, 0.5, black)
            o.rotation_euler.z = ang
    # Китай: красное поле, большая и четыре малые звезды
    poly([(cn_x, y), (cn_x + w, y), (cn_x + w, y + h), (cn_x, y + h)], 0.44, red)
    star(cn_x + 11, y + 11, 6.5, 0.47, yellow)
    for dx, dy in ((21, 4), (25, 8.5), (25, 14.5), (21, 19)):
        star(cn_x + dx, y + dy, 2.2, 0.47, yellow, rot=0.4)


def roof_logo(cx, cy, text="RENAL-AUTO", size=10):
    """Надпись на крыше контейнера."""
    bpy.ops.object.text_add(location=(cx, -cy, 25))
    t = bpy.context.object
    t.data.body = text
    t.data.size = size
    t.data.align_x = "CENTER"
    t.data.align_y = "CENTER"
    t.data.materials.append(mat("logo", (0.95, 0.95, 0.92), rough=0.5))


def gantry_crane(x, quay, water_reach, m_steel, m_dark, vertical_boom=True, span=46):
    """Портальный кран: две ноги на причале, стрела над водой; длинная тень на воду."""
    h = 260
    for dx in (-span / 2, span / 2):
        for y in (quay - 34, quay - 6):
            box(x + dx - 3, y - 3, x + dx + 3, y + 3, 0, h, m_steel)
        box(x + dx - 3.5, quay - 37, x + dx + 3.5, quay - 3, h - 8, h, m_steel)
    box(x - span / 2 - 4, quay - 40, x + span / 2 + 4, quay - 30, h, h + 10, m_steel)
    box(x - span / 2 - 4, quay - 10, x + span / 2 + 4, quay, h, h + 10, m_steel)
    # стрела: две балки + поперечины, уходит над водой
    for dx in (-8, 8):
        box(x + dx - 2.5, quay - 90, x + dx + 2.5, quay + water_reach, h + 10, h + 16, m_steel)
    y = quay - 86
    while y < quay + water_reach:
        box(x - 10, y, x + 10, y + 2, h + 12, h + 15, m_dark)
        y += 14
    box(x - 14, quay - 30, x + 14, quay - 10, h + 16, h + 34, m_dark)  # кабина/машинное
    beacon(x, quay + water_reach - 2, h + 20)
    beacon(x, quay - 88, h + 20)


def ground(W, H, quay, m_ground, m_water, m_hazard, m_concrete):
    box(-40, -40, W + 40, quay, -2, 0, m_ground)
    box(-40, quay, W + 40, H + 60, -30, -6, m_water)
    box(-40, quay - 1, W + 40, quay + 7, -6, 0.5, m_concrete)  # стенка причала
    box(-40, quay - 7, W + 40, quay - 1, 0, 0.3, m_hazard)
    foam = noisy("foam", (0.06, 0.16, 0.2), (0.3, 0.42, 0.45), scale=0.15, rough=0.4)
    box(-40, quay + 7, W + 40, quay + 12, -6.2, -5.8, foam)  # пена у стенки


def yard_wide():
    k = WIDE
    W, H, road, apron, quay, zw = k["W"], k["H"], k["road"], k["apron"], k["quay"], k["zone_w"]
    m_ground = noisy("ground", (0.2, 0.2, 0.19), (0.27, 0.27, 0.26), scale=0.03)
    m_yard = noisy("yard", (0.075, 0.078, 0.082), (0.11, 0.112, 0.115), scale=0.05, stains=True)
    m_road = noisy("road", (0.05, 0.052, 0.056), (0.075, 0.077, 0.08), scale=0.06, stains=True)
    m_white = mat("white", (0.78, 0.78, 0.74), rough=0.7)
    m_yellow = mat("yellow", (0.8, 0.55, 0.06), rough=0.7)
    m_conc = noisy("concrete", (0.32, 0.32, 0.31), (0.4, 0.4, 0.39), scale=0.08, stains=True)
    m_steel = mat("steel", (0.85, 0.12, 0.08), rough=0.5)  # краны в фирменном красном
    m_dark = mat("dark", (0.05, 0.05, 0.055), rough=0.5)
    m_lamp = mat("lamp", (0.9, 0.9, 0.85), rough=0.3)
    m_grass = noisy("grass", (0.09, 0.16, 0.06), (0.14, 0.22, 0.08), scale=0.08, bump=0.4)
    m_median = noisy("median", (0.16, 0.16, 0.155), (0.21, 0.21, 0.2), scale=0.08)
    ground(W, H, quay, m_ground, water_mat(), hazard_mat(), m_conc)

    box(-40, -40, W + 40, 8, 0, 0.4, m_grass)  # полоса газона у забора
    box(-40, 8, W + 40, 10, 0, 18, m_dark)  # забор
    box(-40, road - 20, W + 40, road + 20, 0, 0.21, m_road)
    dashes(-40, road, W + 40, road, m_white)
    paint_line(-40, road - 18, W + 40, road - 18, 1.2, m_white)
    paint_line(-40, road + 18, W + 40, road + 18, 1.2, m_white)

    for x0 in k["zones"]:
        cx = x0 + 24
        x1 = x0 + 51 + k["cols"] * k["pitch"]
        box(x0, 96, x0 + zw, apron - 18, 0, 0.25, m_yard)
        for a in k["aisles"]:
            box(x0, a - 18, x0 + zw, a + 18, 0, 0.3, m_road)
            dashes(x0 + 48, a, x0 + zw, a, m_yellow, w=1.4)
        box(x0 + 6, road + 20, x0 + 42, apron - 18, 0, 0.33, m_road)
        dashes(cx, road + 24, cx, apron - 18, m_yellow, w=1.4)
        # разделительная полоса между рядами «спина к спине»
        box(x0 + 51, 293, x1, 317, 0.3, 0.42, m_median)
        for sy, a in k["rows"]:
            for i in range(k["cols"] + 1):
                x = x0 + 51 + i * k["pitch"]
                paint_line(x, sy - 26, x, sy + 26, 1.6, m_white)
            far = sy - 26 if sy < a else sy + 26
            paint_line(x0 + 51, far, x1, far, 1.6, m_white)
    box(-40, apron - 18, W + 40, apron + 18, 0, 0.36, m_road)
    dashes(-40, apron, W + 40, apron, m_white)

    # контейнеры вдоль верхнего края (уходят за кадр) и по бокам
    x, n = -30, 0
    while x < W + 40:
        ln = random.choice((55, 55, 110))
        container(x + ln / 2, 24, ln)
        if ln == 110 and n % 2 == 0 and 100 < x < W - 150:
            roof_logo(x + ln / 2, 24)
        n += 1
        x += ln + 3
    for y in (150, 265, 380, 495):
        container(1590, y, 110, vertical=True, tiers=random.choice((1, 2)))
    for y in (160, 270, 380):
        container(12, y, 55, vertical=True, tiers=2)
    # будка у ворот
    box(14, 2, 40, 16, 0, 26, m_lamp, bevel=1)
    box(12, 0, 42, 18, 26, 28, m_dark)
    if NIGHT:
        box(16, 14, 38, 16.5, 20, 27, glow((1, 0.9, 0.7), 6))  # окно будки
    painted_flags(k["zones"][0] + 686, k["zones"][1] + 686, 477)
    # фонари: между зонами, по краям, над рядами и вдоль причала
    for y in (110, 305, 500):
        light_pole(800, y, m_dark, m_lamp)
    for x0 in k["zones"]:
        for x in (x0 + 210, x0 + 560):
            light_pole(x, 305, m_dark, m_lamp)
        light_pole(x0 + 380, 104, m_dark, m_lamp)
    for x in (30, 1570):
        light_pole(x, 500, m_dark, m_lamp)
    for x in (420, 800, 1180):
        light_pole(x, quay - 22, m_dark, m_lamp, h=70)
    # портальные краны по краям причала, стрелы над водой
    gantry_crane(180, quay, 170, m_steel, m_dark)
    gantry_crane(1420, quay, 170, m_steel, m_dark)
    # кнехты
    bx = 40
    while bx < W:
        bpy.ops.mesh.primitive_cylinder_add(radius=3, depth=6, location=(bx, -(quay + 2), 3))
        bpy.context.object.data.materials.append(m_dark)
        bx += 80
    return W, H


def yard_narrow():
    k = NARROW
    W, H, lane, quay = k["W"], k["H"], k["lane"], k["quay"]
    m_ground = noisy("ground", (0.2, 0.2, 0.19), (0.27, 0.27, 0.26), scale=0.03)
    m_yard = noisy("yard", (0.075, 0.078, 0.082), (0.11, 0.112, 0.115), scale=0.05, stains=True)
    m_road = noisy("road", (0.05, 0.052, 0.056), (0.075, 0.077, 0.08), scale=0.06, stains=True)
    m_white = mat("white", (0.78, 0.78, 0.74), rough=0.7)
    m_yellow = mat("yellow", (0.8, 0.55, 0.06), rough=0.7)
    m_conc = noisy("concrete", (0.32, 0.32, 0.31), (0.4, 0.4, 0.39), scale=0.08, stains=True)
    m_steel = mat("steel", (0.85, 0.12, 0.08), rough=0.5)
    m_dark = mat("dark", (0.05, 0.05, 0.055), rough=0.5)
    m_lamp = mat("lamp", (0.9, 0.9, 0.85), rough=0.3)
    ground(W, H, quay, m_ground, water_mat(), hazard_mat(), m_conc)
    for y0 in k["zones"]:
        box(16, y0, W - 16, y0 + 236, 0, 0.25, m_yard)
        for j in range(k["rows"] + 1):
            y = y0 + 21 + j * k["pitch"]
            paint_line(lane - 88, y, lane - 30, y, 1.4, m_white)
            paint_line(lane + 30, y, lane + 88, y, 1.4, m_white)
        paint_line(lane - 88, y0 + 21, lane - 88, y0 + 21 + k["rows"] * k["pitch"], 1.4, m_white)
        paint_line(lane + 88, y0 + 21, lane + 88, y0 + 21 + k["rows"] * k["pitch"], 1.4, m_white)
    box(lane - 18, -40, lane + 18, quay, 0, 0.36, m_road)
    dashes(lane, -40, lane, quay, m_yellow, w=1.4)
    # контейнеры по бокам сверху, будка у ворот
    for x in (40, 96, 264, 320):
        container(x, 18, 55, tiers=random.choice((1, 2)))
    box(lane + 22, 14, lane + 38, 38, 0, 24, m_lamp, bevel=1)
    for x, y in ((24, 298), (W - 24, 298), (24, 70), (W - 24, 70), (24, 530), (W - 24, 530)):
        light_pole(x, y, m_dark, m_lamp, h=90)
    gantry_crane(28, quay, 80, m_steel, m_dark, span=30)
    gantry_crane(W - 28, quay, 80, m_steel, m_dark, span=30)
    return W, H


def render_yard(kind, out):
    sc = reset()
    sc.render.film_transparent = False
    sc.cycles.samples = SAMPLES
    sc.view_settings.look = "AgX - Medium High Contrast"
    if NIGHT:
        sc.view_settings.exposure = 0.1
        sky((0.05, 0.07, 0.13), 0.35)
        moon = sun(0.09)
        moon.data.color = (0.7, 0.8, 1)
    else:
        sc.view_settings.exposure = -0.9
        sky()
        sun()
    W, H = yard_wide() if kind == "wide" else yard_narrow()
    sc.render.resolution_x, sc.render.resolution_y = W * 2, H * 2
    top_camera(W / 2, -H / 2, max(W, H))
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)


# --- машины ------------------------------------------------------------------------------
# Метры. Нос — к −X (как в car.py), на спрайте нос смотрит вверх.
BODIES = {
    #        длина ширина  пояс  крыша от/до (доля длины от носа)  высота крыши
    "sedan": (4.8, 1.86, 0.95, 0.34, 0.74, 1.44),
    "suv": (4.6, 1.92, 1.05, 0.27, 0.93, 1.70),
    "hatch": (3.9, 1.76, 0.95, 0.30, 0.94, 1.50),
    "van": (5.1, 1.98, 1.05, 0.17, 0.97, 1.82),
}
PAINTS = {
    "white": ((0.86, 0.87, 0.88), 0.0), "pearl": ((0.86, 0.83, 0.76), 0.2), "silver": ((0.6, 0.62, 0.64), 0.85),
    "grey": ((0.3, 0.31, 0.33), 0.7), "graphite": ((0.08, 0.085, 0.095), 0.6), "black": ((0.012, 0.012, 0.014), 0.2),
    "blue": ((0.03, 0.12, 0.42), 0.6), "red": ((0.55, 0.02, 0.02), 0.3),
}
SPRITE_M = 6.0  # спрайт — 6 × 3 м, у всех кузовов один масштаб


def build_car(kind, paint, glass, dark, lamp, tail):
    L, Wd, belt, r0, r1, rh = BODIES[kind]
    hl = L / 2
    front, rear = -hl, hl
    box_n = 6 if kind in ("suv", "van") else 5

    def plan(x):  # сужение кузова к бамперам
        t = min(abs(x) / hl, 0.9999)
        return (1 - t ** 6) ** (1 / 6)

    hood = 0.82 if kind in ("sedan", "hatch") else 0.95

    def body(x):
        f = (x - front) / L
        top = interp([(0, hood - 0.12), (0.12, hood), (r0, belt), (0.85, belt), (1, belt - 0.05)], f)
        bot = 0.32
        p = plan(x)
        return superellipse(0, (top + bot) / 2, Wd / 2 * (0.55 + 0.45 * p), (top - bot) / 2 * (0.4 + 0.6 * p), n=box_n, tumble=0.1)

    xs = [front + L * i / 120 for i in range(121)]
    car = [loft("body", xs, body)]
    car[0].data.materials.append(paint)

    g0, g1 = front + L * (r0 - 0.08), front + L * r1
    peak0, peak1 = front + L * (r0 + 0.1), front + L * (r1 - (0.05 if kind in ("suv", "van") else 0.14))

    def roof_z(x):
        return interp([(g0, belt), (peak0, rh), (peak1, rh), (g1, belt + (0.25 if kind in ("suv", "van") else 0.05))], x)

    def greenhouse(x):
        bot = belt - 0.02
        top = max(roof_z(x), bot + 0.01)
        return superellipse(0, (top + bot) / 2, Wd / 2 * 0.84, (top - bot) / 2, n=6, tumble=0.32)

    gx = [g0 + (g1 - g0) * i / 80 for i in range(81)]
    gh = loft("glass", gx, greenhouse)
    gh.data.materials.append(glass)

    def roof(x):
        return superellipse(0, roof_z(x) - 0.01, Wd / 2 * 0.66, 0.03, n=4, m=24)

    rx = [peak0 + 0.05 + (peak1 - peak0 - 0.1) * i / 50 for i in range(51)]
    rf = loft("roof", rx, roof)
    rf.data.materials.append(paint)
    car += [gh, rf]
    for side in (-1, 1):  # зеркала, фары, фонари
        bpy.ops.mesh.primitive_cube_add(location=(g0 + 0.25, side * (Wd / 2 + 0.08), belt + 0.05))
        o = bpy.context.object
        o.scale = (0.08, 0.11, 0.06)
        o.data.materials.append(paint)
        bpy.ops.mesh.primitive_cube_add(location=(front + 0.12, side * Wd * 0.34, hood - 0.08))
        o2 = bpy.context.object
        o2.scale = (0.08, 0.2, 0.05)
        o2.data.materials.append(lamp)
        bpy.ops.mesh.primitive_cube_add(location=(rear - 0.06, side * Wd * 0.36, belt - 0.1))
        o3 = bpy.context.object
        o3.scale = (0.05, 0.22, 0.05)
        o3.data.materials.append(tail)
        car += [o, o2, o3]
    if kind in ("suv", "van"):  # рейлинги
        for side in (-1, 1):
            bpy.ops.mesh.primitive_cube_add(location=((peak0 + peak1) / 2, side * Wd * 0.3, rh + 0.03))
            o = bpy.context.object
            o.scale = ((peak1 - peak0) / 2, 0.025, 0.025)
            o.data.materials.append(dark)
            car.append(o)
    piv = bpy.data.objects.new("car", None)
    bpy.context.collection.objects.link(piv)
    for p in car:
        p.parent = piv
    piv.rotation_euler.z = math.radians(-90)  # нос вверх на спрайте
    return piv


def render_cars(out):
    os.makedirs(out, exist_ok=True)
    for kind in BODIES:
        for name, (color, metal) in PAINTS.items():
            sc = reset()
            sc.cycles.samples = SAMPLES
            sc.render.resolution_x, sc.render.resolution_y = 64, 128
            sky((0.75, 0.8, 0.9), 0.9)
            s = sun(3.2)
            s.rotation_euler = (0, 0, 0)  # тень под машиной: спрайт поворачивается вместе с ней
            s.data.angle = math.radians(25)
            paint = mat("paint", color, rough=0.25, metal=metal, coat=1.0)
            glass = mat("glass", (0.01, 0.014, 0.02), rough=0.05, metal=0.6)
            dark = mat("dark", (0.03, 0.03, 0.032), rough=0.5)
            lamp = mat("lamp", (0.9, 0.9, 0.88), rough=0.1, emit=(1, 0.97, 0.9), emit_s=1.5)
            tail = mat("tail", (0.6, 0.02, 0.02), rough=0.2, emit=(1, 0.05, 0.03), emit_s=1.0)
            build_car(kind, paint, glass, dark, lamp, tail)
            bpy.ops.mesh.primitive_plane_add(size=40)
            bpy.context.object.is_shadow_catcher = True
            top_camera(0, 0, SPRITE_M, z=50)
            sc.render.filepath = os.path.join(out, f"{kind}-{name}.png")
            bpy.ops.render.render(write_still=True)


# --- судно -------------------------------------------------------------------------------

def render_ship(out):
    """Судно в единицах сцены: 560 × 92, нос справа. Палуба пустая — машины на ней рисует сцена."""
    sc = reset()
    sc.cycles.samples = SAMPLES
    w, h = 560, 92
    sc.render.resolution_x, sc.render.resolution_y = (w + 80) * 2, (h + 60) * 2
    sky()
    sun()
    hull = mat("hull", (0.03, 0.05, 0.08), rough=0.45)
    deck = noisy("deck", (0.045, 0.06, 0.055), (0.065, 0.085, 0.075), scale=0.08, rough=0.7)
    white = mat("white", (0.85, 0.86, 0.86), rough=0.4)
    glass = mat("glass", (0.02, 0.03, 0.05), rough=0.05, metal=0.6)
    red = mat("red", (0.75, 0.05, 0.04), rough=0.45)
    yellow = mat("yellow", (0.8, 0.55, 0.06), rough=0.6)

    def section(x):  # план корпуса: прямой борт, острый нос справа, скруглённая корма
        t = x / w
        half = h / 2 * (1 - max(0, (t - 0.82) / 0.18) ** 2.2 * 0.92) * (0.92 + 0.08 * min(1, t / 0.04))
        return superellipse(0, 0, half, 16, n=8, m=48)

    xs = [w * i / 140 for i in range(141)]
    hb = loft("hull", xs, section)
    hb.data.materials.append(hull)
    # палуба
    bpy.ops.mesh.primitive_cube_add(location=(w * 0.44, 0, 16))
    d = bpy.context.object
    d.scale = (w * 0.38, h / 2 - 6, 0.5)
    d.data.materials.append(deck)
    for yy in (-h / 2 + 8, h / 2 - 8):  # жёлтые линии по бортам
        bpy.ops.mesh.primitive_cube_add(location=(w * 0.44, yy, 16.6))
        o = bpy.context.object
        o.scale = (w * 0.38, 0.8, 0.1)
        o.data.materials.append(yellow)
    # надстройка на корме
    bpy.ops.mesh.primitive_cube_add(location=(32, 0, 34))
    s = bpy.context.object
    s.scale = (24, h / 2 - 10, 18)
    s.data.materials.append(white)
    bpy.ops.mesh.primitive_cube_add(location=(48, 0, 46))
    b = bpy.context.object
    b.scale = (4, h / 2 - 4, 6)
    b.data.materials.append(glass)
    bpy.ops.mesh.primitive_cylinder_add(radius=7, depth=16, location=(20, 0, 58))
    bpy.context.object.data.materials.append(red)
    # бак на носу
    bpy.ops.mesh.primitive_cube_add(location=(w * 0.9, 0, 22))
    f = bpy.context.object
    f.scale = (18, h / 2 - 22, 6)
    f.data.materials.append(white)
    for o in bpy.data.objects:  # судно строилось от x=0 — центрируем в кадре
        if o.type == "MESH":
            o.location.x += -w / 2 + 10
    bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, -2))
    bpy.context.object.is_shadow_catcher = True
    top_camera(0, 0, w + 80, z=500)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    if what == "yard":
        render_yard(args[1] if len(args) > 1 else "wide", opts.get("--out", "yard.png"))
    elif what == "cars":
        render_cars(opts.get("--out", "cars"))
    elif what == "ship":
        render_ship(opts.get("--out", "ship.png"))
