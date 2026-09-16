# BITU Tyutor Bot

Talabalarni tyutor va guruh bo'yicha ro'yxatga oluvchi Telegram bot. Tyutorlar o'z guruhlarini boshqaradi va
talabalar ma'lumotlarini Excel (.xlsx) ko'rinishida yuklab oladi; superadminlar tyutorlarni boshqaradi.

## Rollar

| Rol | Qayerdan aniqlanadi | Imkoniyatlar |
|---|---|---|
| **Superadmin** | `.env` faylidagi `SUPERADMIN_IDS` | Tyutor qo'shish / tahrirlash / o'chirish, barcha tyutorlar bo'yicha Excel |
| **Tyutor** | Superadmin tomonidan botga qo'shiladi | O'z guruhlarini boshqarish, o'z talabalarini Excelga yuklash |
| **Talaba** | Boshqa barcha foydalanuvchilar | `/start` orqali ro'yxatdan o'tish |

Rollar **qo'shiluvchan**: bitta foydalanuvchi ham superadmin, ham tyutor bo'lishi mumkin — asosiy menyuda ikkala
tugma ham ko'rinadi. Talaba ro'yxatdan o'tganda tyutor va barcha superadminlarga xabar boradi (bir kishi ikki rolda
bo'lsa ham faqat **bitta** xabar oladi).

## O'rnatish

Talablar: Python 3.10+ (serverda 3.10.12 da sinalgan).

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux / macOS
pip install -r requirements.txt
```

## Sozlash (`.env`)

`.env.example` faylidan nusxa oling va qiymatlarni to'ldiring:

```bash
copy .env.example .env            # Windows
# cp .env.example .env            # Linux / macOS
```

```
BOT_TOKEN=123456789:AAExampleToken      # @BotFather bergan token
SUPERADMIN_IDS=111111111,222222222      # superadminlarning Telegram ID lari (vergul bilan)
DB_PATH=data/bot.db                     # ixtiyoriy, SQLite fayl yo'li
```

`BOT_TOKEN` bo'lmasa yoki `SUPERADMIN_IDS` bo'sh/noto'g'ri bo'lsa bot ishga tushmaydi va aniq xato chiqaradi.

### Telegram ID ni qanday bilish mumkin?

1. Telegramda [@userinfobot](https://t.me/userinfobot) ga kiring va `/start` yuboring — bot sizning `Id` ingizni
   ko'rsatadi.
2. Yoki superadmin tyutorni qo'shayotganda tyutorning istalgan xabarini botga *forward* qilsa, ID avtomatik
   o'qiladi (agar foydalanuvchi forward qilinganda profilini yashirmagan bo'lsa).

## Ishga tushirish

```bash
python main.py
```

Bot ishga tushganda `/start`, `/help`, `/cancel` buyruqlari hamma uchun, superadmin va tyutor chatlarida esa
qo'shimcha buyruqlar menyuga avtomatik qo'shiladi.

## Serverga joylash

Ubuntu serverda systemd xizmati sifatida ishlaydi — to'liq qo'llanma: [DEPLOY.md](DEPLOY.md).

```bash
git clone https://github.com/flipa0604/bitutyutor.git ~/apps/bitutyutor
cd ~/apps/bitutyutor && bash deploy/install.sh
nano .env                              # BOT_TOKEN va SUPERADMIN_IDS
sudo systemctl restart bitutyutor
```

## Imkoniyatlar

### Superadmin (`/admin` yoki 👑 Admin panel)

- `/tutors` — tyutorlar ro'yxati, har bir tyutor kartasi (guruhlar va talabalar soni); kartadagi
  👥 **Guruhlari** orqali istalgan tyutorning guruhiga, undan talabasiga kirib, unga xabar yuborish yoki
  uni o'chirish mumkin (pastdagi "Talabalarni boshqarish" bo'limiga qarang)
- `/add_tutor` — tyutor qo'shish (F.I.SH → Telegram ID → tasdiqlash)
- `/edit_tutor` — tyutor ismini yoki Telegram ID sini o'zgartirish
- `/delete_tutor` — tyutorni o'chirish (uning guruhlari va talabalari ham o'chiriladi, oldin tasdiq so'raladi)
- `/users` — botni ishga tushirgan **barcha** foydalanuvchilar: ✅ ro'yxatdan o'tganlar va 🕗 o'tmaganlar,
  har birida ism, username va Telegram ID; 20 tadan sahifalanadi
- `/test_users` — 🧪 test userlar ro'yxati: qo'shish (ID kiritib yoki xabarini forward qilib) va
  o'chirish. Faqat shu ro'yxatdagilar qayta ro'yxatdan o'ta oladi (pastga qarang)
- 📊 Excel (barcha tyutorlar) — bitta faylda `Barchasi` varag'i + har bir tyutor uchun alohida varaq
- 📊 Excel (tyutor bo'yicha) — tanlangan tyutorning to'liq fayli

### Tyutor (`/tutor` yoki 👨‍🏫 Tyutor panel)

- `/groups` — guruhlarim (har birida talabalar soni), guruh kartasi (🎓 Talabalar tugmasi bilan)
- `/students` — talabalar: guruhni, keyin talabani tanlab xabar yuborish yoki o'chirish
- `/add_group` — guruh qo'shish (bir tyutorda bir xil nom takrorlanmaydi)
- `/edit_group` — guruh nomini o'zgartirish
- `/delete_group` — guruhni o'chirish (talabalar ma'lumoti ham o'chadi, oldin tasdiq so'raladi)
- `/excel` — Excel yuklab olish:
  - 👥 **Guruh bo'yicha** — faqat tanlangan guruh (bitta varaq)
  - 🏠 **Turar joy bo'yicha** — TTJ / Kvartira / O'z uyi / Qarindoshinikida bo'yicha barcha guruhlardan
    (Guruh ustuni bilan)
  - 📦 **Barcha guruhlar** — `Barchasi` varag'i + har bir guruh uchun alohida varaq

Tyutor faqat **o'z** guruhlari va talabalarini ko'radi.

#### Talabalarni boshqarish (tyutor va superadmin)

Guruh → talaba tanlangach uning to'liq kartasi va ikkita tugma chiqadi:

- ✉️ **Xabar yuborish** — matn kiritiladi va talabaga
  `✉️ Sizga xabar / 👨‍🏫 Kimdan: tyutor <ism>` sarlavhasi bilan boradi (superadmin yuborsa —
  `👑 Kimdan: administratsiya`; superadmin talabaning o'z tyutori bo'lsa, tyutor nomi bilan).
  Faqat matn, 3500 belgigacha. Talaba botni bloklagan bo'lsa, yuboruvchiga shu haqda aytiladi.
- 🗑 **O'chirish** — tasdiqdan so'ng talabaning ro'yxatdan o'tishda kiritgan barcha ma'lumotlari
  bazadan o'chiriladi (keyingi Excel fayllarida ham bo'lmaydi). So'ng bot "Talabaga xabar yuborasizmi?"
  deb so'raydi: ✉️ **Ha** — matn kiritiladi va talabaga qaysi guruh ro'yxatidan o'chirilgani haqidagi
  izoh bilan boradi; ❌ **Yo'q** — talabaga hech narsa bormaydi. Ikkala holda ham ma'lumotlar o'chirilgan
  bo'ladi. O'chirilgan talaba xohlasa `/start` orqali qaytadan ro'yxatdan o'ta oladi.

Tyutor faqat o'z talabalarini boshqara oladi; superadmin — hammanikini (tyutor kartasi → 👥 Guruhlari).

### Talaba (`/start`)

Ro'yxatdan o'tish bosqichlari: tyutor → guruh → telefon (kontakt yuborish yoki `+998XXXXXXXXX`) → F.I.SH →
yo'nalish → turar joy (TTJ / Kvartira / O'zimning uyimda / Qarindoshinikida; faqat TTJ bo'lsa manzil
so'ralmaydi) → manzil → otasining F.I.SH va telefoni → onasining F.I.SH va telefoni → tasdiqlash.

#### Ma'lumotlarni tahrirlash

Ro'yxatdan o'tgan talaba `/start` yoki `/mydata` bosganda o'z kartasini ko'radi va **istalgan vaqtda**
ma'lumotlarini o'zgartira oladi:

- ✏️ **Ma'lumotlarimni tahrirlash** — kerakli maydonni tanlab, faqat o'shani qayta kiritadi:
  F.I.SH, telefon, yo'nalish, turar joy, manzil, ota-onasining ismi va raqami, hatto tyutor/guruh.
  Har bir o'zgarish darhol saqlanadi; ✅ **Tayyor** bosilganda tyutor va superadminlarga yangilangan
  karta boradi (bir necha maydon o'zgartirilsa ham **bitta** xabar).
Turar joy TTJ ga o'zgartirilsa manzil avtomatik `TTJ` bo'ladi va so'ralmaydi.

**Bir marta ro'yxatdan o'tgan talaba qayta ro'yxatdan o'ta olmaydi** — u faqat tahrirlay oladi.
Bu tasodifan eski ma'lumotni butunlay almashtirib yuborishdan saqlaydi.

#### 🧪 Test userlar

Jarayonni boshidan sinab ko'rish kerak bo'lsa, superadmin `/test_users` orqali Telegram ID larni
ro'yxatga qo'shadi (bir nechta bo'lishi mumkin). Shu ro'yxatdagi odam kartasida **ikkala** tugma
turadi: ✏️ tahrirlash va 🔄 **Qaytadan ro'yxatdan o'tish** — ya'ni to'liq jarayonni xohlagancha
takrorlay oladi. Ro'yxatdan chiqarilsa, tugma yo'qoladi.

Talaba qayta ro'yxatdan o'tsa, eski ma'lumotlari yangilanadi (tyutorga "ma'lumotlarini yangiladi" xabari boradi).
`/cancel` yoki ❌ Bekor qilish — istalgan bosqichda jarayonni to'xtatadi.

## Excel fayl tuzilishi

Ustunlar: `№ | F.I.SH | Telefon | Yo'nalish | Tyutor | Guruh | Turar joy | Manzil | Otasining F.I.SH | Otasining tel |
Onasining F.I.SH | Onasining tel | Telegram username | Telegram ID | Ro'yxatdan o'tgan vaqt | Oxirgi tahrir`.

`Oxirgi tahrir` — talaba ma'lumotlarini qachon oxirgi marta o'zgartirgani. Ro'yxatdan o'tgandan keyin
hech narsa o'zgartirilmagan bo'lsa, katak **bo'sh** turadi. Excel har safar bazadan yangi o'qiladi,
ya'ni yuklab olingan fayl doim eng so'nggi ma'lumotni ko'rsatadi.
Sarlavha qatori qalin va rangli, birinchi qator muzlatilgan, filtr yoqilgan. Telefon raqamlari matn sifatida saqlanadi.

## Loyiha tuzilishi

```
main.py                 # kirish nuqtasi (python main.py)
bot/config.py           # .env sozlamalari
bot/db.py               # SQLite (aiosqlite) ma'lumotlar bazasi
bot/models.py           # Tutor, Group, Student dataclass'lari
bot/texts.py            # barcha o'zbekcha matnlar
bot/keyboards.py        # klaviaturalar va callback ma'lumotlari
bot/states.py           # FSM holatlari
bot/filters.py          # IsSuperAdmin, IsTutor filtrlari
bot/utils.py            # telefon/ism tekshiruvi, HTML escape
bot/excel.py            # Excel fayllarini yasash
bot/commands.py         # bot buyruqlari menyusi
bot/handlers/           # common, admin, tutor, student handler'lari
tests/                  # pytest testlari
deploy/                 # systemd unit + install.sh / update.sh
```

## Testlar

```bash
pip install pytest pytest-asyncio
python -m pytest -q
```
