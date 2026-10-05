import sys, math, bpy
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from common import *
import car as carmod

args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
W, H, S = int(args.get('--w', 960)), int(args.get('--h', 600)), int(args.get('--s', 32))
sc = reset(); sc.render.resolution_x, sc.render.resolution_y = W, H; sc.cycles.samples = S
sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'
sc.world.node_tree.nodes['Background'].inputs[1].default_value = 0.25

RED = mat('red', (0.7, 0.012, 0.015), rough=0.32, coat=0.5)
DARK = mat('dark', (0.02, 0.02, 0.022), rough=0.4)
PAINT = mat('paint', (0.006, 0.006, 0.008), rough=0.12, metal=0.0, coat=1.0)
GLASS = mat('glass', (0.004, 0.005, 0.008), rough=0.03, metal=0.8)
TIRE = mat('tire', (0.012, 0.012, 0.012), rough=0.75)
RIM = mat('rim', (0.07, 0.07, 0.075), rough=0.3, metal=1.0)
LAMP = mat('lamp', (1, 1, 1), emit=(1, 0.96, 0.9), emit_s=12)
TAIL = mat('tail', (0.8, 0.02, 0.02), emit=(1, 0.04, 0.02), emit_s=8)

# torii
GX, TY = 3.0, 2.2
for x in (-GX, GX):
    bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=0.21, radius2=0.17, depth=4.3, location=(x, TY, 2.15))
    link(bpy.context.object, RED); shade(bpy.context.object, 0.02)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.27, depth=0.3, location=(x, TY, 0.15))
    link(bpy.context.object, DARK); shade(bpy.context.object, 0.04)
Lk = 4.7; k = []
for i in range(41):
    x = -Lk + 2 * Lk * i / 40; t = abs(x) / Lk
    k.append((x, 4.62 + 0.5 * t ** 3))
o = extrude_profile('kasagi', [(x, z) for x, z in k] + [(x, z + 0.3 + 0.08 * (abs(x) / Lk) ** 2) for x, z in reversed(k)], 0.6)
o.location.y = TY; link(o, RED); shade(o, 0.035)
o = extrude_profile('kasagi_dark', [(x * 0.99, z - 0.1) for x, z in k] + [(x * 0.99, z + 0.01) for x, z in reversed(k)], 0.66)
o.location.y = TY; link(o, DARK); shade(o, 0.02)
for loc, s in (((0, TY, 4.38), (4.3, 0.24, 0.13)), ((0, TY, 3.5), (3.85, 0.15, 0.17)), ((0, TY, 3.95), (0.14, 0.13, 0.3))):
    bpy.ops.mesh.primitive_cube_add(location=loc); o = bpy.context.object; o.scale = s; link(o, RED); shade(o, 0.03)

car = carmod.build(PAINT, GLASS, TIRE, RIM, LAMP, TAIL)
car.location = (float(args.get('--cx', -0.5)), -0.3, 0); car.rotation_euler.z = math.radians(float(args.get('--rot', -18)))
car.scale = (1.12,) * 3

bpy.ops.mesh.primitive_plane_add(size=80); fl = bpy.context.object; fl.is_shadow_catcher = True

area_light('key', (-7, -8, 9), (0, 0, 1), 7, 2600)
area_light('rim', (4, 7, 6), (0, 0, 1.2), 5, 2500, (1, 0.5, 0.45))
area_light('fill', (9, -7, 3), (0, 0, 1), 7, 900, (0.85, 0.9, 1))
area_light('strip', (-1, -5, 6), (0, 0, 0.8), 1.2, 600)
camera((-6.8, -17.5, 3.4), (0.0, 0.6, 2.45), lens=float(args.get('--lens', 55)))
sc.render.filepath = args.get('--out', 'hero_preview.png')
bpy.ops.render.render(write_still=True)
