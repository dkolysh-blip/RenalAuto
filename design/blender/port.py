"""Графика сцены «Порт» для лендинга /port: вид сверху на терминал, машины и судно.

    python port.py yard wide   --s 64 --out yard-wide.png     # 2400×1120, подложка десктопа
    python port.py yard route  --s 64 --out yard-route.png    # 3200×1320, подложка десктопа «маршрут»: стоянки, море, Владивосток
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
# маршрут: стоянки Кореи и Китая (2 ряда × 8 крупных мест), море с судном и площадка Владивостока справа
ROUTE = dict(W=1600, H=660, road=40, aisle=276, rows=[(214, 276), (338, 276)], apron=440, quay=478,
             zones=[30, 610], zone_w=570, cols=8, pitch=64, vlad=1200)
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
    m_ground = noisy("ground", (0.3, 0.3, 0.29), (0.38, 0.38, 0.37), scale=0.03)
    m_yard = noisy("yard", (0.2, 0.205, 0.21), (0.26, 0.265, 0.27), scale=0.05, stains=True)  # светлый бетон
    m_road = noisy("road", (0.09, 0.093, 0.1), (0.125, 0.128, 0.135), scale=0.06, stains=True)
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
    # флаги зон — у названий зон на сцене (SVG): низ зоны занимает шкала цен
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


def ground_text(x, y, text, size, m, rot=0.0, z=0.46):
    """Надпись краской на покрытии (номер места, стрелка)."""
    bpy.ops.object.text_add(location=(x, -y, z))
    t = bpy.context.object
    t.data.body = text
    t.data.size = size
    t.data.align_x = "CENTER"
    t.data.align_y = "CENTER"
    t.rotation_euler.z = rot
    t.data.materials.append(m)
    return t


def tree(x, y, r, m_leaf, m_trunk):
    """Дерево сверху: крона из нескольких неровных шаров — даёт живую тень на асфальте."""
    bpy.ops.mesh.primitive_cylinder_add(radius=r * 0.12, depth=r * 1.1, location=(x, -y, r * 0.55))
    bpy.context.object.data.materials.append(m_trunk)
    for _ in range(5):
        dx, dy = random.uniform(-0.45, 0.45) * r, random.uniform(-0.45, 0.45) * r
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=r * random.uniform(0.55, 0.8),
                                              location=(x + dx, -(y + dy), r * random.uniform(1.0, 1.4)))
        o = bpy.context.object
        o.scale.z = 0.7
        o.data.materials.append(m_leaf)
        d = o.modifiers.new("d", "DISPLACE")
        tex = bpy.data.textures.new("leaf", "CLOUDS")
        tex.noise_scale = r * 0.25
        d.texture = tex
        d.strength = r * 0.25
        for p_ in o.data.polygons:
            p_.use_smooth = True


def yard_route():
    """Подложка-маршрут: две стоянки с живым асфальтом, причал, справа — светлая площадка Владивостока.

    Без кранов и контейнеров. Детали, которые делают картинку настоящей: стыки плит, следы шин, потёртая разметка,
    номера мест, колесоотбойники, бордюры, полоса зелени с деревьями и низкое солнце с длинными мягкими тенями.
    """
    k = ROUTE
    W, H, road, apron, quay, zw, VX, a = k["W"], k["H"], k["road"], k["apron"], k["quay"], k["zone_w"], k["vlad"], k["aisle"]
    m_ground = noisy("ground", (0.2, 0.21, 0.225), (0.25, 0.26, 0.275), scale=0.03)
    m_yard = noisy("yard", (0.125, 0.135, 0.15), (0.185, 0.195, 0.21), scale=0.035, stains=True)
    m_road = noisy("road", (0.065, 0.07, 0.08), (0.105, 0.11, 0.12), scale=0.05, stains=True)
    m_white = noisy("white", (0.5, 0.5, 0.48), (0.82, 0.82, 0.8), scale=0.6, rough=0.7, bump=0.05)      # краска местами стёрта
    m_yellow = noisy("yellow", (0.5, 0.36, 0.08), (0.82, 0.57, 0.06), scale=0.6, rough=0.7, bump=0.05)
    m_num = mat("num", (0.55, 0.56, 0.55), rough=0.8)
    m_conc = noisy("concrete", (0.32, 0.32, 0.31), (0.4, 0.4, 0.39), scale=0.08, stains=True)
    m_curb = noisy("curb", (0.36, 0.36, 0.35), (0.46, 0.46, 0.45), scale=0.2)
    m_joint = mat("joint", (0.05, 0.053, 0.06), rough=0.9)
    m_tyre = mat("tyre", (0.055, 0.058, 0.066), rough=0.7)  # чуть темнее асфальта: накат, а не чёрная полоса
    m_vlad = noisy("vlad", (0.47, 0.49, 0.51), (0.6, 0.62, 0.64), scale=0.04, stains=True)  # светлый бетон площадки
    m_dark = mat("dark", (0.05, 0.05, 0.055), rough=0.5)
    m_lamp = mat("lamp", (0.9, 0.9, 0.85), rough=0.3)
    m_grass = noisy("grass", (0.06, 0.12, 0.05), (0.12, 0.2, 0.08), scale=0.12, bump=0.5)
    m_leaf = noisy("leaf", (0.04, 0.11, 0.04), (0.1, 0.2, 0.07), scale=0.3, bump=0.6)
    m_trunk = mat("trunk", (0.1, 0.07, 0.05), rough=0.9)
    m_red = mat("red", (0.75, 0.08, 0.06), rough=0.6)
    ground(W, H, quay, m_ground, water_mat(), hazard_mat(), m_conc)

    box(-40, -40, W + 40, 6, 0, 0.4, m_grass)
    box(-40, road - 20, W + 40, road + 20, 0, 0.21, m_road)
    dashes(-40, road, W + 40, road, m_white)
    for dy in (-9, 9):  # накатанные колеи на дороге
        for off in (-3.2, 3.2):
            box(-40, road + dy + off - 0.9, W + 40, road + dy + off + 0.9, 0.21, 0.225, m_tyre)
    for x0 in k["zones"]:
        cx = x0 + 24
        x1 = x0 + 50 + k["cols"] * k["pitch"]
        # зелёная полоса с деревьями между дорогой и стоянкой, бордюр вокруг площадки
        box(x0 + 46, road + 22, x0 + zw, 98, 0, 1.6, m_grass, bevel=0.4)
        box(x0 + 44, road + 20, x0 + zw + 2, 100, 0, 1.2, m_curb, bevel=0.3)
        for i in range(6):
            tree(x0 + 96 + i * 92 + random.uniform(-8, 8), 80 + random.uniform(-3, 3), random.uniform(11, 14), m_leaf, m_trunk)
        box(x0 - 2, 98, x0 + zw + 2, 414, 0, 1.0, m_curb, bevel=0.3)
        box(x0, 100, x0 + zw, 412, 0, 1.05, m_yard)
        # стыки бетонных плит
        for i in range(1, 9):
            box(x0 + i * 64 - 14.4, 100, x0 + i * 64 - 13.6, 412, 1.05, 1.07, m_joint)
        for y in (136, 172, 380):
            box(x0, y - 0.4, x0 + zw, y + 0.4, 1.05, 1.07, m_joint)
        box(x0, a - 22, x0 + zw, a + 22, 0, 1.1, m_road)
        dashes(x0 + 48, a, x0 + zw, a, m_yellow, w=1.4)
        for dy in (-10, 10):
            for off in (-3.4, 3.4):
                box(x0 + 30, a + dy + off - 0.8, x0 + zw - 8, a + dy + off + 0.8, 1.1, 1.115, m_tyre)
        box(x0 + 6, road + 20, x0 + 42, apron - 18, 0, 1.12, m_road)
        dashes(cx, road + 24, cx, apron - 18, m_yellow, w=1.4)
        for i, (sy, _) in enumerate(k["rows"]):
            up = sy < a
            for c in range(k["cols"] + 1):
                x = x0 + 50 + c * k["pitch"]
                paint_line(x, sy - 42, x, sy + 42, 1.8, m_white, z=1.14)
            far = sy - 42 if up else sy + 42
            paint_line(x0 + 50, far, x1, far, 1.8, m_white, z=1.14)
            for c in range(k["cols"]):
                sx = x0 + 82 + c * k["pitch"]
                # колесоотбойник у дальнего края и следы шин от проезда к месту
                wy = sy - 33 if up else sy + 33
                box(sx - 16, wy - 1.6, sx + 16, wy + 1.6, 1.05, 2.6, m_curb, bevel=0.5)
                for off in (-11, 11):
                    box(sx + off - 1.3, min(sy, a) + (24 if up else 0), sx + off + 1.3, max(sy, a) - (0 if up else 24), 1.05, 1.065, m_tyre)
                ground_text(sx, a + (-17 if up else 17), f"{i * k['cols'] + c + 1:02d}", 7.5, m_num, z=1.12)
        # стрелки направления на проезде
        for xx in (x0 + 150, x0 + 400):
            ground_text(xx, a - 9, "›", 22, m_white, z=1.12)
            ground_text(xx + 60, a + 9, "‹", 22, m_white, z=1.12)
    box(-40, apron - 18, VX, apron + 18, 0, 0.36, m_road)
    dashes(-40, apron, VX - 20, apron, m_white)
    for dy in (-9, 9):
        for off in (-3.2, 3.2):
            box(-40, apron + dy + off - 0.9, VX - 10, apron + dy + off + 0.9, 0.36, 0.375, m_tyre)
    # «зебра» у выезда на причал, напротив рампы судна
    for i in range(7):
        box(352 + i * 8, apron + 19, 357 + i * 8, quay - 9, 0.3, 0.33, m_white)
    for x in (320, 905):
        light_pole(x, 104, m_dark, m_lamp, h=70)
    for x in (16, 603, 1190):
        light_pole(x, 420, m_dark, m_lamp, h=70)
    for x in (200, 560, 900):
        light_pole(x, quay - 14, m_dark, m_lamp, h=60)
    # будка охраны у въезда
    box(60, 64, 80, 78, 0, 12, m_lamp, bevel=1)
    box(58, 62, 82, 80, 12, 13.5, m_dark)
    bx = 40
    while bx < VX - 20:
        bpy.ops.mesh.primitive_cylinder_add(radius=3, depth=6, location=(bx, -(quay + 2), 3))
        bpy.context.object.data.materials.append(m_dark)
        bx += 80

    # Владивосток: площадка чуть выше причала, красная кромка со стороны моря и стоянок, три больших места под машины
    box(VX, road + 20, W + 40, H + 60, -6, 1.2, m_vlad)
    box(VX - 5, road + 20, VX, H + 60, -6, 1.6, m_red)
    m_vline = mat("vline", (0.2, 0.22, 0.25), rough=0.7)
    for i in range(3):
        y = 96 + i * 182
        for (x0_, y0_, x1_, y1_) in ((VX + 20, y, W - 20, y), (VX + 20, y + 164, W - 20, y + 164)):
            paint_line(x0_, y0_, x1_, y1_, 1.8, m_vline, z=1.5)
        paint_line(VX + 20, y, VX + 20, y + 164, 1.8, m_vline, z=1.5)
        paint_line(W - 20, y, W - 20, y + 164, 1.8, m_vline, z=1.5)
        ground_text(W - 44, y + 146, f"B{i + 1}", 16, m_vline, z=1.5)
    return W, H


def yard_narrow():
    k = NARROW
    W, H, lane, quay = k["W"], k["H"], k["lane"], k["quay"]
    m_ground = noisy("ground", (0.3, 0.3, 0.29), (0.38, 0.38, 0.37), scale=0.03)
    m_yard = noisy("yard", (0.2, 0.205, 0.21), (0.26, 0.265, 0.27), scale=0.05, stains=True)  # светлый бетон
    m_road = noisy("road", (0.09, 0.093, 0.1), (0.125, 0.128, 0.135), scale=0.06, stains=True)
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
        sc.view_settings.exposure = -0.75
        sky()
        s_ = sun()
        if kind == "route":  # низкое солнце: длинные мягкие тени от столбов, деревьев и бордюров
            s_.rotation_euler = (math.radians(42), 0, math.radians(-40))
            s_.data.angle = math.radians(3)
            s_.data.energy = 3.4
            s_.data.color = (1, 0.93, 0.82)
            sky((0.5, 0.62, 0.86), 0.5)
            sc.view_settings.exposure = -0.55
    W, H = yard_wide() if kind == "wide" else yard_route() if kind == "route" else yard_narrow()
    sc.render.resolution_x, sc.render.resolution_y = W * 2, H * 2
    top_camera(W / 2, -H / 2, max(W, H))
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)


# --- машины ------------------------------------------------------------------------------
# Метры. Нос — к −X (как в car.py), на спрайте нос смотрит вверх.
BODIES = {
    #        длина ширина  пояс  стекло от/до (доля длины от носа)  высота крыши
    "sedan": (4.8, 1.86, 0.95, 0.29, 0.86, 1.44),
    "suv": (4.6, 1.92, 1.05, 0.25, 0.95, 1.70),
    "hatch": (3.9, 1.76, 0.95, 0.27, 0.95, 1.50),
    "van": (5.1, 1.98, 1.05, 0.15, 0.97, 1.82),
}
PAINTS = {
    "white": ((0.72, 0.73, 0.74), 0.0), "pearl": ((0.72, 0.69, 0.62), 0.2), "silver": ((0.5, 0.52, 0.54), 0.85),
    "grey": ((0.26, 0.27, 0.29), 0.7), "graphite": ((0.07, 0.075, 0.085), 0.6), "black": ((0.012, 0.012, 0.014), 0.2),
    "blue": ((0.03, 0.12, 0.42), 0.6), "red": ((0.5, 0.02, 0.02), 0.3),
}
SPRITE_M = 6.0  # спрайт — 6 × 3 м, у всех кузовов один масштаб
SPRITE_PX = 64 * int(opts.get("--k", 3))  # ширина спрайта: на схеме машины крупные, рендерим с запасом под чёткие экраны


def build_car(kind, paint, glass, dark, lamp, tail):
    """Кузов сверху: скруглённые нос и корма, лобовое и заднее стекло, узкие боковые окна, крыша в цвет кузова."""
    L, Wd, belt, r0, r1, rh = BODIES[kind]
    hl = L / 2
    front = -hl
    boxy = kind in ("suv", "van")

    def cap(f, n=2.6, span=0.16):  # скругление углов у бамперов: 0 на торце, 1 дальше span от него
        d = min(f, 1 - f) / span
        return 1.0 if d >= 1 else (1 - (1 - d) ** n) ** (1 / n)

    hood = 0.84 if not boxy else 0.97
    wide = [(0, 0.9), (0.14, 0.985), (0.3, 1.0), (0.82, 1.0), (1, 0.93)]  # нос чуть уже кормы

    def body(x):
        f = (x - front) / L
        top = interp([(0, hood - 0.14), (0.1, hood), (r0, belt), (0.88, belt), (1, belt - 0.07)], f)
        bot = 0.3
        c = cap(f)
        return superellipse(0, (top + bot) / 2, Wd / 2 * interp(wide, f) * (0.5 + 0.5 * c), (top - bot) / 2 * (0.45 + 0.55 * c),
                            n=4.2 if boxy else 3.6, tumble=0.1)

    xs = [front + L * i / 160 for i in range(161)]
    car = [loft("body", xs, body)]
    car[0].data.materials.append(paint)

    # остекление: низ — по поясу, верх — крыша; лобовое длиннее заднего, у универсальных кузовов корма почти отвесная
    g0, g1 = front + L * r0, front + L * r1
    ws = 0.13 if not boxy else 0.115          # длина лобового стекла в долях длины
    rw = 0.115 if kind == "sedan" else 0.05   # заднее стекло
    p0, p1 = g0 + L * ws, g1 - L * rw

    def roof_z(x):
        return interp([(g0, belt - 0.01), (p0, rh), (p1, rh - 0.02), (g1, belt + (0.3 if boxy else 0.04))], x)

    def greenhouse(x):
        f = (x - g0) / (g1 - g0)
        bot = belt - 0.03
        top = max(roof_z(x), bot + 0.02)
        return superellipse(0, (top + bot) / 2, Wd / 2 * 0.86 * (0.9 + 0.1 * cap(f, span=0.2)), (top - bot) / 2, n=5, tumble=0.3)

    gx = [g0 + (g1 - g0) * i / 100 for i in range(101)]
    gh = loft("glass", gx, greenhouse)
    gh.data.materials.append(glass)

    # крыша в цвет кузова: чуть шире остекления сверху, с округлыми торцами — стекло видно спереди, сзади и узкой полосой по бокам
    ra, rb = p0 - L * 0.012, p1 + L * 0.012

    def roof(x):
        f = (x - ra) / (rb - ra)
        return superellipse(0, roof_z(max(min(x, p1), p0)) + 0.005, Wd / 2 * 0.86 * 0.7 * 0.83 * (0.86 + 0.14 * cap(f, n=2.2, span=0.12)) / 0.83,
                            0.075, n=2.6, m=32)

    rx = [ra + (rb - ra) * i / 60 for i in range(61)]
    rf = loft("roof", rx, roof)
    rf.data.materials.append(paint)
    car += [gh, rf]
    if boxy:  # панорамная крыша и рейлинги
        bpy.ops.mesh.primitive_cube_add(location=(p0 + (p1 - p0) * 0.36, 0, rh + 0.078))
        o = bpy.context.object
        o.scale = ((p1 - p0) * 0.26, Wd * 0.2, 0.012)
        o.data.materials.append(glass)
        b = o.modifiers.new("b", "BEVEL")
        b.width = 0.06
        b.segments = 3
        car.append(o)
        for side in (-1, 1):
            bpy.ops.mesh.primitive_cube_add(location=((p0 + p1) / 2, side * Wd * 0.262, rh + 0.05))
            o = bpy.context.object
            o.scale = ((p1 - p0) * 0.42, 0.022, 0.022)
            o.data.materials.append(dark)
            car.append(o)
    for side in (-1, 1):  # зеркала, фары, фонари
        bpy.ops.mesh.primitive_cube_add(location=(g0 + 0.3, side * (Wd / 2 + 0.07), belt + 0.04))
        o = bpy.context.object
        o.scale = (0.07, 0.1, 0.05)
        o.rotation_euler.z = side * math.radians(-18)
        o.data.materials.append(paint)
        o.modifiers.new("b", "BEVEL").width = 0.03
        # фары и фонари — узкие полоски, утопленные в кузов: сверху видна только кромка
        bpy.ops.mesh.primitive_cube_add(location=(front + 0.3, side * Wd * 0.31, hood - 0.085))
        o2 = bpy.context.object
        o2.scale = (0.045, 0.17, 0.04)
        o2.rotation_euler.z = side * math.radians(16)
        o2.data.materials.append(lamp)
        bpy.ops.mesh.primitive_cube_add(location=(hl - 0.17, side * Wd * 0.3, belt - 0.085))
        o3 = bpy.context.object
        o3.scale = (0.035, 0.2, 0.04)
        o3.rotation_euler.z = side * math.radians(-9)
        o3.data.materials.append(tail)
        car += [o, o2, o3]
    piv = bpy.data.objects.new("car", None)
    bpy.context.collection.objects.link(piv)
    for p in car:
        p.parent = piv
    piv.rotation_euler.z = math.radians(-90)  # нос вверх на спрайте
    return piv


def render_cars(out):
    os.makedirs(out, exist_ok=True)
    only = opts.get("--only")
    for kind in BODIES:
        for name, (color, metal) in PAINTS.items():
            if only and f"{kind}-{name}" not in only.split(","):
                continue
            sc = reset()
            sc.cycles.samples = SAMPLES
            sc.render.resolution_x, sc.render.resolution_y = SPRITE_PX, SPRITE_PX * 2
            sky((0.55, 0.66, 0.9), 0.55)  # небо даёт мягкую тень вокруг кузова и блики на стёклах
            s = sun(2.6)
            s.rotation_euler = (0, 0, 0)  # тень под машиной: спрайт поворачивается вместе с ней
            s.data.angle = math.radians(30)
            s.visible_glossy = False  # солнце в зените отражалось бы от крыши прямо в камеру и выбеливало её
            paint = mat("paint", color, rough=0.3, metal=metal, coat=0.45)
            glass = mat("glass", (0.012, 0.02, 0.03), rough=0.04, metal=0.75)
            dark = mat("dark", (0.03, 0.03, 0.032), rough=0.5)
            lamp = mat("lamp", (0.85, 0.87, 0.9), rough=0.1, emit=(1, 0.97, 0.9), emit_s=0.5)
            tail = mat("tail", (0.45, 0.01, 0.01), rough=0.2, emit=(1, 0.03, 0.02), emit_s=0.35)
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
