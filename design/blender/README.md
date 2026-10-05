# 3D-картинка главной (Blender)

Сцена «машина под воротами-тории» по мотивам логотипа собирается скриптом, без ручной работы в Blender.

```bash
pip install bpy pillow           # bpy = Blender как модуль Python
cd design/blender
python hero.py --w 2000 --h 1600 --s 160 --lens 50 --out final.png   # ~5 мин на CPU
python export.py final.png ../../renalauto/static/hero.webp
```

- `common.py` — сцена, материалы, свет, камера; `car.py` — кузов лофтом по сечениям; `hero.py` — композиция.
- Фон прозрачный (тень — shadow catcher), поэтому картинка подходит и для светлой, и для тёмной темы.
- Быстрый черновик: `python hero.py --out draft.png` (960×600, 32 сэмпла).
