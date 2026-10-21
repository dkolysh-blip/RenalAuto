"""Карта для блока «Путь машины»: страны из Natural Earth 1:110m → SVG-контуры.

    pip install 'geopandas==0.14.4'   # в этой версии датасет naturalearth_lowres встроен
    python journey_map.py             # пишет renalauto/templates/_journey_land.svg и печатает координаты точек
"""
import math
import warnings
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

warnings.filterwarnings("ignore")
LON0, LON1, LAT0, LAT1 = 112.0, 146.0, 32.5, 51.5
W = 1000
K = math.cos(math.radians((LAT0 + LAT1) / 2))
H = round(W * (LAT1 - LAT0) / ((LON1 - LON0) * K))


def xy(lon, lat):
    return (lon - LON0) / (LON1 - LON0) * W, (LAT1 - lat) / (LAT1 - LAT0) * H


def chaikin(pts, n=2):
    """Срезаем углы грубого контура 1:110m — берег выглядит естественнее."""
    for _ in range(n):
        out = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            out += [(.75 * x0 + .25 * x1, .75 * y0 + .25 * y1), (.25 * x0 + .75 * x1, .25 * y0 + .75 * y1)]
        pts = out
    return pts


def ring(coords):
    pts = chaikin([xy(*c[:2]) for c in coords[:-1]])
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
names = {"Russia": "ru", "China": "cn", "South Korea": "kr", "North Korea": "kp", "Japan": "jp", "Mongolia": "mn"}
clip = box(LON0 - 2, LAT0 - 2, LON1 + 2, LAT1 + 2)
out = []
for _, row in world[world.name.isin(names)].iterrows():
    g = row.geometry.intersection(clip)
    if g.is_empty:
        continue
    polys = getattr(g, "geoms", [g])
    d = " ".join(ring(p.exterior.coords) for p in polys if p.geom_type == "Polygon")
    out.append(f'<path class="j-land land-{names[row["name"]]}" d="{d}"/>')

dst = Path(__file__).resolve().parents[2] / "renalauto" / "templates" / "_journey_land.svg"
dst.write_text(f"{{# сгенерировано design/map/journey_map.py, viewBox 0 0 {W} {H} #}}\n" + "\n".join(out) + "\n")
print("viewBox", W, H)
for name, lon, lat in [("Vladivostok", 131.9, 43.1), ("Ussuriysk", 131.95, 43.8), ("Busan", 129.04, 35.1),
                       ("Incheon", 126.6, 37.45), ("Harbin", 126.6, 45.75), ("Suifenhe", 131.15, 44.4),
                       ("Khabarovsk", 135.07, 48.48), ("Birobidzhan", 132.9, 48.8), ("Belogorsk", 128.5, 50.9),
                       ("Shenyang", 123.4, 41.8), ("Changchun", 125.3, 43.9)]:
    x, y = xy(lon, lat)
    print(f"{name:12s} {x:6.1f} {y:6.1f}")
