# Serverga joylash (deploy)

Bot Ubuntu serverda **systemd** xizmati sifatida ishlaydi: qayta ishga tushish avtomatik, loglar
`journalctl` da. Joriy o'rnatma:

| | |
|---|---|
| Server | `172.31.202.203` |
| Foydalanuvchi | `flipa` |
| Katalog | `/home/flipa/apps/bitutyutor` |
| Xizmat nomi | `bitutyutor` |
| Repozitoriy | https://github.com/flipa0604/bitutyutor |

## Birinchi marta o'rnatish

```bash
ssh flipa@172.31.202.203
git clone https://github.com/flipa0604/bitutyutor.git ~/apps/bitutyutor
cd ~/apps/bitutyutor
bash deploy/install.sh
```

`install.sh` quyidagilarni bajaradi (takroran ishlatsa ham xavfsiz):

1. `venv/` yaratadi va `requirements.txt` ni o'rnatadi;
2. `.env` bo'lmasa, `.env.example` dan nusxa oladi va `DB_PATH` ni absolyut yo'lga qo'yadi
   (mavjud `.env` ustidan **yozmaydi**);
3. `deploy/bitutyutor.service` shablonidan systemd unit yasab, `enable` qiladi.

## `.env` ni to'ldirish

```bash
nano ~/apps/bitutyutor/.env
```

```
BOT_TOKEN=<@BotFather bergan token>
SUPERADMIN_IDS=<Telegram ID lar, vergul bilan>
DB_PATH=/home/flipa/apps/bitutyutor/data/bot.db
```

Ikkalasi ham majburiy — bo'lmasa bot ishga tushmaydi va logda aniq xato yozadi.
Telegram ID ni [@userinfobot](https://t.me/userinfobot) dan olasiz.

`.env` `.gitignore` da — hech qachon GitHub'ga tushmaydi.

## Ishga tushirish va boshqarish

```bash
sudo systemctl start bitutyutor      # ishga tushirish
sudo systemctl restart bitutyutor    # qayta ishga tushirish (.env o'zgargach shart)
sudo systemctl stop bitutyutor       # to'xtatish
systemctl status bitutyutor          # holati
journalctl -u bitutyutor -f          # loglar (jonli)
journalctl -u bitutyutor -n 50       # oxirgi 50 qator
```

## Kodni yangilash

Lokalda `git push` qilgandan so'ng serverda:

```bash
cd ~/apps/bitutyutor && bash deploy/update.sh
```

`update.sh` — `git pull` → bog'liqliklarni tekshirish → `systemctl restart` → holatni ko'rsatish.

## SSH kalit (parolsiz deploy)

Deploy qiluvchi kompyuterda kalit: `~/.ssh/bitutyutor_deploy` (maxfiy qismi faqat o'sha kompyuterda
qoladi). Yangi kalit kerak bo'lsa:

```bash
ssh-keygen -t ed25519 -N "" -C bitutyutor-deploy -f ~/.ssh/bitutyutor_deploy
cat ~/.ssh/bitutyutor_deploy.pub       # shu qatorni serverga qo'yasiz
```

Serverda `flipa` bo'lib bir marta bajariladi (`sudo` parolni bir marta so'raydi):

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo '<ochiq kalit qatori>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
# faqat botni qayta ishga tushirish parolsiz (boshqa hech narsa emas); visudo avval tekshiradi
echo 'flipa ALL=(root) NOPASSWD: /usr/bin/systemctl restart bitutyutor' > /tmp/btd
sudo visudo -cf /tmp/btd && sudo install -m 440 -o root -g root /tmp/btd /etc/sudoers.d/bitutyutor-deploy; rm -f /tmp/btd
# loglarni sudo'siz o'qish
sudo usermod -aG systemd-journal flipa
```

Tekshirish (deploy qiluvchi kompyuterdan):

```bash
ssh -i ~/.ssh/bitutyutor_deploy -o IdentitiesOnly=yes flipa@172.31.202.203 'sudo -n -l /usr/bin/systemctl restart bitutyutor'
```

## Ma'lumotlar bazasi (backup)

Baza — bitta SQLite fayl: `~/apps/bitutyutor/data/bot.db`. `.gitignore` da, ya'ni `git pull`
uni tegmaydi. Nusxa olish:

```bash
cp ~/apps/bitutyutor/data/bot.db ~/bot-$(date +%F).db
```

## Muammolarni aniqlash

| Belgi | Sabab / yechim |
|---|---|
| `Configuration error: BOT_TOKEN is not set` | `.env` da token yo'q yoki bo'sh |
| `BOT_TOKEN is malformed` | Token noto'g'ri ko'chirilgan (ortiqcha bo'shliq/qator) |
| `SUPERADMIN_IDS is empty` | `.env` da `SUPERADMIN_IDS` to'ldirilmagan |
| Xizmat `activating (auto-restart)` da qotgan | `journalctl -u bitutyutor -n 50` — sabab logda |
| `TelegramConflictError` | Xuddi shu token bilan bot boshqa joyda (lokalda?) ishlab turibdi |
