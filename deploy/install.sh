#!/usr/bin/env bash
# BITU Tyutor Bot — serverga birinchi marta o'rnatish (Ubuntu + systemd).
#
#   git clone https://github.com/flipa0604/bitutyutor.git ~/apps/bitutyutor
#   cd ~/apps/bitutyutor && bash deploy/install.sh
#
# Skript takroran ishga tushirilsa ham xavfsiz: mavjud venv va .env ustidan yozilmaydi.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="bitutyutor"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
RUN_USER="$(id -un)"

cd "$APP_DIR"
echo "==> Loyiha: ${APP_DIR}  (foydalanuvchi: ${RUN_USER})"

# 1) Virtual muhit + bog'liqliklar
if [ ! -x venv/bin/python ]; then
  echo "==> venv yaratilmoqda"
  python3 -m venv venv
fi
./venv/bin/python -m pip install --quiet --upgrade pip
echo "==> Bog'liqliklar o'rnatilmoqda"
./venv/bin/python -m pip install --quiet -r requirements.txt

# 2) .env — mavjud bo'lsa tegilmaydi, tokenni foydalanuvchi o'zi kiritadi
if [ ! -f .env ]; then
  echo "==> .env yaratilmoqda (.env.example dan)"
  cp .env.example .env
  # DB ni absolyut yo'lga qo'yamiz: systemd boshqa katalogdan ishga tushsa ham topiladi
  sed -i "s|^DB_PATH=.*|DB_PATH=${APP_DIR}/data/bot.db|" .env
fi
chmod 600 .env
mkdir -p data

# 3) systemd xizmati
echo "==> systemd xizmati o'rnatilmoqda: ${SERVICE_NAME}"
sed -e "s|__APP_DIR__|${APP_DIR}|g" -e "s|__USER__|${RUN_USER}|g" \
    deploy/bitutyutor.service | sudo tee "$SERVICE_FILE" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" >/dev/null

echo
echo "==> O'rnatish tugadi."
echo "    1. .env ni to'ldiring:   nano ${APP_DIR}/.env"
echo "    2. Ishga tushiring:      sudo systemctl restart ${SERVICE_NAME}"
echo "    3. Loglarni ko'ring:     journalctl -u ${SERVICE_NAME} -f"
