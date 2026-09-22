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
- 🗂 Excel: to'liq anketa (hamma) — to'liq anketa bo'yicha barcha tyutorlar; tyutor kartasida esa
  🗂 **To'liq anketa** tugmasi faqat o'sha tyutorning fayli
- `/broadcast` yoki 📢 **Hammaga xabar** — botni ishga tushirgan **barcha** foydalanuvchilarga (talabalar,
  tyutorlar, boshqa adminlar) bir martada xabar yuborish. Qadamlar: ✍️ matn (majburiy) → 🖼 rasm → 🎬 video →
  🎤 ovozli xabar (uchtasi ixtiyoriy, ⏭ bilan o'tkaziladi, har birida bir nechta yuborish mumkin, rasm/video
  izohi bilan). Oxirida ko'rib chiqish ekrani: ➕ Matn / Rasm / Video / Ovozli xabar bilan yana qism qo'shish
  (yoki shunchaki yuborish), 🗑 oxirgisini o'chirish, 👁 o'zingizga yuborib ko'rish, 📤 yuborish → tasdiq.
  Xabar Telegram'ning `copyMessage` orqali asl holida (formatlash, izohlar bilan, "forward" belgisi yo'q)
  qism-qism boradi; ko'pi bilan 10 ta qism. Yuborish tugagach hisobot: yetib bordi / botni bloklagan / xato.

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
  - 🗂 **To'liq anketa: guruh bo'yicha** / **barcha guruhlar** — to'liq anketa hisoboti (32 ustun)
- `/phone` — o'z telefon raqamini kiritish (to'liq anketa faylida talabalari yonida ko'rinadi)

Tyutor faqat **o'z** guruhlari va talabalarini ko'radi.

#### Talabalarni boshqarish (tyutor va superadmin)

Guruh → 🎓 Talabalar → **qaysi anketa** (asosiy / to'liq, har birida nechta talaba borligi ko'rinadi) →
talaba tanlangach uning kartasi va ikkita tugma chiqadi:

- ✉️ **Xabar yuborish** — matn kiritiladi va talabaga
  `✉️ Sizga xabar / 👨‍🏫 Kimdan: tyutor <ism>` sarlavhasi bilan boradi (superadmin yuborsa —
  `👑 Kimdan: administratsiya`; superadmin talabaning o'z tyutori bo'lsa, tyutor nomi bilan).
  Faqat matn, 3500 belgigacha. Talaba botni bloklagan bo'lsa, yuboruvchiga shu haqda aytiladi.
- 🗑 **O'chirish** — tasdiqdan so'ng talabaning **o'sha anketada** kiritgan barcha ma'lumotlari
  bazadan o'chiriladi (keyingi Excel fayllarida ham bo'lmaydi). So'ng bot "Talabaga xabar yuborasizmi?"
  deb so'raydi: ✉️ **Ha** — matn kiritiladi va talabaga qaysi guruh ro'yxatidan o'chirilgani haqidagi
  izoh bilan boradi; ❌ **Yo'q** — talabaga hech narsa bormaydi. Ikkala holda ham ma'lumotlar o'chirilgan
  bo'ladi. O'chirilgan talaba xohlasa `/start` orqali qaytadan ro'yxatdan o'ta oladi.

Tyutor faqat o'z talabalarini boshqara oladi; superadmin — hammanikini (tyutor kartasi → 👥 Guruhlari).

### Talaba (`/start`)

`/start` bosilganda avval **qaysi anketa** to'ldirilishi so'raladi. Ikkala anketa bir-biridan **mustaqil**:
biri uchun ikkinchisi **shart emas** — talaba to'g'ridan-to'g'ri to'liq anketani to'ldirsa ham bo'ladi,
faqat asosiysini to'ldirsa ham. Har biri alohida bazada saqlanadi, alohida tahrirlanadi, alohida
Excelga chiqadi va alohida o'chiriladi. Tyutorlar va guruhlar esa ikkalasi uchun **umumiy**.

Shuning uchun tyutorga ko'rinadigan barcha sanoqlar ham alohida: guruh tugmasida `📋 3 ta · 🗂 50 ta`,
guruh va tyutor kartasida ikkita qator, talabalar ro'yxatida esa avval qaysi anketa ekani tanlanadi.

#### 📋 Asosiy anketa (8 ta savol)

Bosqichlar: tyutor → guruh → telefon (kontakt yuborish yoki `+998XXXXXXXXX`) → F.I.SH →
yo'nalish → turar joy (TTJ / Kvartira / O'zimning uyimda / Qarindoshinikida; faqat TTJ bo'lsa manzil
so'ralmaydi) → manzil → otasining F.I.SH va telefoni → onasining F.I.SH va telefoni → tasdiqlash.

#### 🗂 To'liq anketa (22 ta savol)

Bosqichlar: tyutor → guruh → telefon → F.I.SH → ta'lim yo'nalishi → kurs → tug'ilgan sana → pasport →
JShShR → fuqarolik → viloyat → shahar/tuman → MFY → MFY raqami → ko'cha va uy → ish bilan bandligi
(ishlasa: tashkilot, lavozim, joylashuv, tel) → oila qurganligi (qurgan bo'lsa: turmush o'rtog'ining
F.I.SH, ish joyi, tel) → ijtimoiy holati → otasining va onasining F.I.SH, tel, ish joyi → tasdiqlash.

Har bir savolda pastda **⬅️ Orqaga** (bir qadam ortga) va **❌ Bekor qilish** tugmalari turadi; variantli
savollar (kurs, fuqarolik, viloyat, ish, oila) tugmalar bilan tanlanadi, ijtimoiy holat esa bir nechta
belgilanadigan ro'yxat. Ota-onasi haqida ma'lumot bo'lmasa — **⚠️ Ma'lumot yo'q** tugmasi.

**Ma'lumotni to'qib yozish qiyin bo'lishi uchun:**

- telefon raqami **faqat 📱 tugma** orqali olinadi — Telegram hisobidagi haqiqiy raqam (qo'lda kiritib
  bo'lmaydi, boshqa odamning kontakti ham qabul qilinmaydi);
- pasport `AA1234567` shaklida tekshiriladi (kirill harflari lotinga o'giriladi);
- **JShShR tug'ilgan sana bilan solishtiriladi**: 14 xonali, birinchi raqami asr va jinsni, 2–7-raqamlari
  tug'ilgan sanani bildiradi — tasodifiy raqam o'tmaydi;
- bitta **pasport yoki JShShR ikki marta** ishlatilmaydi (bazada unikal);
- tug'ilgan sana haqiqiy sana bo'lishi va yosh 15–70 oralig'ida bo'lishi kerak;
- kurs, viloyat va boshqa variantlar faqat ro'yxatdagi qiymatlardan olinadi.

Tyutorning telefon raqamini talaba kiritmaydi — uni **tyutorning o'zi** `/phone` yoki tyutor panelidagi
📞 tugma orqali kiritadi (raqam kiritilmaguncha panelda eslatma turadi) va u to'liq anketa faylida
har bir talabasining yonida chiqadi.

#### Ma'lumotlarni tahrirlash

`/start` yoki `/mydata` bosilganda ikkala anketaning holati ko'rinadi (✅ to'ldirilgan / 🕗 to'ldirilmagan).
To'ldirilganini tanlab kartani ko'rish va **istalgan maydonni** o'zgartirish mumkin: asosiy anketada —
F.I.SH, telefon, yo'nalish, turar joy, manzil, ota-ona, tyutor/guruh; to'liq anketada — yuqoridagi
22 savolning har biri (tug'ilgan sana o'zgartirilsa, JShShR qaytadan so'raladi; "ishlayman" ga
o'zgartirilsa, ish ma'lumotlari so'raladi va aksincha — tozalanadi).

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

### 📋 Asosiy anketa

Ustunlar: `№ | F.I.SH | Telefon | Yo'nalish | Tyutor | Guruh | Turar joy | Manzil | Otasining F.I.SH | Otasining tel |
Onasining F.I.SH | Onasining tel | Telegram username | Telegram ID | Ro'yxatdan o'tgan vaqt | Oxirgi tahrir`.

### 🗂 To'liq anketa

Ustunlar (tyutorlar bo'limi so'ragan tartibda): `№ | Tyutori F.I.Sh. | Tyutor tel. raqami | Talaba F.I.Sh. |
Talaba tel raqami | Talim yo'nalishi | Guruhi | Kursi | Pasport seriya raqami | Pasport JShShR (PNFL) |
Tug'ilgan kun oy yili | Fuqoroligi | Viloyati | Shahar (Tuman) | MFY | MFY raqami (MFY raisi, yoshlar yetakchisi) |
Ko'cha uy raqami | Ish bilan bandligi | Ishlaydigan tashkiloti nomi | Lavozimi | Ishlaydigan tashkiloti joylashgan joyi |
Ishlaydigan tashkilot tel raqami | Olila qurgan (Oila qurmagan) | Turmush o'rtog'ini F.I.Sh. |
Turmush o'rtog'ining ish joyi | Turmush o'rtog'ini tel raqami | Ijtimoiy holati | Otasini F.I.Sh. |
Otasini tel raqami | Otasini ish joyi | Onasini F.I.Sh. | Onasini tel raqami | Onasini ish joyi |
Telegram ID | To'ldirilgan vaqt | Oxirgi tahrir`.

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
