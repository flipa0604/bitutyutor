#!/usr/bin/env bash
# GitHub'dan yangilanishni tortib olib, botni qayta ishga tushiradi.
#   cd ~/apps/bitutyutor && bash deploy/update.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="bitutyutor"

cd "$APP_DIR"
echo "==> git pull"
git pull --ff-only
echo "==> Bog'liqliklar tekshirilmoqda"
./venv/bin/python -m pip install --quiet -r requirements.txt
echo "==> Qayta ishga tushirilmoqda"
sudo systemctl restart "$SERVICE_NAME"
sleep 2
systemctl --no-pager --lines=0 status "$SERVICE_NAME"
