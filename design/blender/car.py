import bpy, bmesh, math
from mathutils import Vector

def interp(pts, x):
    """piecewise smoothstep interpolation through (x, v) control points"""
    if x <= pts[0][0]: return pts[0][1]
    for (x0, v0), (x1, v1) in zip(pts, pts[1:]):
        if x <= x1:
            t = (x - x0) / (x1 - x0); t = t * t * (3 - 2 * t)
            return v0 + (v1 - v0) * t
    return pts[-1][1]

def loft(name, xs, section):
    """section(x) -> list of (y, z) ring (same count). Closed ends with fans."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rings = []
    for x in xs:
        rings.append([bm.verts.new((x, y, z)) for y, z in section(x)])
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    for ring, rev in ((rings[0], True), (rings[-1], False)):
        c = sum((v.co for v in ring), Vector()) / n
        cv = bm.verts.new(c)
        for i in range(n):
            j = (i + 1) % n
            f = (ring[i], ring[j], cv)
            bm.faces.new(f[::-1] if rev else f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    for p in me.polygons: p.use_smooth = True
    return ob

def superellipse(cy, cz, hw, hh, n=4.0, m=40, tumble=0.0):
    out = []
    for k in range(m):
        a = 2 * math.pi * k / m
        c, s = math.cos(a), math.sin(a)
        y = hw * math.copysign(abs(c) ** (2 / n), c)
        z = hh * math.copysign(abs(s) ** (2 / n), s)
        if z > 0: y *= 1 - tumble * (z / hh) ** 2
        out.append((cy + y, cz + z))
    return out

L = 2.45
BELT = [(-L, 0.66), (-2.0, 0.74), (-0.95, 0.92), (1.2, 0.98), (2.1, 0.96), (L, 0.88)]
BOT = [(-L, 0.42), (-2.0, 0.27), (2.0, 0.27), (L, 0.4)]
ROOF = [(-1.0, 0.93), (-0.1, 1.36), (0.7, 1.38), (1.55, 1.18), (2.15, 0.99)]

def endf(x, p=5.0):
    t = min(abs(x) / L, 0.99999)
    return (1 - t ** p) ** (1 / p)

def body_section(x):
    top, bot = interp(BELT, x), interp(BOT, x)
    f = endf(x)
    cz, hh = (top + bot) / 2, (top - bot) / 2 * (0.25 + 0.75 * f)
    return superellipse(0, cz, 0.93 * (0.35 + 0.65 * f), hh, n=5, tumble=0.12)

def glass_section(x):
    bot = interp(BELT, x) - 0.03
    top = max(interp(ROOF, x), bot + 0.005)
    cz, hh = (top + bot) / 2, (top - bot) / 2
    return superellipse(0, cz, 0.74, hh, n=6, tumble=0.25)

def build(paint, glass, tire, rim, lamp, tail):
    xs = [-L + 2 * L * (i / 120) for i in range(121)]
    body = loft('body', xs, body_section)
    body.data.materials.append(paint)
    gx = [-1.0 + 3.15 * (i / 80) for i in range(81)]
    gh = loft('glass', gx, glass_section); gh.data.materials.append(glass)
    # roof panel: slightly narrower, thin, on top of glass
    def roof_section(x):
        top = interp(ROOF, x) + 0.012
        return superellipse(0, top - 0.02, 0.6, 0.035, n=4, m=24)
    rx = [-0.15 + 1.75 * (i / 50) for i in range(51)]
    rf = loft('roof', rx, roof_section); rf.data.materials.append(paint)
    parts = [body, gh, rf]
    WX = 1.52
    for x in (-WX, WX):
        # wheel arch cut
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.47, depth=2.4, location=(x, 0, 0.4), rotation=(math.pi / 2, 0, 0))
        cut = bpy.context.object
        m = body.modifiers.new('arch', 'BOOLEAN'); m.object = cut; m.operation = 'DIFFERENCE'; m.solver = 'EXACT'
        cut.hide_render = True; cut.hide_viewport = True
        for y in (-0.8, 0.8):
            bpy.ops.mesh.primitive_cylinder_add(vertices=72, radius=0.41, depth=0.28, location=(x, y, 0.41), rotation=(math.pi / 2, 0, 0))
            t = bpy.context.object; t.data.materials.append(tire)
            b = t.modifiers.new('b', 'BEVEL'); b.width = 0.07; b.segments = 5
            for p in t.data.polygons: p.use_smooth = True
            bpy.ops.mesh.primitive_cylinder_add(vertices=72, radius=0.29, depth=0.29, location=(x, y * 1.005, 0.41), rotation=(math.pi / 2, 0, 0))
            r = bpy.context.object; r.data.materials.append(rim)
            b = r.modifiers.new('b', 'BEVEL'); b.width = 0.02; b.segments = 2
            parts += [t, r]
            # spokes
            for k in range(5):
                a = 2 * math.pi * k / 5
                bpy.ops.mesh.primitive_cube_add(location=(x, y * 1.03, 0.41), rotation=(0, a, 0))
                s = bpy.context.object; s.scale = (0.26, 0.02, 0.04); s.data.materials.append(rim)
                s.location.x += 0.0
                parts.append(s)
    body.modifiers.new('wn', 'WEIGHTED_NORMAL')
    # lamps: thin light bars
    for side in (-1, 1):
        bpy.ops.mesh.primitive_cube_add(location=(-L + 0.1, side * 0.55, 0.62), rotation=(0, math.radians(-35), math.radians(side * -12)))
        o = bpy.context.object; o.scale = (0.03, 0.26, 0.022); o.data.materials.append(lamp); parts.append(o)
    bpy.ops.mesh.primitive_cube_add(location=(L - 0.06, 0, 0.83))
    o = bpy.context.object; o.scale = (0.03, 0.82, 0.02); o.data.materials.append(tail); parts.append(o)
    piv = bpy.data.objects.new('car', None); bpy.context.collection.objects.link(piv)
    for p in parts: p.parent = piv
    for o in bpy.data.objects:
        if o.name.startswith('Cylinder') and o.hide_render: o.parent = piv
    return piv
