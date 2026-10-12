# BITU Tyutor Bot — ishlash qoidalari

## 1. Maxfiylik: repoga hech qachon tushmasligi kerak

Bu bot talabalarning **shaxsiy ma'lumotlarini** saqlaydi (F.I.SH, telefon, uy manzili,
ota-onasining ismi va raqami). Quyidagilar git repoga, commit xabariga, README/DEPLOY matniga
va issue/PR ga **hech qachon** tushmaydi:

| Nima | Qayerda bo'ladi |
|---|---|
| `BOT_TOKEN`, `SUPERADMIN_IDS` va boshqa haqiqiy qiymatlar | faqat serverdagi `.env` (chmod 600) |
| `data/`, `*.db`, `*.db-journal` — talabalar bazasi | faqat serverda |
| `*.xlsx` — eksport qilingan ro'yxatlar | faqat yuklab olgan odamda |
| Server paroli, tokenlar | hech qayerda saqlanmaydi — kerak bo'lsa foydalanuvchidan so'raladi |
| SSH deploy kalitining **maxfiy** qismi | faqat ishlab chiquvchi kompyuterida (`~/.ssh/bitutyutor_deploy`) — repoga, chatga, boshqa joyga ko'chirilmaydi |

`.env.example` da faqat **namunaviy** qiymatlar turadi. Server IP, foydalanuvchi nomi va kalit
fayli **yo'li** `DEPLOY.md` / shu faylda bo'lishi mumkin, **parol va kalitning o'zi — yo'q**.

Hammasi `.gitignore` da ro'yxatga olingan. Yangi turdagi maxfiy fayl paydo bo'lsa: avval
`.gitignore` ga qo'shing, keyin faylni yarating. Har `git add -A` dan keyin
`git status --short` bilan ro'yxatni ko'zdan kechiring — ortiqcha fayl bo'lmasin.

## 2. Commit va push

- Muallif va push — **doim `flipa0604 <haydarovhayotjon6@gmail.com>`** nomidan.
- Commit xabarida **AI atributsiyasi bo'lmasin**: `Co-Authored-By:`, `Claude-Session:`,
  `🤖 Generated with ...` kabi qatorlar qo'shilmaydi. Xuddi shu qoida PR tavsiflariga ham
  tegishli. Agar xato bilan qo'shilib ketsa: `git commit --amend` → `git push --force-with-lease`.
- Commit xabarlari o'zbekcha, nima va nega o'zgarganini yozadi.
- Repo: https://github.com/flipa0604/bitutyutor (ochiq).

## 3. Kod

- **Python 3.10+** — server 3.10.12 da ishlaydi, 3.11 ga xos imkoniyatlardan foydalanmang
  (`datetime.UTC`, `asyncio.TaskGroup`, `typing.Self`, `StrEnum`, `tomllib`).
- O'zgarishdan keyin `python -m pytest -q` to'liq yashil bo'lishi shart.
- Bitta aiosqlite ulanishi bo'lishgani uchun `bot/db.py` dagi **hamma** so'rov `_lock` ostida
  ketma-ket bajariladi; qulfni ushlab turgan joyda `*_unlocked` variantini chaqiring
  (`asyncio.Lock` reentrant emas).
- Foydalanuvchiga ko'rinadigan barcha matnlar `bot/texts.py` da, o'zbek (lotin) tilida.
- Deploy: `DEPLOY.md`. Serverda yangilash — `bash deploy/update.sh`.

## 4. Serverga kirish va deploy

Server: `flipa@172.31.202.203` (Ubuntu 22.04, Python 3.10.12), loyiha `~/apps/bitutyutor`,
systemd xizmati `bitutyutor`, baza `~/apps/bitutyutor/data/bot.db`.

**Kirish — doim SSH kalit bilan, parolsiz** (kalit shu kompyuterda: `C:\Users\user\.ssh\bitutyutor_deploy`,
ochiq qismi serverdagi `~/.ssh/authorized_keys` da, izohi `bitutyutor-deploy`):

```bash
ssh -i ~/.ssh/bitutyutor_deploy -o IdentitiesOnly=yes -o BatchMode=yes flipa@172.31.202.203 '<buyruq>'
```

- `sudo` faqat bitta buyruqqa parolsiz: `sudo systemctl restart bitutyutor`
  (`/etc/sudoers.d/bitutyutor-deploy`). Loglar sudo'siz o'qiladi: `journalctl -u bitutyutor`
  (`flipa` — `systemd-journal` guruhida). Boshqa `sudo` kerak bo'lsa — parol foydalanuvchidan so'raladi.
- Kalit ishlamasa (yo'qolgan / almashtirilgan): yangisini `ssh-keygen -t ed25519 -N "" -C bitutyutor-deploy
  -f ~/.ssh/bitutyutor_deploy` bilan yaratib, `DEPLOY.md` → "SSH kalit" bo'limidagi buyruqlarni
  foydalanuvchiga serverda bajartiring. Parol bilan kirish (PuTTY `plink`) — faqat zaxira yo'l.

**Deploy tartibi** — bitta SSH sessiyada, skript stdin orqali (`... 'bash -s' < skript.sh`), butun skript
`main() { ... }; main < /dev/null` ichida (biror buyruq qolgan skriptni stdin'dan "yeb" qo'ymasin):

1. Joriy ishga tushish jurnalida (`journalctl _SYSTEMD_INVOCATION_ID=$(systemctl show -p InvocationID
   --value bitutyutor)`) boshlangan-u tugamagan **hammaga xabar** (`broadcasts … parts to` /
   `Broadcast by … finished`) yoki **🔄 tekshiruv** (`checks … users for blocks` / `Check by … finished`)
   bo'lsa — **restart qilinmaydi**: ular bot jarayonining ichida ketadi.
2. Bazadan nusxa: `~/backups/bitutyutor-<sana-vaqt>.db` (Python `sqlite3` `backup()` + `integrity_check`).
3. `git pull --ff-only` → serverdagi venv'da `pip install pytest pytest-asyncio` va
   `python -m pytest -q -p no:cacheprovider` (Python 3.10) — testlar yiqilsa, restart **yo'q**.
4. `source deploy/update.sh` (restart) → `journalctl -u bitutyutor -n 12` — `Start polling` bor, xato yo'q.
