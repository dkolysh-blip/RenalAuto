#!/usr/bin/env bash
# Разовая установка автодеплоя на сервере: bash deploy/install.sh
# После неё сервер сам раз в 2 минуты проверяет GitHub и выкладывает новые коммиты текущей ветки.
set -euo pipefail
dir=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
chmod +x "$dir/deploy/autodeploy.sh"

cat > /etc/systemd/system/renalauto-deploy.service <<UNIT
[Unit]
Description=RenalAuto: выкладка новых коммитов из GitHub
After=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=$dir
ExecStart=$dir/deploy/autodeploy.sh
UNIT

cat > /etc/systemd/system/renalauto-deploy.timer <<UNIT
[Unit]
Description=RenalAuto: проверка GitHub раз в 2 минуты

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now renalauto-deploy.timer
echo "Автодеплой включён для ветки $(git -C "$dir" rev-parse --abbrev-ref HEAD). Журнал: journalctl -u renalauto-deploy -n 50"
