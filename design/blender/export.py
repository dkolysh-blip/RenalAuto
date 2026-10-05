"""Обрезает рендер по объекту, плавно гасит тень к краям и сохраняет renalauto/static/hero.webp."""
import sys
from PIL import Image, ImageChops

src = sys.argv[1] if len(sys.argv) > 1 else "final.png"
dst = sys.argv[2] if len(sys.argv) > 2 else "../../renalauto/static/hero.webp"
im = Image.open(src)
l, t, r, b = im.getchannel("A").point(lambda v: 255 if v > 90 else 0).getbbox()
m = fade = 150
im = im.crop((max(l - m, 0), max(t - m, 0), min(r + m, im.width), min(b + m, im.height)))
W, H = im.size


def ramp(d):
    x = max(0.0, min(1.0, d / fade))
    return x * x * (3 - 2 * x)


col = Image.new("L", (W, 1)); col.putdata([int(255 * ramp(min(x, W - 1 - x))) for x in range(W)])
row = Image.new("L", (1, H)); row.putdata([int(255 * ramp(min(y, H - 1 - y))) for y in range(H)])
im.putalpha(ImageChops.multiply(im.getchannel("A"), ImageChops.multiply(col.resize((W, H)), row.resize((W, H)))))
im.thumbnail((1400, 1400), Image.LANCZOS)
im.save(dst, quality=86, method=6)
print(dst, im.size)
