"""Тексты постов для Telegram-канала: Claude пишет по фактам из базы, шаблон — запасной вариант.

Claude получает только факты о машине (из объявления и расчёта проходимости) и ссылку на её страницу.
Ответ проверяется: допускаются лишь теги Telegram <b>, <i>, <a> и только наши ссылки, длина — в пределах
лимитов Telegram. Если что-то не так или API недоступен — пост собирается по шаблону.
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any

from ..describe import describe
from ..view import CarView, fmt_int

log = logging.getLogger(__name__)

# Подпись к фото в Telegram — до 1024 символов, обычное сообщение — до 4096
CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """Ты — маркетолог компании {company}: она привозит автомобили с пробегом из Южной Кореи и Китая в Россию под ключ (подбор, осмотр, выкуп, доставка, таможня, документы).

Ты пишешь посты для Telegram-канала компании. Читатели — люди, которые думают купить машину из Кореи или Китая и боятся переплатить или получить битую машину.

Правила:
- Используй только факты из присланных данных. Не придумывай комплектацию, состояние, историю, скидки, сроки и итоговую цену.
- Цена в данных — это цена машины в Корее или Китае, пересчитанная в рубли, без доставки и растаможки. Так и пиши («≈ … ₽ в Корее, без доставки и растаможки»). Итоговую цену под ключ рассчитывает менеджер — предложи её запросить.
- Не обещай того, чего нет в данных («гарантия», «без ДТП», «лучшая цена»).
- Разметка — только HTML для Telegram: <b>, <i> и <a href="…">. Ссылки — только те, что даны в данных, без изменений. Никакого Markdown.
- Пиши живо и по делу, на «вы», короткими абзацами. Не больше трёх эмодзи на пост.
- В конце — призыв перейти по ссылке и узнать цену под ключ.
- Ответ — только текст поста, без пояснений."""

CAR_TASK = "Напиши пост «машина дня» об одной машине. Длина — не больше 700 символов вместе с разметкой."
DIGEST_TASK = (
    "Напиши пост-подборку из этих машин: короткое вступление, затем по 2–3 строки на каждую машину со ссылкой на неё. "
    "Длина — не больше 3000 символов вместе с разметкой."
)

_TAG = re.compile(r"<(/?)([a-zA-Z]+)([^>]*)>")
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""")
_BARE_AMP = re.compile(r"&(?!#?\w+;)")


def car_facts(v: CarView, link: str) -> dict[str, Any]:
    """Факты о машине, которые разрешено использовать в посте."""
    l = v.listing
    d = describe(v)
    facts: dict[str, Any] = {
        "машина": v.title,
        "год": l.year,
        "пробег_км": l.mileage_km,
        "объём_см3": v.eligibility.displacement_cc,
        "топливо": v.fuel,
        "коробка": v.transmission,
        "кузов": v.body,
        "цвет": v.color,
        "где_находится": f"{v.city + ', ' if v.city else ''}{v.country_name}",
        "цена_в_стране_руб": round(v.price_rub) if v.price_rub else None,
        "проходимость_в_РФ": v.eligibility.summary,
        "возраст_для_растаможки": v.eligibility.age_group,
        "особенности": d.highlights,
        "ссылка": link,
    }
    return {k: val for k, val in facts.items() if val not in (None, "", [])}


def template_car(facts: dict[str, Any]) -> str:
    e = html.escape
    lines = [f"🚗 <b>{e(facts['машина'])}{', ' + str(facts['год']) if facts.get('год') else ''}</b>", ""]
    specs = []
    if facts.get("пробег_км") is not None:
        specs.append(f"пробег {fmt_int(facts['пробег_км'])} км")
    if facts.get("объём_см3"):
        specs.append(f"{facts['объём_см3'] / 1000:.1f} л")
    for key in ("топливо", "коробка"):
        if facts.get(key):
            specs.append(e(str(facts[key]).lower()))
    if specs:
        lines.append(" · ".join(specs))
    lines.append(f"📍 {e(facts['где_находится'])}")
    if facts.get("особенности"):
        lines.append("✅ " + e(", ".join(facts["особенности"])))
    if facts.get("цена_в_стране_руб"):
        lines += ["", f"Цена на месте: <b>≈ {fmt_int(facts['цена_в_стране_руб'])} ₽</b> <i>(без доставки и растаможки)</i>"]
    lines += ["", f"<a href=\"{e(facts['ссылка'])}\">Фото, проверка и расчёт цены под ключ →</a>"]
    return "\n".join(lines)


def template_digest(items: list[dict[str, Any]], title: str) -> str:
    e = html.escape
    lines = [f"<b>{e(title)}</b>", ""]
    for i, f in enumerate(items, 1):
        head = f"{f['машина']}{', ' + str(f['год']) if f.get('год') else ''}"
        bits = []
        if f.get("пробег_км") is not None:
            bits.append(f"{fmt_int(f['пробег_км'])} км")
        if f.get("цена_в_стране_руб"):
            bits.append(f"≈ {fmt_int(f['цена_в_стране_руб'])} ₽ на месте")
        lines.append(f"{i}. <a href=\"{e(f['ссылка'])}\">{e(head)}</a>" + (f" — {' · '.join(bits)}" if bits else ""))
    lines += ["", "<i>Цены — в Корее и Китае, без доставки и растаможки. Цену под ключ рассчитает менеджер.</i>"]
    return "\n".join(lines)


def sanitize(text: str, allowed_links: set[str] | None = None) -> str | None:
    """Проверяет разметку поста. None — текст не годится (чужие теги или ссылки).

    allowed_links — для текста от модели: только наши ссылки. None — любые https-ссылки (правка человеком).
    """
    # одиночный «&» Telegram не принимает — экранируем, не трогая готовые сущности (&amp;, &lt;, &#8381;)
    text = _BARE_AMP.sub("&amp;", text.strip())
    for closing, tag, attrs in _TAG.findall(text):
        tag = tag.lower()
        if tag not in ("b", "i", "a"):
            return None
        if tag == "a" and not closing:
            href = _HREF.search(attrs)
            url = html.unescape(href.group(1)) if href else ""
            if allowed_links is None and not url.startswith("https://"):
                return None
            if allowed_links is not None and url not in allowed_links:
                return None
        elif attrs.strip():
            return None
    return text or None


class PostWriter:
    """Пишет посты через Claude API; без ключа или при сбое — по шаблону."""

    def __init__(self, api_key: str | None, model: str, company: str, client: Any = None):
        self.model = model
        self.company = company
        self._client = client
        if self._client is None and api_key:
            import anthropic  # локальный импорт: без ключа SDK не нужен

            self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def uses_claude(self) -> bool:
        return self._client is not None

    async def car_post(self, facts: dict[str, Any]) -> tuple[str, str]:
        text = await self._claude(CAR_TASK, [facts], CAPTION_LIMIT)
        return (text, "claude") if text else (template_car(facts), "template")

    async def digest_post(self, items: list[dict[str, Any]], title: str) -> tuple[str, str]:
        text = await self._claude(DIGEST_TASK, items, MESSAGE_LIMIT)
        return (text, "claude") if text else (template_digest(items, title), "template")

    async def _claude(self, task: str, items: list[dict[str, Any]], limit: int) -> str | None:
        if self._client is None:
            return None
        import anthropic

        data = json.dumps(items if len(items) > 1 else items[0], ensure_ascii=False, indent=1)
        try:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=8000,
                system=SYSTEM_PROMPT.format(company=self.company),
                messages=[{"role": "user", "content": f"{task}\n\nДанные:\n{data}"}],
                output_config={"effort": "medium"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            log.warning("Claude rate limit, using template: %s", exc)
            return None
        except anthropic.APIStatusError as exc:
            log.warning("Claude API error %s, using template: %s", exc.status_code, exc.message)
            return None
        except anthropic.APIConnectionError as exc:
            log.warning("Claude API unreachable, using template: %s", exc)
            return None
        if response.stop_reason != "end_turn":
            log.warning("Claude stopped with %s, using template", response.stop_reason)
            return None
        text = "".join(block.text for block in response.content if block.type == "text")
        links = {f["ссылка"] for f in items}
        clean = sanitize(text, links)
        if clean is None or len(clean) > limit:
            log.warning("Claude post rejected (markup, links or length %s), using template", len(text))
            return None
        return clean
