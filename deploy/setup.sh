#!/usr/bin/env bash
# Run on the server as root from the directory with the uploaded code.
set -euo pipefail
APP=/opt/sneakora-bot

apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync >/dev/null

id sneakora &>/dev/null || useradd --system --home "$APP" --shell /usr/sbin/nologin sneakora
mkdir -p "$APP"
rsync -a --delete --exclude venv --exclude .git --exclude data ./ "$APP"/
chmod 600 "$APP/.env"

[ -d "$APP/venv" ] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R sneakora:sneakora "$APP"

cp "$APP/deploy/sneakora-bot.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable sneakora-bot >/dev/null
systemctl restart sneakora-bot
systemctl --no-pager status sneakora-bot | head -5
