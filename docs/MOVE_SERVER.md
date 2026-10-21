# Переезд сайта на свой сервер в России и адрес без :8443

Зачем:
- сайт откроется на обычном `https://renal-auto.asia`, без `:8443`; порт 443 на Bulgogi занят нодой Marzban;
- заявки с сайта (имена и телефоны) по 152-ФЗ нужно хранить на сервере в России.

Bulgogi остаётся: на нём продолжает работать VPN, а сборщик Encar с корейским IP шлёт объявления на новый сервер.

## 1. Сервер

VPS в России: Ubuntu 24.04, 1–2 vCPU, 2 ГБ памяти, 20 ГБ диска (Timeweb Cloud, Selectel, REG.RU и т. п.).
За день до переезда уменьшите TTL записи `renal-auto.asia` в DNS до 300 секунд — переключение пройдёт быстрее.

## 2. Установка

```sh
curl -fsSL https://get.docker.com | sh
git clone https://github.com/dkolysh-blip/renalauto.git /root/RenalAuto   # репозиторий приватный — нужен токен или deploy key
cd /root/RenalAuto && git checkout claude/focused-heisenberg-drdrqe
```

## 3. Перенос настроек и базы (с Bulgogi)

```sh
# на Bulgogi
cd /root/RenalAuto && docker compose stop renalauto
tar czf /root/renalauto-data.tgz .env data
scp /root/renalauto-data.tgz root@<IP нового сервера>:/root/
# на новом сервере
cd /root/RenalAuto && tar xzf /root/renalauto-data.tgz
```

В `.env` на новом сервере:

```
HTTPS_PORT=443
SITE_URL=https://renal-auto.asia
INGEST_TOKEN=<если пусто: openssl rand -hex 24>
```

## 4. DNS и запуск

1. В DNS домена: записи `A` для `renal-auto.asia` и `www.renal-auto.asia` → IP нового сервера.
2. Когда домен начнёт открываться на новый IP (`dig +short renal-auto.asia`):
   ```sh
   cd /root/RenalAuto && docker compose up -d --build
   docker compose logs caddy | grep -i certificate   # Caddy сам получит сертификат Let's Encrypt
   ```
3. Проверка: `https://renal-auto.asia/port` открывается, `https://renal-auto.asia/health` отвечает.

## 5. Bulgogi: сайт выключить, сборщик Encar включить

```sh
cd /root/RenalAuto && docker compose down          # сайт и Caddy на Bulgogi больше не нужны
cp .env.collector.example .env.collector
# в .env.collector: COLLECTOR_SERVER=https://renal-auto.asia и INGEST_TOKEN — тот же, что на новом сервере
docker compose -f docker-compose.collector.yml up -d --build
```

Через несколько минут в `https://renal-auto.asia/health` появится сборщик (`COLLECTOR_NAME`).

## 6. После переезда

- Яндекс Метрика: в настройках счётчика 113699503 адрес сайта — `https://renal-auto.asia`.
- Директ: в `docs/direct-campaign.xlsx`, лист «Настройки», адрес лендинга — `https://renal-auto.asia/port`.
- Остальные площадки (KB Chachacha, Dongchedi, Che168) сервер опрашивает сам. Если какая-то не отвечает с российского IP — перенесём её в сборщик на Bulgogi, как Encar.
