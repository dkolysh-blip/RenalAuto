"""Картинка-превью ссылки на машину (1200×630) для мессенджеров и соцсетей.

Слева — логотип, название, ≈ цена с растаможкой и цветная полоска «из чего она складывается»,
справа — фото машины. Цвета полоски те же, что в карточке на сцене порта.
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
FONTS = HERE / "fonts"
W, H, SPLIT = 1200, 630, 600
BG, INK, MUTED = (245, 246, 248), (22, 25, 29), (102, 112, 133)
LINES = {  # ключ строки расклада → подпись и цвет, как в port.js
    "car": ("Машина", (11, 92, 143)),
    "duty": ("Пошлина", (221, 31, 31)),
    "fees": ("Сборы", (242, 165, 49)),
    "fee": ("Комиссия", (22, 25, 29)),
}


@lru_cache(maxsize=None)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size)


@lru_cache(maxsize=1)
def logo() -> Image.Image:
    # логотип берём из общего превью сайта: тот же фон, не нужно рисовать SVG
    return Image.open(HERE / "static/brand/og.jpg").convert("RGB").crop((60, 60, 380, 175))


def money(rub: float) -> str:
    if rub >= 1_000_000:
        return f"{rub / 1_000_000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " млн ₽"
    return f"{round(rub):,}".replace(",", " ") + " ₽"


def wrap(d: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int, lines: int) -> list[str]:
    out, cur = [], ""
    for word in text.split():
        nxt = f"{cur} {word}".strip()
        if d.textlength(nxt, font=f) <= width or not cur:
            cur = nxt
            continue
        out.append(cur)
        cur = word
    out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        while d.textlength(out[-1] + "…", font=f) > width and " " in out[-1]:
            out[-1] = out[-1].rsplit(" ", 1)[0]
        out[-1] += "…"
    return out


def cover(photo: bytes | None) -> Image.Image | None:
    if not photo:
        return None
    try:
        im = Image.open(io.BytesIO(photo)).convert("RGB")
    except Exception:  # noqa: BLE001 — битая картинка: превью без фото
        return None
    w, h = W - SPLIT, H
    k = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def render_car(*, title: str, sub: str, total: float | None, lines: list[dict] | None,
               country: str, photo: bytes | None) -> bytes:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    pic = cover(photo)
    if pic is not None:
        mask = Image.new("L", pic.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, pic.width + 40, pic.height), 36, fill=255)
        im.paste(pic, (SPLIT, 0), mask)
        # плашка страны поверх фото
        tag = "Корея" if country == "KR" else "Китай"
        f = font("Onest-Bold", 26)
        tw = d.textlength(tag, font=f)
        d.rounded_rectangle((SPLIT + 28, 28, SPLIT + 60 + tw, 76), 24, fill=(255, 255, 255))
        d.text((SPLIT + 44, 52), tag, font=f, fill=INK, anchor="lm")
    else:  # фото нет — справа сцена порта из общего превью сайта
        im.paste(Image.open(HERE / "static/brand/og.jpg").convert("RGB").crop((640, 0, W, H)), (640, 0))

    x, wmax = 64, SPLIT - 64 - 40
    im.paste(logo().resize((256, 92), Image.LANCZOS), (x - 8, 44))

    y = 182
    ft = font("Unbounded-Bold", 40)
    for ln in wrap(d, title, ft, wmax, 2):
        d.text((x, y), ln, font=ft, fill=INK)
        y += 52
    d.text((x, y + 4), sub, font=font("Onest-Medium", 28), fill=MUTED)

    y = 384
    if total:
        d.text((x, y), "≈ " + money(total), font=font("Unbounded-Bold", 58), fill=INK)
        d.text((x, y + 80), "с растаможкой и нашей комиссией", font=font("Onest-Medium", 26), fill=MUTED)
        parts = [ln for ln in (lines or []) if ln.get("rub")]
        sum_ = sum(ln["rub"] for ln in parts) or 1
        bx, by, bw = x, y + 128, wmax
        cx = bx
        for i, ln in enumerate(parts):
            seg = bw * ln["rub"] / sum_ if i < len(parts) - 1 else bx + bw - cx
            d.rectangle((cx, by, cx + seg, by + 14), fill=LINES[ln["k"]][1])
            cx += seg
        # скруглить концы полоски — закрасить углы фоном
        rmask = Image.new("L", (bw, 14), 0)
        ImageDraw.Draw(rmask).rounded_rectangle((0, 0, bw - 1, 13), 7, fill=255)
        bar = im.crop((bx, by, bx + bw, by + 14))
        im.paste(Image.new("RGB", bar.size, BG), (bx, by))
        im.paste(bar, (bx, by), rmask)
        lx, f = x, font("Onest-Medium", 22)
        for ln in parts:
            label, color = LINES[ln["k"]]
            d.ellipse((lx, by + 36, lx + 12, by + 48), fill=color)
            d.text((lx + 20, by + 42), label, font=f, fill=INK, anchor="lm")
            lx += 20 + d.textlength(label, font=f) + 26
    else:
        d.text((x, y), "Цену с растаможкой", font=font("Unbounded-Bold", 40), fill=INK)
        d.text((x, y + 54), "посчитает менеджер", font=font("Unbounded-Bold", 40), fill=INK)

    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()
