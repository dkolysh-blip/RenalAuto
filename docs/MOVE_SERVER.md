# Переезд на renal-auto.ru (REG.RU)

Итог: сайт открывается на `https://renal-auto.ru`, без `:8443`. Адрес `реналавто.рф` сам перебрасывает на него.
Заявки хранятся на сервере в России, как требует 152-ФЗ.

## Почему не «Хостинг Хост-0»

Хост-0 — виртуальный хостинг под PHP-сайты. Нашему сайту нужно то, чего там нет:
Docker, своя программа, которая работает круглосуточно и сама опрашивает площадки, база на диске.
Поэтому нужен **облачный сервер (VPS) в Рег.облаке** — в том же личном кабинете REG.RU.
Хост-0 после переезда можно не продлевать. Если на нём есть почта на `@renal-auto.ru` — сначала скажите, перенесём MX-записи.

Bulgogi остаётся: на нём работает VPN, а сборщик Encar с корейским IP шлёт объявления на новый сервер.

## 1. Сервер в Рег.облаке

Личный кабинет REG.RU → **Рег.облако** → **Облачные серверы** → **Создать сервер**:
- образ **Ubuntu 24.04**;
- 2 vCPU, 2 ГБ памяти, диск от 20 ГБ;
- регион — Москва или Санкт-Петербург.

После создания на почту придут IP-адрес и пароль `root`.

## 2. DNS домена

Сейчас у `renal-auto.ru` DNS-серверы хостинга (`ns1.hosting.reg.ru`). Чтобы управлять записями без хостинга:

1. **Домены** → `renal-auto.ru` → **DNS-серверы и управление зоной** → **Изменить** → «Бесплатные DNS-серверы REG.RU» (`ns1.reg.ru`, `ns2.reg.ru`).
2. Там же, в **Ресурсных записях**, — две записи `A`:
   - `@` → IP облачного сервера;
   - `www` → IP облачного сервера.
3. То же самое для `реналавто.рф`.

Записи обновляются от 15 минут до суток. Проверить: `dig +short renal-auto.ru` должен показать новый IP.

## 3. Установка на сервере

```sh
ssh root@<IP сервера>
curl -fsSL https://get.docker.com | sh
git clone https://github.com/dkolysh-blip/renalauto.git /root/RenalAuto   # репозиторий приватный — нужен токен или deploy key
cd /root/RenalAuto && git checkout claude/focused-heisenberg-drdrqe
```

## 4. Настройки и база (с Bulgogi)

```sh
# на Bulgogi
cd /root/RenalAuto && docker compose stop renalauto
tar czf /root/renalauto-data.tgz .env data
scp /root/renalauto-data.tgz root@<IP нового сервера>:/root/
# на новом сервере
cd /root/RenalAuto && tar xzf /root/renalauto-data.tgz
```

В `.env` на новом сервере поменять:

```
DOMAIN=renal-auto.ru
REDIRECT_DOMAINS=xn--80aagj5akljy.xn--p1ai, www.xn--80aagj5akljy.xn--p1ai
HTTPS_PORT=443
SITE_URL=https://renal-auto.ru
INGEST_TOKEN=<если пусто: openssl rand -hex 24>
```

`xn--80aagj5akljy.xn--p1ai` — это `реналавто.рф`, так домен записывается для серверов.

## 5. Запуск

Когда `dig +short renal-auto.ru` показывает новый IP:

```sh
cd /root/RenalAuto && docker compose up -d --build
docker compose logs caddy | grep -i certificate   # Caddy сам получит сертификаты Let's Encrypt
```

Проверка:
- `https://renal-auto.ru/port` — открывается лендинг;
- `https://renal-auto.ru/health` — отвечает;
- `https://реналавто.рф` — перебрасывает на `renal-auto.ru`.

## 6. Bulgogi: сайт выключить, сборщик Encar включить

```sh
cd /root/RenalAuto && docker compose down          # сайт и Caddy на Bulgogi больше не нужны
cp .env.collector.example .env.collector
# в .env.collector: COLLECTOR_SERVER=https://renal-auto.ru и INGEST_TOKEN — тот же, что на новом сервере
docker compose -f docker-compose.collector.yml up -d --build
```

Через несколько минут в `https://renal-auto.ru/health` появится сборщик (`COLLECTOR_NAME`).

## 7. После переезда

- Яндекс Метрика: в настройках счётчика 113699503 адрес сайта — `https://renal-auto.ru`.
- Директ: в `docs/direct-campaign.xlsx`, лист «Настройки», адрес лендинга — `https://renal-auto.ru/port`.
- `renal-auto.asia` можно тоже перевести на новый сервер и добавить в `REDIRECT_DOMAINS` — старые ссылки продолжат работать.
- Остальные площадки (KB Chachacha, Dongchedi, Che168) сервер опрашивает сам. Если какая-то не отвечает с российского IP — перенесём её в сборщик на Bulgogi, как Encar.
