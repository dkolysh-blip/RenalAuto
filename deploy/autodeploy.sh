#!/usr/bin/env bash
# Автодеплой: если в GitHub появились новые коммиты в ветке, которая выложена на сервере, —
# забирает их, пересобирает сайт и проверяет, что он отвечает. Запускается таймером раз в 2 минуты
# (ставится один раз: bash deploy/install.sh). Журнал: journalctl -u renalauto-deploy
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

exec 9>.deploy.lock
flock -n 9 || exit 0  # предыдущая выкладка ещё идёт

branch=$(git rev-parse --abbrev-ref HEAD)
git fetch --quiet origin "$branch"
remote=$(git rev-parse "origin/$branch")
[ "$(cat .deployed 2>/dev/null || true)" = "$remote" ] && exit 0

# с чем сравнивать: последняя удачно выложенная версия; при первом запуске её нет — считаем, что изменилось всё
before=$(cat .deployed 2>/dev/null || true)
echo "deploy: $branch ${before:0:7} -> ${remote:0:7}"
git merge --quiet --ff-only "origin/$branch"

# Сборка идёт до замены контейнера: если она упала, старая версия сайта продолжает работать.
docker compose up -d --build

# Caddyfile подключён в контейнер файлом: новую версию прокси видит только после перезапуска.
# Перезапускаем, только если новый файл проходит проверку, — иначе сайт остаётся на старом.
if [ -z "$before" ] || ! git diff --quiet "$before" "$remote" -- Caddyfile; then
  if docker run --rm --env-file .env -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2 \
      caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    docker compose restart caddy
  else
    echo "deploy: Caddyfile не прошёл проверку — прокси оставлен на старой настройке" >&2
  fi
fi

for _ in $(seq 1 30); do
  if curl -fsS -m 5 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "$remote" > .deployed
    echo "deploy: ok ${remote:0:7}"
    exit 0
  fi
  sleep 2
done
echo "deploy: сайт не отвечает после выкладки ${remote:0:7} — смотрите docker compose logs renalauto" >&2
exit 1
