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
| Server paroli, SSH kaliti, tokenlar | hech qayerda saqlanmaydi — har safar so'raladi |

`.env.example` da faqat **namunaviy** qiymatlar turadi. Server IP va foydalanuvchi nomi
`DEPLOY.md` da bo'lishi mumkin, **parol — yo'q**.

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
