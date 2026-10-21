"""Агент-маркетолог: регулярно готовит посты для Telegram-канала из свежих машин в базе.

Цикл: отобрать проходные машины с фото и ценой, о которых ещё не писали → написать посты
(Claude или шаблон) → сохранить черновики → сообщить менеджеру. Публикует человек кнопкой
в /admin/marketing (или сразу, если включён MARKETING_AUTOPUBLISH).
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from ..config import Settings
from ..models import Post
from ..notify import TelegramNotifier
from ..rates import Rates
from ..storage import Storage
from ..view import CarView, car_view
from .writer import PostWriter, car_facts

log = logging.getLogger(__name__)

# Не повторяем машину в канале чаще, чем раз в столько дней
REPEAT_AFTER_DAYS = 30
DIGEST_SIZE = 5
# Из скольких свежих объявлений выбираем
POOL = 400


class PostNotFound(LookupError):
    pass


class PublishError(RuntimeError):
    pass


def pick_cars(storage: Storage, rates: Rates, *, exclude: set[str], limit: int) -> list[CarView]:
    """Свежие проходные машины с фото, ценой и годом; сначала — по одной на марку."""
    candidates: list[CarView] = []
    for listing in storage.search(passable_only=True, sort="new", limit=POOL):
        if f"{listing.source}/{listing.external_id}" in exclude:
            continue
        v = car_view(listing, rates)
        # «unknown» (не хватает данных о проходимости) в канал не берём — меньше неприятных сюрпризов
        if v.eligibility.verdict not in ("ok", "warn") or not v.photos or not v.price_rub or not listing.year:
            continue
        candidates.append(v)
    chosen: list[CarView] = []
    per_make: Counter[str] = Counter()
    for max_per_make in (1, limit):
        for v in candidates:
            if len(chosen) >= limit:
                return chosen
            make = v.make or v.title.split()[0]
            if v not in chosen and per_make[make] < max_per_make:
                chosen.append(v)
                per_make[make] += 1
    return chosen


class MarketingAgent:
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        rates: Rates,
        notifier: TelegramNotifier,
        writer: PostWriter | None = None,
    ):
        self.settings = settings
        self.storage = storage
        self.rates = rates
        self.notifier = notifier
        self.writer = writer or PostWriter(settings.anthropic_api_key, settings.marketing_model, settings.company_name)
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    # --- подготовка постов --------------------------------------------------------

    def link(self, v: CarView, campaign: str, today: date) -> str:
        utm = {"utm_source": "telegram", "utm_medium": "channel", "utm_campaign": campaign,
               "utm_content": today.isoformat()}
        return f"{self.settings.site_url}{v.path}?{urlencode(utm)}"

    def digest_due(self, now: datetime) -> bool:
        weekday = self.settings.marketing_digest_weekday
        if weekday is None or now.weekday() != weekday:
            return False
        last = self.storage.last_post_at("digest")
        return last is None or now - last > timedelta(days=6)

    async def run_once(self, now: datetime | None = None) -> list[Post]:
        """Готовит порцию постов. Возвращает созданные черновики (или опубликованные при автопубликации)."""
        async with self._lock:
            now = now or datetime.now(timezone.utc)
            today = now.date()
            exclude = self.storage.post_car_keys(now - timedelta(days=REPEAT_AFTER_DAYS))
            posts: list[Post] = []

            for v in pick_cars(self.storage, self.rates, exclude=exclude, limit=self.settings.marketing_posts_per_run):
                text, writer = await self.writer.car_post(car_facts(v, self.link(v, "car", today)))
                key = f"{v.listing.source}/{v.listing.external_id}"
                posts.append(self.storage.add_post(Post(kind="car", text=text, photo=v.photos[0], cars=[key], writer=writer)))
                exclude.add(key)

            if self.digest_due(now):
                cars = pick_cars(self.storage, self.rates, exclude=exclude, limit=DIGEST_SIZE)
                if len(cars) >= 3:
                    items = [car_facts(v, self.link(v, "digest", today)) for v in cars]
                    text, writer = await self.writer.digest_post(items, "Подборка недели: свежие машины из Кореи и Китая")
                    keys = [f"{v.listing.source}/{v.listing.external_id}" for v in cars]
                    posts.append(self.storage.add_post(Post(kind="digest", text=text, cars=keys, writer=writer)))

            if not posts:
                log.info("marketing: нет новых машин для постов")
                return posts
            if self.settings.marketing_autopublish and self.settings.marketing_channel_id:
                published = []
                for post in posts:
                    try:
                        published.append(await self.publish(post.id))
                    except PublishError as exc:
                        log.warning("marketing autopublish #%s failed: %s", post.id, exc)
                        published.append(self.storage.get_post(post.id))
                return published
            await self.notifier.send_manager(
                f"✍️ Агент-маркетолог подготовил постов для канала: {len(posts)}. "
                f"Проверьте и опубликуйте: {self.settings.site_url}/admin/marketing"
            )
            return posts

    # --- публикация -----------------------------------------------------------------

    async def publish(self, post_id: int) -> Post:
        post = self.storage.get_post(post_id)
        if post is None:
            raise PostNotFound(post_id)
        if post.status == "published":
            return post
        channel = self.settings.marketing_channel_id
        if not channel:
            raise PublishError("MARKETING_CHANNEL_ID не задан — некуда публиковать")
        try:
            message_id = await self.notifier.post_to_channel(channel, post.text, post.photo)
        except Exception as exc:  # noqa: BLE001 — любую ошибку Telegram/сети показываем в админке
            self.storage.save_post(post.model_copy(update={"status": "failed", "error": str(exc)}))
            raise PublishError(str(exc)) from exc
        return self.storage.save_post(post.model_copy(update={
            "status": "published", "message_id": message_id, "error": None,
            "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }))

    # --- фоновый запуск ------------------------------------------------------------------

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="marketing-agent")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def seconds_until_next_run(self, now: datetime) -> float:
        # Отсчёт от последнего поста: перезапуск сервиса не порождает лишнюю порцию (и расходы на API)
        last = self.storage.last_post_at()
        if last is None:
            return 0.0
        interval = timedelta(hours=self.settings.marketing_interval_hours)
        return max(0.0, (last + interval - now).total_seconds())

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.seconds_until_next_run(datetime.now(timezone.utc)))
            try:
                posts = await self.run_once()
                if not posts:
                    # новых машин нет — заглянем через час, а не через сутки
                    await asyncio.sleep(3600)
            except Exception:  # noqa: BLE001 — агент не должен ронять сервис
                log.exception("marketing run failed")
                await asyncio.sleep(3600)
