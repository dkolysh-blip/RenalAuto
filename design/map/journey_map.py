"""Карта для блока «Путь машины»: Natural Earth 1:50m → SVG-контуры стран, озёр и рек.

    # данные (public domain): https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
    #   ne_50m_admin_0_countries.geojson, ne_50m_lakes.geojson, ne_50m_rivers_lake_centerlines.geojson
    pip install shapely
    python journey_map.py <папка с geojson>   # пишет renalauto/templates/_journey_land.svg, печатает координаты точек

Проекция равнопромежуточная: 112–146° в. д. и 32,5–51,5° с. ш. ложатся в 1000 × 752.
Контуры рисуются и за этими границами — камера блока отъезжает и приближается.
"""
import json
import math
import sys
from pathlib import Path

from shapely.geometry import box, shape

src = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
LON0, LON1, LAT0, LAT1 = 112.0, 146.0, 32.5, 51.5
W = 1000
K = math.cos(math.radians((LAT0 + LAT1) / 2))
H = round(W * (LAT1 - LAT0) / ((LON1 - LON0) * K))
CLIP = box(100, 24, 160, 62)
TOL = 0.04  # упрощение контура, градусы (~1,2 px карты)


def xy(lon, lat):
    return (lon - LON0) / (LON1 - LON0) * W, (LAT1 - lat) / (LAT1 - LAT0) * H


def line(coords, close):
    pts = [xy(*c[:2]) for c in coords]
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    return d + (" Z" if close else "")


def polys(g):
    return [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and p.area > 0.02]


def load(name):
    return json.loads((src / f"{name}.geojson").read_text())["features"]


out = []
names = {"Russia": "ru", "China": "cn", "South Korea": "kr", "North Korea": "kp", "Japan": "jp", "Mongolia": "mn"}
for f in load("ne_50m_admin_0_countries"):
    code = names.get(f["properties"]["NAME"])
    if not code:
        continue
    g = shape(f["geometry"]).intersection(CLIP).simplify(TOL)
    d = " ".join(line(p.exterior.coords, True) for p in polys(g))
    out.append(f'<path class="j-land land-{code}" d="{d}"/>')
for f in load("ne_50m_lakes"):
    g = shape(f["geometry"]).intersection(CLIP).simplify(TOL)
    if not g.is_empty:
        out += [f'<path class="j-lake" d="{line(p.exterior.coords, True)}"/>' for p in polys(g)]
for f in load("ne_50m_rivers_lake_centerlines"):
    g = shape(f["geometry"]).intersection(CLIP).simplify(TOL)
    for ln in getattr(g, "geoms", [g]):
        if ln.geom_type == "LineString" and ln.length > 1.5:
            out.append(f'<path class="j-river" d="{line(ln.coords, False)}"/>')

dst = Path(__file__).resolve().parents[2] / "renalauto" / "templates" / "_journey_land.svg"
dst.write_text(f"{{# сгенерировано design/map/journey_map.py из Natural Earth 1:50m, система координат 0 0 {W} {H} #}}\n"
               + "\n".join(out) + "\n")
print("map", W, H, f"{dst.stat().st_size // 1024} КБ")
for name, lon, lat in [("Vladivostok", 131.9, 43.12), ("Ussuriysk", 131.95, 43.8), ("Busan", 129.04, 35.1),
                       ("Harbin", 126.63, 45.75), ("Mudanjiang", 129.6, 44.58), ("Suifenhe", 131.15, 44.4),
                       ("Khabarovsk", 135.07, 48.48), ("Birobidzhan", 132.92, 48.79), ("Belogorsk", 128.47, 50.92),
                       ("Svobodny", 128.13, 51.38), ("YourCity", 119.5, 50.8)]:
    x, y = xy(lon, lat)
    print(f"{name:12s} {x:6.1f} {y:6.1f}")
