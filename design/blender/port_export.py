"""Рендеры port.py → renalauto/static/port/*.webp (подложки, судно, спрайты машин).

    python port_export.py <папка с рендерами>   # подложки дня и ночи, судно, машины — что найдётся
"""
import sys
from pathlib import Path

from PIL import Image

src = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
dst = Path(__file__).resolve().parents[2] / "renalauto" / "static" / "port"
(dst / "cars").mkdir(parents=True, exist_ok=True)

# что есть в папке рендеров — то и обновляем (можно перерендерить только подложки)
for name in ("yard-wide", "yard-narrow", "yard-wide-night", "yard-narrow-night"):
    if (src / f"{name}.png").exists():
        Image.open(src / f"{name}.png").convert("RGB").save(dst / f"{name}.webp", quality=80, method=6)
if (src / "ship.png").exists():
    Image.open(src / "ship.png").save(dst / "ship.webp", quality=88, method=6)
for png in sorted((src / "cars").glob("*.png")) if (src / "cars").exists() else []:
    Image.open(png).save(dst / "cars" / f"{png.stem}.webp", quality=90, method=6)

total = sum(f.stat().st_size for f in dst.rglob("*.webp"))
print(f"{dst}: {len(list(dst.rglob('*.webp')))} файлов, {total // 1024} КБ")
