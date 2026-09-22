"""All user-facing Uzbek (Latin) strings and message formatters."""

from __future__ import annotations

import re

from collections.abc import Sequence

from .models import SURVEY_BASIC, SURVEY_FULL, BotUser, FullProfile, Student, TestUser, Tutor
from .utils import clean_text, hesc

# ----------------------------------------------------------------- buttons

BTN_ADMIN_PANEL = "👑 Admin panel"
BTN_TUTOR_PANEL = "👨‍🏫 Tyutor panel"
BTN_REGISTER = "📝 Talaba sifatida ro'yxatdan o'tish"
BTN_CANCEL = "❌ Bekor qilish"
MAIN_MENU_BUTTONS: frozenset[str] = frozenset({BTN_ADMIN_PANEL, BTN_TUTOR_PANEL, BTN_REGISTER})
"""Reply-keyboard labels of the main menu; free-text FSM steps never accept them as data."""
BTN_BACK = "⬅️ Orqaga"
BTN_PREV = "⬅️"
BTN_NEXT = "➡️"
BTN_SEND_CONTACT = "📱 Raqamni yuborish"

BTN_RES_TTJ = "🏠 TTJ"
BTN_RES_KVARTIRA = "🏢 Kvartira"
BTN_RES_UY = "🏡 O'zimning uyimda"
BTN_RES_QARINDOSH = "🏘️ Qarindoshinikida"

BTN_ADMIN_TUTORS = "👨‍🏫 Tyutorlar ro'yxati"
BTN_ADMIN_ADD_TUTOR = "➕ Tyutor qo'shish"
BTN_ADMIN_USERS = "👥 Foydalanuvchilar"
BTN_ADMIN_TEST_USERS = "🧪 Test userlar"
BTN_ADD_TEST_USER = "➕ Test user qo'shish"
BTN_ADMIN_EXCEL_ALL = "📊 Excel (barcha tyutorlar)"
BTN_ADMIN_EXCEL_PICK = "📊 Excel (tyutor bo'yicha)"
BTN_ADMIN_EXCEL_FULL = "🗂 Excel: to'liq anketa (hamma)"
BTN_EXCEL_FULL = "🗂 To'liq anketa"
BTN_ADMIN_BROADCAST = "📢 Hammaga xabar"
BTN_BC_SKIP = "⏭ O'tkazib yuborish"
BTN_BC_CONTINUE = "➡️ Davom etish"
BTN_BC_ADD_TEXT = "➕ Matn"
BTN_BC_ADD_PHOTO = "➕ Rasm"
BTN_BC_ADD_VIDEO = "➕ Video"
BTN_BC_ADD_VOICE = "➕ Ovozli xabar"
BTN_BC_REMOVE_LAST = "🗑 Oxirgisini o'chirish"
BTN_BC_PREVIEW = "👁 Ko'rib chiqish (o'zimga yuborish)"
BTN_BC_SEND = "📤 Hammaga yuborish"
BTN_BC_CONFIRM = "✅ Ha, yuborish"
BTN_EDIT_NAME = "✏️ Ismini o'zgartirish"
BTN_EDIT_TG = "🆔 Telegram ID o'zgartirish"
BTN_DELETE = "🗑 O'chirish"
BTN_SAVE = "✅ Saqlash"
BTN_YES_DELETE = "✅ Ha, o'chirish"
BTN_NO = "❌ Yo'q"
BTN_EXCEL = "📊 Excel"

BTN_TUTOR_GROUPS = "👥 Guruhlarim"
BTN_TUTOR_ADD_GROUP = "➕ Guruh qo'shish"
BTN_TUTOR_EXCEL = "📊 Excel yuklab olish"
BTN_RENAME_GROUP = "✏️ Nomini o'zgartirish"
BTN_GROUP_STUDENTS = "🎓 Talabalar"  # tutor panel (pick a group first) and every group card
BTN_TUTOR_GROUP_LIST = "👥 Guruhlari"  # on the superadmin's tutor card
BTN_SEND_MESSAGE = "✉️ Xabar yuborish"
BTN_YES_SEND_MESSAGE = "✉️ Ha, xabar yuborish"
BTN_EXCEL_BY_GROUP = "👥 Guruh bo'yicha"
BTN_EXCEL_BY_RESIDENCE = "🏠 Turar joy bo'yicha"
BTN_EXCEL_ALL_GROUPS = "📦 Barcha guruhlar (bitta faylda)"
BTN_EXCEL_FULL_GROUP = "🗂 To'liq anketa: guruh bo'yicha"
BTN_EXCEL_FULL_ALL = "🗂 To'liq anketa: barcha guruhlar"
BTN_EXCEL_RES_UY = "🏡 O'z uyi"

BTN_CONFIRM = "✅ Tasdiqlash"
BTN_RESTART = "🔄 Qaytadan boshlash"

# student self-service; the edit menu packs two of these per row, so labels stay short
BTN_EDIT_MY_DATA = "✏️ Ma'lumotlarimni tahrirlash"
BTN_REREGISTER = "🔄 Qaytadan ro'yxatdan o'tish"
BTN_EDIT_DONE = "✅ Tayyor"
BTN_EDIT_TUTOR_GROUP = "👨‍🏫 Tyutor / guruh"
BTN_EDIT_FULL_NAME = "👤 F.I.SH"
BTN_EDIT_PHONE = "📞 Telefon"
BTN_EDIT_DIRECTION = "🎓 Yo'nalish"
BTN_EDIT_RESIDENCE = "🏠 Turar joy"
BTN_EDIT_ADDRESS = "📍 Manzil"
BTN_EDIT_FATHER_NAME = "👨 Otasi"
BTN_EDIT_FATHER_PHONE = "📞 Otasining tel"
BTN_EDIT_MOTHER_NAME = "👩 Onasi"
BTN_EDIT_MOTHER_PHONE = "📞 Onasining tel"

# --------------------------------------------------------------- residence

RESIDENCE_LABELS: dict[str, str] = {
    "ttj": "TTJ",
    "kvartira": "Kvartira",
    "uy": "O'z uyi",
    "qarindosh": "Qarindoshinikida",
}
RESIDENCE_BUTTONS: dict[str, str] = {
    BTN_RES_TTJ: "ttj",
    BTN_RES_KVARTIRA: "kvartira",
    BTN_RES_UY: "uy",
    BTN_RES_QARINDOSH: "qarindosh",
}
_RESIDENCE_ALIASES: dict[str, str] = {  # keys use the ASCII apostrophe; see ``_APOSTROPHES_RE``
    "ttj": "ttj",
    "kvartira": "kvartira",
    "uy": "uy",
    "o'zimning uyimda": "uy",
    "o'z uyi": "uy",
    "o'z uyim": "uy",
    "uyimda": "uy",
    "qarindosh": "qarindosh",
    "qarindoshnikida": "qarindosh",
    "qarindoshinikida": "qarindosh",
    "qarindoshimnikida": "qarindosh",
    "qarindoshlarnikida": "qarindosh",
    "qarindoshlarimnikida": "qarindosh",
}
# Phone keyboards type the Uzbek apostrophe as ’ (iOS/Android smart punctuation), ʻ (Gboard's Uzbek
# layout, the official letter), ‘, ʼ, ` or ´; all of them mean the same word.
_APOSTROPHES_RE = re.compile("[‘’ʻʼ`´]")


def residence_label(value: str) -> str:
    return RESIDENCE_LABELS.get(value, value)


def parse_residence(text: str | None) -> str | None:
    """Map a residence button label (or the same words typed) to a ``RESIDENCE_VALUES`` code."""
    if not text:
        return None
    value = text.strip()
    if value in RESIDENCE_BUTTONS:
        return RESIDENCE_BUTTONS[value]
    return _RESIDENCE_ALIASES.get(_APOSTROPHES_RE.sub("'", clean_text(value)).lower())


# ------------------------------------------------------------------ common

GREETING = "👋 Assalomu alaykum, <b>{name}</b>!\n\nKerakli bo'limni pastdagi tugmalar orqali tanlang."
CANCELLED = "❌ Bekor qilindi."
CANCELLED_STUDENT = "❌ Bekor qilindi. Boshlash uchun /start ni bosing."
UNKNOWN = "Tushunarsiz buyruq. /start ni bosing."
STALE_BUTTON = "Bu tugma eskirgan yoki sizga ruxsat yo'q."
NO_PERMISSION = "⛔️ Ruxsat yo'q."
ADMIN_ONLY = "⛔️ Bu buyruq faqat superadminlar uchun."
TUTOR_ONLY = "⛔️ Bu buyruq faqat tyutorlar uchun. Siz tyutor sifatida ro'yxatga olinmagansiz."
USE_BUTTONS = "Iltimos, xabardagi tugmalardan foydalaning yoki /cancel ni bosing."
NO_DATA = "📭 Ma'lumot topilmadi."

HELP_ADMIN = (
    "👑 <b>Superadmin buyruqlari</b>\n"
    "/admin — admin panel\n"
    "/tutors — tyutorlar ro'yxati\n"
    "/users — botni ishga tushirgan barcha foydalanuvchilar\n"
    "/test_users — qayta ro'yxatdan o'ta oladigan test userlar\n"
    "/add_tutor — tyutor qo'shish\n"
    "/edit_tutor — tyutorni tahrirlash\n"
    "/delete_tutor — tyutorni o'chirish\n"
    "/broadcast — hammaga xabar yuborish (matn + ixtiyoriy rasm, video, ovozli xabar)"
)
HELP_TUTOR = (
    "👨‍🏫 <b>Tyutor buyruqlari</b>\n"
    "/tutor — tyutor panel\n"
    "/groups — guruhlarim\n"
    "/students — talabalar: guruhni, keyin talabani tanlab xabar yuborish yoki o'chirish\n"
    "/add_group — guruh qo'shish\n"
    "/edit_group — guruh nomini o'zgartirish\n"
    "/delete_group — guruhni o'chirish\n"
    "/excel — Excel yuklab olish (📋 asosiy va 🗂 to'liq anketa)\n"
    "/phone — telefon raqamim (to'liq anketa ro'yxatida ko'rinadi)"
)
HELP_STUDENT = (
    "📝 <b>Talaba</b>\n"
    "/start — anketani tanlash: 📋 asosiy yoki 🗂 to'liq (ikkalasi alohida saqlanadi)\n"
    "/mydata — anketalarimni ko'rish va tahrirlash\n"
    "/cancel — joriy amalni bekor qilish\n"
    "/help — yordam"
)


def help_text(is_admin: bool, is_tutor: bool) -> str:
    parts = ["ℹ️ <b>Yordam</b>"]
    if is_admin:
        parts.append(HELP_ADMIN)
    if is_tutor:
        parts.append(HELP_TUTOR)
    parts.append(HELP_STUDENT)
    return "\n\n".join(parts)


# ------------------------------------------------------------------- admin

ADMIN_PANEL = "👑 <b>Admin panel</b>\n\nKerakli bo'limni tanlang:"
TUTOR_LIST_TITLE = "👨‍🏫 <b>Tyutorlar ro'yxati</b> ({n} ta). Tyutorni tanlang:"
TUTOR_LIST_EMPTY = "Hozircha tyutorlar yo'q. ➕ Tyutor qo'shish tugmasini bosing."
TUTOR_PICK_EDIT = "✏️ Tahrirlash uchun tyutorni tanlang:"
TUTOR_PICK_DELETE = "🗑 O'chirish uchun tyutorni tanlang:"
TUTOR_PICK_EXCEL = "📊 Qaysi tyutorning ma'lumotlarini yuklab olasiz?"
TUTOR_EDIT_FIELD = "✏️ <b>{name}</b> — nimani o'zgartirasiz?"
ASK_TUTOR_NAME = "✍️ Tyutorning F.I.SH ini kiriting:"
ASK_TUTOR_NEW_NAME = "✍️ Tyutor uchun yangi F.I.SH kiriting:"
TUTOR_NAME_INVALID = "❗️ Ism bo'sh bo'lmasligi va 100 belgidan oshmasligi kerak. Qaytadan kiriting:"
ASK_TUTOR_TG = (
    "🆔 Tyutorning Telegram ID sini kiriting (musbat butun son).\n\n"
    "ID ni bilish uchun tyutor @userinfobot ga /start yuborsin — bot uning ID sini ko'rsatadi.\n"
    "Yoki tyutorning istalgan xabarini shu yerga <i>forward</i> qiling."
)
ASK_TUTOR_NEW_TG = "🆔 Tyutor uchun yangi Telegram ID kiriting (yoki uning xabarini forward qiling):"
TUTOR_TG_INVALID = "❗️ Telegram ID musbat butun son bo'lishi kerak (masalan: 123456789). Qaytadan kiriting:"
TUTOR_TG_HIDDEN = (
    "❗️ Bu foydalanuvchi forward qilinganda profilini yashirgan. ID ni @userinfobot orqali aniqlab, qo'lda kiriting:"
)
TUTOR_TG_DUPLICATE = "❗️ Bu Telegram ID allaqachon boshqa tyutorga biriktirilgan. Boshqa ID kiriting:"
TUTOR_CONFIRM_ADD = (
    "Quyidagi tyutor qo'shiladi:\n\n👨‍🏫 F.I.SH: <b>{name}</b>\n🆔 Telegram ID: <code>{telegram_id}</code>"
)
TUTOR_SAVED = "✅ Tyutor qo'shildi."
TUTOR_UPDATED = "✅ Tyutor ma'lumotlari yangilandi."
TUTOR_NOT_FOUND = "❗️ Tyutor topilmadi (o'chirilgan bo'lishi mumkin)."
TUTOR_DELETE_CONFIRM = (
    "⚠️ <b>{name}</b> tyutorini o'chirmoqchimisiz?\n\n"
    "Bu tyutorga tegishli {groups} ta guruh va {students} ta talaba ham o'chiriladi."
)
TUTOR_DELETED = "🗑 Tyutor o'chirildi."
TUTOR_CARD = (
    "👨‍🏫 <b>Tyutor:</b> {name}\n"
    "🆔 Telegram ID: <code>{telegram_id}</code>\n"
    "👥 Guruhlar: {groups} ta\n"
    "🎓 Talabalar: {students} ta\n"
    "🕒 Qo'shilgan: {created_at}"
)
TUTOR_GROUP_LIST_TITLE = "👥 <b>{name}</b> — guruhlari ({n} ta). Guruhni tanlang:"
TUTOR_GROUP_LIST_EMPTY = "📭 <b>{name}</b> tyutorida hali guruhlar yo'q."


TEST_USERS_INTRO = (
    "🧪 <b>Test userlar</b>\n\n"
    "Bu ro'yxatdagilar ro'yxatdan o'tgandan keyin ham <b>qaytadan</b> ro'yxatdan o'ta oladi — "
    "jarayonni sinab ko'rish uchun. Qolgan hamma faqat ma'lumotlarini tahrirlay oladi."
)
TEST_USERS_EMPTY = TEST_USERS_INTRO + "\n\nRo'yxat hozircha bo'sh."
TEST_USERS_LIST = TEST_USERS_INTRO + "\n\nHozir ro'yxatda {n} ta:\n{lines}\n\nO'chirish uchun ustiga bosing."
ASK_TEST_USER_TG = (
    "🆔 Test userning Telegram ID sini kiriting (musbat butun son).\n\n"
    "Yoki uning istalgan xabarini shu yerga <i>forward</i> qiling — ID avtomatik o'qiladi."
)
TEST_USER_ADDED = "✅ Test userlar ro'yxatiga qo'shildi: <code>{telegram_id}</code>"
TEST_USER_DUPLICATE = "❗️ Bu ID allaqachon test userlar ro'yxatida."
TEST_USER_REMOVED = "🗑 Test userlar ro'yxatidan olib tashlandi."
REREGISTER_BLOCKED = "Siz allaqachon ro'yxatdan o'tgansiz. Ma'lumotlaringizni tahrirlash tugmasi orqali o'zgartiring."

USERS_EMPTY = "📭 Hozircha hech kim botni ishga tushirmagan."
USERS_TITLE = (
    "👥 <b>Bot foydalanuvchilari</b>\n\n"
    "Jami: <b>{total}</b> ta · ✅ ro'yxatdan o'tgan: <b>{registered}</b> ta · "
    "🕗 o'tmagan: <b>{pending}</b> ta\n"
    "📄 {page}/{pages}-sahifa"
)


def test_user_line(user: TestUser) -> str:
    username = f" @{hesc(user.username)}" if user.username else ""
    name = hesc(user.name) or "nomsiz"
    return f"• {name}{username} — <code>{user.telegram_id}</code>"


def test_users_text(users: Sequence[TestUser]) -> str:
    if not users:
        return TEST_USERS_EMPTY
    return TEST_USERS_LIST.format(n=len(users), lines="\n".join(test_user_line(u) for u in users))


def test_user_button_label(user: TestUser) -> str:
    return f"🗑 {user.name or user.telegram_id} ({user.telegram_id})"


def user_line(index: int, user: BotUser) -> str:
    """One row of /users: ``✅`` finished registering, ``🕗`` only pressed /start."""
    mark = "✅" if user.is_student else "🕗"
    username = f" @{hesc(user.username)}" if user.username else ""
    name = hesc(user.full_name) or "—"
    return f"{index}. {mark} {name}{username} — <code>{user.telegram_id}</code>"


def users_page(users: Sequence[BotUser], total: int, registered: int, page: int, pages: int, offset: int) -> str:
    """The /users message: counters, page number and the numbered slice (``offset`` is 0-based)."""
    head = USERS_TITLE.format(
        total=total, registered=registered, pending=total - registered, page=page + 1, pages=pages
    )
    lines = [user_line(offset + i, u) for i, u in enumerate(users, start=1)]
    return head + "\n\n" + "\n".join(lines)


def tutor_button_label(tutor: Tutor) -> str:
    return f"{tutor.name} (id: {tutor.telegram_id})"


def tutor_card(tutor: Tutor, groups: int, students: int) -> str:
    return TUTOR_CARD.format(
        name=hesc(tutor.name),
        telegram_id=tutor.telegram_id,
        groups=groups,
        students=students,
        created_at=hesc(tutor.created_at),
    )


# ------------------------------------------------------------------- tutor

TUTOR_PANEL = "👨‍🏫 <b>Tyutor panel</b> — {name}\n\nKerakli bo'limni tanlang:"
GROUP_LIST_TITLE = "👥 <b>Guruhlarim</b> ({n} ta). Guruhni tanlang:"
GROUP_LIST_EMPTY = "Hozircha guruhlar yo'q. ➕ Guruh qo'shish tugmasini bosing."
GROUP_PICK_EDIT = "✏️ Nomini o'zgartirish uchun guruhni tanlang:"
GROUP_PICK_DELETE = "🗑 O'chirish uchun guruhni tanlang:"
GROUP_PICK_EXCEL = "👥 Qaysi guruhni yuklab olasiz?"
ASK_GROUP_NAME = "✍️ Guruh nomini kiriting (masalan: DI-21-01):"
ASK_GROUP_NEW_NAME = "✍️ <b>{name}</b> guruhi uchun yangi nom kiriting:"
GROUP_NAME_INVALID = "❗️ Guruh nomi bo'sh bo'lmasligi va 64 belgidan oshmasligi kerak. Qaytadan kiriting:"
GROUP_DUPLICATE = "❗️ Sizda bu nomdagi guruh allaqachon mavjud. Boshqa nom kiriting:"
GROUP_SAVED = "✅ Guruh qo'shildi."
GROUP_RENAMED = "✅ Guruh nomi o'zgartirildi."
GROUP_NOT_FOUND = "❗️ Guruh topilmadi (o'chirilgan bo'lishi mumkin)."
GROUP_DELETE_CONFIRM = (
    "⚠️ <b>{name}</b> guruhini o'chirmoqchimisiz?\n\nGuruhdagi {count} ta talaba ma'lumoti ham o'chiriladi."
)
GROUP_DELETED = "🗑 Guruh o'chirildi."
GROUP_CARD = "👥 <b>Guruh:</b> {name}\n🎓 Talabalar: {count} ta\n🕒 Yaratilgan: {created_at}"
EXCEL_MENU = (
    "📊 Qaysi ma'lumotni yuklab olasiz?\n\n"
    "Yuqoridagi uchtasi — 📋 asosiy anketa, pastdagilar — 🗂 to'liq anketa."
)
EXCEL_FULL_PICK_GROUP = "🗂 To'liq anketa: qaysi guruhni yuklab olasiz?"
EXCEL_PICK_RESIDENCE = "🏠 Turar joy turini tanlang:"
EXCEL_CAPTION = "📊 {title}\n🎓 Talabalar: {count} ta"


def group_button_label(name: str, count: int) -> str:
    return f"{name} — {count} ta talaba"


# ------------------------------------------------------- broadcast (superadmin)

BC_PART_LABELS: dict[str, str] = {
    "text": "📝 Matn",
    "photo": "🖼 Rasm",
    "video": "🎬 Video",
    "voice": "🎤 Ovozli xabar",
}
BC_ASK_TEXT = (
    "📢 <b>Hammaga xabar</b>\n\n"
    "1/4 — ✍️ Xabar matnini kiriting (majburiy). Bu matn hamma foydalanuvchiga birinchi bo'lib boradi; "
    "Telegram'dagi formatlash (qalin, havola va h.k.) saqlanadi."
)
BC_TEXT_REQUIRED = "❗️ Avval matn kiriting — bu majburiy. Rasm, video va ovozli xabar keyingi qadamlarda so'raladi."
BC_ASK_PHOTO = (
    "2/4 — 🖼 Rasm qo'shasizmi? (ixtiyoriy)\n"
    "Rasm yuboring (bir nechta bo'lishi mumkin, izohi bilan ham) yoki ⏭ tugmasini bosing."
)
BC_ASK_VIDEO = "3/4 — 🎬 Video qo'shasizmi? (ixtiyoriy)\nVideo yuboring yoki ⏭ tugmasini bosing."
BC_ASK_VOICE = "4/4 — 🎤 Ovozli xabar qo'shasizmi? (ixtiyoriy)\nOvozli xabar yuboring yoki ⏭ tugmasini bosing."
BC_PART_ADDED = "✅ {label} qo'shildi (xabarda {n} ta qism). Yana yuborishingiz yoki davom etishingiz mumkin."
BC_UNSUPPORTED = "❗️ Faqat matn, rasm, video yoki ovozli xabar qo'shish mumkin."
BC_TOO_MANY_PARTS = "❗️ Bitta xabarda ko'pi bilan {max} ta qism bo'lishi mumkin. Keraksizini 🗑 bilan o'chiring."
BC_REVIEW_TITLE = "📢 <b>Xabar tayyor.</b> Tarkibi:"
BC_REVIEW_FOOTER = (
    "👥 Qabul qiluvchilar: <b>{n}</b> ta foydalanuvchi (botni ishga tushirgan hamma).\n\n"
    "➕ bilan qism qo'shing, 👁 bilan o'zingizga yuborib ko'ring, so'ng 📤 bosing."
)
BC_ASK_MORE = "➕ {label} yuboring:"
BC_PREVIEW_DONE = "👆 Xabar shu ko'rinishda boradi."
BC_PREVIEW_FAILED = "❗️ {label} nusxalanmadi — asl xabar o'chirilgan bo'lishi mumkin. Uni 🗑 bilan olib tashlang."
BC_NOTHING_TO_REMOVE = "Birinchi matn majburiy — uni o'chirib bo'lmaydi."
BC_CONFIRM = "⚠️ Xabar ({parts} ta qism) <b>{n}</b> ta foydalanuvchiga yuboriladi. Tasdiqlaysizmi?"
BC_NO_RECIPIENTS = "📭 Hozircha hech kim botni ishga tushirmagan — yuboradigan odam yo'q."
BC_STARTED = "📤 Yuborilmoqda… {done}/{total}"
BC_REPORT = (
    "✅ <b>Yuborish tugadi.</b>\n"
    "👥 Qabul qiluvchilar: {total}\n"
    "✅ Yetib bordi: {sent}\n"
    "🚫 Botni bloklagan: {blocked}\n"
    "⚠️ Xato: {failed}"
)
BC_CANCELLED = "❌ Xabar bekor qilindi, hech kimga yuborilmadi."
BC_STALE = "Bu tugma eskirgan — xabar tuzish tugagan yoki bekor qilingan."


def broadcast_part_line(index: int, kind: str, summary: str) -> str:
    label = BC_PART_LABELS.get(kind, kind)
    return f"{index}. {label} — «{hesc(summary)}»" if summary else f"{index}. {label}"


# ------------------------------------------------------- surveys (two questionnaires)

BTN_SURVEY_BASIC = "📋 Asosiy anketa"
BTN_SURVEY_FULL = "🗂 To'liq anketa"
SURVEY_LABELS: dict[str, str] = {SURVEY_BASIC: BTN_SURVEY_BASIC, SURVEY_FULL: BTN_SURVEY_FULL}
SURVEY_SHORT_LABELS: dict[str, str] = {SURVEY_BASIC: "Asosiy anketa", SURVEY_FULL: "To'liq anketa"}
SURVEY_ABOUT: dict[str, str] = {
    SURVEY_BASIC: "F.I.SH, telefon, yo'nalish, turar joy va ota-onangiz — 8 ta savol",
    SURVEY_FULL: "pasport, JShShR, yashash manzili, ish, oila va ijtimoiy holat — 22 ta savol",
}
SURVEY_PICK = (
    "📝 <b>Qaysi anketani to'ldirasiz?</b>\n\n"
    "{lines}\n\n"
    "Ikkalasi bir-biridan mustaqil: birini to'ldirib, ikkinchisini keyin ham to'ldirishingiz mumkin."
)
SURVEY_PICK_EDIT = "✏️ <b>Qaysi anketani ko'rasiz yoki o'zgartirasiz?</b>\n\n{lines}"
SURVEY_LINE_DONE = "✅ <b>{label}</b> — to'ldirilgan ({at})"
SURVEY_LINE_TODO = "🕗 <b>{label}</b> — to'ldirilmagan · {about}"
SURVEY_NOT_FILLED = "Siz <b>{label}</b> ni hali to'ldirmagansiz. Boshlaymiz 👇"
SURVEY_STALE = "Bu tugma eskirgan — /start ni bosing."


def survey_label(code: str) -> str:
    return SURVEY_LABELS.get(code, code)


def survey_lines(filled: dict[str, str | None]) -> str:
    """One status line per survey; ``filled`` maps a code to the date it was filled (or ``None``)."""
    lines = []
    for code, label in SURVEY_LABELS.items():
        at = filled.get(code)
        if at:
            lines.append(SURVEY_LINE_DONE.format(label=label, at=hesc(at)))
        else:
            lines.append(SURVEY_LINE_TODO.format(label=label, about=SURVEY_ABOUT[code]))
    return "\n".join(lines)


# --------------------------------------------------------- full survey: buttons

BTN_FULL_SKIP_PARENT = "⚠️ Ma'lumot yo'q"
BTN_CITIZEN_UZ = "🇺🇿 O'zbekiston"
BTN_CITIZEN_OTHER = "🌍 Boshqa davlat"
BTN_EMPLOYED_YES = "💼 Ishlayman"
BTN_EMPLOYED_NO = "🚫 Ishlamayman"
BTN_MARRIED_YES = "💍 Oila qurganman"
BTN_MARRIED_NO = "🙅 Oila qurmaganman"
BTN_SOCIAL_NONE = "🚫 Hech biri"
BTN_SOCIAL_DONE = "✅ Tayyor"
BTN_EDIT_FULL_DATA = "✏️ Anketani tahrirlash"

CITIZENSHIP_UZ = "O'zbekiston"
SOCIAL_LABELS: dict[str, str] = {
    "yoshlar_daftari": "Yoshlar daftari",
    "ijtimoiy_reestr": "Ijtimoiy himoya reestri",
    "kam_taminlangan": "Kam ta'minlangan",
    "nogiron": "Nogironligi bor",
    "yetim": "Yetim",
    "chin_yetim": "Chin yetim",
}
SOCIAL_NONE_LABEL = "Yo'q"
NO_DATA_VALUE = "—"  # what a deliberately skipped parent field holds


def social_labels(codes: Sequence[str]) -> str:
    names = [SOCIAL_LABELS[c] for c in codes if c in SOCIAL_LABELS]
    return ", ".join(names) if names else SOCIAL_NONE_LABEL


def course_label(course: int) -> str:
    return f"{course}-kurs"


# ------------------------------------------------------- full survey: questions

FULL_TOTAL_STEPS = 22
FULL_INTRO = (
    "🗂 <b>To'liq anketa</b>\n\n"
    "{n} ta savol. Javoblar tyutoringiz va universitet ro'yxatiga tushadi, shuning uchun "
    "ma'lumotlar <b>haqiqiy</b> bo'lishi shart: pasport va JShShR tekshiriladi, telefon raqami "
    "Telegram hisobingizdan olinadi.\n\n"
    "Istalgan paytda ⬅️ Orqaga bilan bir qadam qaytishingiz yoki ❌ Bekor qilish bilan to'xtatishingiz mumkin."
)
FULL_STEP_PREFIX = "📊 <b>{n}/{total}</b>"

FULL_ASK_PHONE = (
    "📞 Telefon raqamingiz.\n\n"
    "Pastdagi <b>📱 Raqamni yuborish</b> tugmasini bosing — raqam Telegram hisobingizdan olinadi "
    "(qo'lda kiritib bo'lmaydi)."
)
FULL_PHONE_BUTTON_ONLY = (
    "❗️ Raqamni faqat <b>📱 Raqamni yuborish</b> tugmasi orqali yuboring — qo'lda yozilgan raqam qabul qilinmaydi."
)
FULL_ASK_FULL_NAME = "👤 F.I.SH ingizni to'liq kiriting (pasportdagidek, masalan: Aliyev Vali G'aniyevich):"
FULL_ASK_DIRECTION = "🎓 Ta'lim yo'nalishingizni kiriting (masalan: Dasturiy injiniring):"
FULL_ASK_COURSE = "📚 Nechanchi kursda o'qiysiz?"
FULL_COURSE_INVALID = "❗️ Pastdagi tugmalardan kursni tanlang (1–6)."
FULL_ASK_BIRTH = "🎂 Tug'ilgan kun, oy, yilingiz (masalan: 05.03.2004):"
FULL_BIRTH_INVALID = (
    "❗️ Sana noto'g'ri. Namuna: <b>05.03.2004</b> (kun.oy.yil). "
    "Yosh {min} dan {max} gacha bo'lishi kerak."
)
FULL_ASK_PASSPORT = "🪪 Pasport seriya va raqami (masalan: AA1234567):"
FULL_PASSPORT_INVALID = "❗️ Pasport noto'g'ri. Namuna: <b>AA1234567</b> — 2 ta harf va 7 ta raqam."
FULL_ASK_PINFL = (
    "🔢 Pasportdagi JShShR (PNFL) — 14 xonali raqam.\n\n"
    "U pasportingizning pastki qismida yozilgan va tug'ilgan sanangizga mos bo'lishi kerak."
)
FULL_PINFL_INVALID = (
    "❗️ JShShR noto'g'ri: 14 ta raqam bo'lishi va tug'ilgan sanangizga ({birth}) mos kelishi kerak. "
    "Pasportdan ko'chirib yozing."
)
FULL_IDENTITY_TAKEN = (
    "❗️ Bu pasport yoki JShShR allaqachon boshqa foydalanuvchi tomonidan kiritilgan. "
    "O'z ma'lumotlaringizni kiriting yoki tyutoringizga murojaat qiling."
)
FULL_ASK_CITIZENSHIP = "🌐 Fuqaroligingiz?"
FULL_ASK_CITIZENSHIP_OTHER = "🌍 Qaysi davlat fuqarosisiz? Davlat nomini kiriting:"
FULL_ASK_REGION = "📍 Yashash viloyatingizni tanlang:"
FULL_REGION_INVALID = "❗️ Ro'yxatdagi viloyatlardan birini tanlang."
FULL_ASK_DISTRICT = "🏙 Shahar yoki tumaningiz (masalan: Chilonzor tumani):"
FULL_ASK_MFY = "🏘 MFY (mahalla) nomi:"
FULL_ASK_MFY_CONTACT = (
    "📞 MFY raqami — mahalla raisi yoki yoshlar yetakchisining telefon raqami (+998901234567):"
)
FULL_ASK_STREET = "🏠 Ko'cha va uy raqamingiz (masalan: Navoiy ko'chasi, 12-uy, 5-xonadon):"
FULL_ASK_EMPLOYED = "💼 Ish bilan bandmisiz?"
FULL_ASK_WORK_PLACE = "🏢 Ishlaydigan tashkilotingiz nomi:"
FULL_ASK_WORK_POSITION = "🧾 Lavozimingiz:"
FULL_ASK_WORK_ADDRESS = "📍 Tashkilot joylashgan joyi (viloyat, tuman, ko'cha):"
FULL_ASK_WORK_PHONE = "📞 Tashkilot telefon raqami (+998901234567 yoki +998712001122):"
FULL_ASK_MARRIED = "💍 Oila qurganmisiz?"
FULL_ASK_SPOUSE_NAME = "👤 Turmush o'rtog'ingizning F.I.SH:"
FULL_ASK_SPOUSE_WORK = "🏢 Turmush o'rtog'ingizning ish joyi (ishlamasa: ishlamaydi):"
FULL_ASK_SPOUSE_PHONE = "📞 Turmush o'rtog'ingizning telefon raqami:"
FULL_ASK_SOCIAL = (
    "🧾 Ijtimoiy holatingiz. Tegishlilarini belgilang (bir nechtasini tanlash mumkin), "
    "so'ng ✅ Tayyor ni bosing. Hech biri tegishli bo'lmasa — 🚫 Hech biri."
)
FULL_ASK_FATHER_NAME = "👨 Otangizning F.I.SH:"
FULL_ASK_FATHER_PHONE = "📞 Otangizning telefon raqami:"
FULL_ASK_FATHER_WORK = "🏢 Otangizning ish joyi (ishlamasa: ishlamaydi):"
FULL_ASK_MOTHER_NAME = "👩 Onangizning F.I.SH:"
FULL_ASK_MOTHER_PHONE = "📞 Onangizning telefon raqami:"
FULL_ASK_MOTHER_WORK = "🏢 Onangizning ish joyi (ishlamasa: uy bekasi):"
FULL_PARENT_SKIP_HINT = "Ma'lumot bo'lmasa (masalan, ota-ona vafot etgan bo'lsa) — ⚠️ Ma'lumot yo'q tugmasini bosing."
FULL_TEXT_INVALID = "❗️ Javob {min}–{max} belgidan iborat bo'lishi kerak. Qaytadan kiriting:"
FULL_USE_BUTTONS = "❗️ Pastdagi tugmalardan birini tanlang."
FULL_NOTHING_TO_GO_BACK = "Bu birinchi savol — ortga qaytadigan qadam yo'q."
FULL_PREVIEW_TITLE = "📋 To'liq anketa — ma'lumotlaringizni tekshiring"
FULL_SAVED = "✅ To'liq anketa saqlandi. Rahmat!"
FULL_RESTARTED = "🔄 To'liq anketani qaytadan boshlaymiz."
FULL_CARD_TITLE_NEW = "🆕 Talaba to'liq anketani to'ldirdi"
FULL_CARD_TITLE_UPDATE = "🔄 Talaba to'liq anketani yangiladi"
FULL_HOME_TITLE = "🗂 To'liq anketangiz"
FULL_EDIT_MENU = "✏️ To'liq anketada qaysi ma'lumotni o'zgartirasiz?"
FULL_GONE = (
    "❗️ To'liq anketangiz topilmadi — tyutoringiz sizni ro'yxatdan o'chirgan yoki guruhingiz "
    "o'chirilgan bo'lishi mumkin."
)

# tutor's own phone (a column of the full survey the student never fills in)
TUTOR_PHONE_MISSING = (
    "📞 <b>Telefon raqamingiz kiritilmagan.</b>\n\n"
    "To'liq anketa ro'yxatida har bir talabaning yonida tyutorning raqami turadi. "
    "Pastdagi tugma orqali raqamingizni yuboring."
)
BTN_TUTOR_PHONE = "📞 Telefon raqamim"
TUTOR_ASK_PHONE = "📞 Telefon raqamingizni yuboring (📱 tugma orqali yoki +998901234567 ko'rinishida):"
TUTOR_PHONE_SAVED = "✅ Telefon raqamingiz saqlandi: {phone}"
TUTOR_PHONE_CURRENT = "📞 Telefon raqamingiz: <b>{phone}</b>\n\nO'zgartirish uchun yangi raqamni yuboring:"


def full_student_card(title: str, profile: FullProfile) -> str:
    """The full survey as one card. Every user-supplied value is HTML-escaped."""
    telegram = f"@{hesc(profile.username)} " if profile.username else ""
    lines = [
        title,
        "",
        f"👨‍🏫 Tyutor: {hesc(profile.tutor_name)}" + (f" ({hesc(profile.tutor_phone)})" if profile.tutor_phone else ""),
        f"👥 Guruh: {hesc(profile.group_name)}",
        "",
        f"👤 F.I.SH: {hesc(profile.full_name)}",
        f"📞 Telefon: {hesc(profile.phone)}",
        f"🎓 Yo'nalish: {hesc(profile.direction)}",
        f"📚 Kurs: {course_label(profile.course)}",
        f"🪪 Pasport: {hesc(profile.passport)}",
        f"🔢 JShShR: {hesc(profile.pinfl)}",
        f"🎂 Tug'ilgan sana: {hesc(profile.birth_date)}",
        f"🌐 Fuqaroligi: {hesc(profile.citizenship)}",
        "",
        f"📍 Viloyat: {hesc(profile.region)}",
        f"🏙 Shahar/tuman: {hesc(profile.district)}",
        f"🏘 MFY: {hesc(profile.mfy)}",
        f"📞 MFY raqami: {hesc(profile.mfy_contact)}",
        f"🏠 Ko'cha, uy: {hesc(profile.street)}",
        "",
    ]
    if profile.employed:
        lines += [
            "💼 Ish bilan band: ha",
            f"🏢 Tashkilot: {hesc(profile.work_place)}",
            f"🧾 Lavozim: {hesc(profile.work_position)}",
            f"📍 Tashkilot joyi: {hesc(profile.work_address)}",
            f"📞 Tashkilot tel: {hesc(profile.work_phone)}",
        ]
    else:
        lines.append("💼 Ish bilan band: yo'q")
    if profile.married:
        lines += [
            "",
            "💍 Oila qurgan: ha",
            f"👤 Turmush o'rtog'i: {hesc(profile.spouse_name)}",
            f"🏢 Ish joyi: {hesc(profile.spouse_work)}",
            f"📞 Telefoni: {hesc(profile.spouse_phone)}",
        ]
    else:
        lines.append("💍 Oila qurgan: yo'q")
    lines += [
        "",
        f"🧾 Ijtimoiy holati: {hesc(social_labels(profile.social_codes))}",
        "",
        f"👨 Otasi: {hesc(profile.father_name)}",
        f"📞 Otasining tel: {hesc(profile.father_phone)}",
        f"🏢 Otasining ish joyi: {hesc(profile.father_work)}",
        f"👩 Onasi: {hesc(profile.mother_name)}",
        f"📞 Onasining tel: {hesc(profile.mother_phone)}",
        f"🏢 Onasining ish joyi: {hesc(profile.mother_work)}",
        "",
        f"🆔 Telegram: {telegram}(ID: {profile.telegram_id})",
    ]
    if profile.created_at:
        lines.append(f"🕒 To'ldirilgan: {hesc(profile.created_at)}")
    if profile.edited_at:
        lines.append(f"✏️ Yangilangan: {hesc(profile.edited_at)}")
    return "\n".join(lines)


# ------------------------------------------- student management (tutor / superadmin)

STUDENT_PICK_GROUP = "🎓 Qaysi guruh talabalarini ko'rasiz?"
STUDENT_PICK_SURVEY = "🎓 <b>{group}</b> guruhi{tutor}\n\nQaysi anketa bo'yicha ro'yxatni ochasiz?"
STUDENT_LIST_TITLE = "🎓 <b>{group}</b> guruhi talabalari ({n} ta){tutor}\n\nTalabani tanlang:"
STUDENT_LIST_EMPTY = "📭 <b>{group}</b> guruhida hali talabalar yo'q.{tutor}"
STUDENT_LIST_TUTOR_LINE = "\n👨‍🏫 Tyutor: {tutor}"  # ``{tutor}`` above: this line for a superadmin, "" for the tutor
STUDENT_CARD_TITLE = "🎓 Talaba ma'lumotlari"
STUDENT_NOT_FOUND = "❗️ Talaba topilmadi (o'chirilgan bo'lishi mumkin)."
STUDENT_DELETE_CONFIRM = (
    "⚠️ Talaba <b>{name}</b> ma'lumotlarini o'chirmoqchimisiz?\n\n"
    "👥 Guruh: {group}\n"
    "🗂 Anketa: {survey}\n\n"
    "Shu anketada kiritgan barcha ma'lumotlari bazadan o'chiriladi va keyingi Excel fayllarida "
    "ko'rinmaydi (ikkinchi anketasiga tegilmaydi). Talaba xohlasa /start orqali qaytadan to'ldira oladi."
)
STUDENT_DELETED_TOAST = "🗑 Talaba o'chirildi"
STUDENT_DELETED = "🗑 Talaba <b>{name}</b> o'chirildi."
STUDENT_DELETED_ASK_MESSAGE = STUDENT_DELETED + "\n\nTalabaga xabar yuborasizmi?"
STUDENT_DELETED_NO_MESSAGE = "🗑 Talaba <b>{name}</b> o'chirildi. Talabaga xabar yuborilmaydi."
STUDENT_DELETED_MESSAGE_SENT = "🗑 Talaba <b>{name}</b> o'chirildi, xabar yuborildi."
STUDENT_DELETED_MESSAGE_BLOCKED = (
    "🗑 Talaba <b>{name}</b> o'chirildi, lekin xabar yetib bormadi — talaba botni bloklagan bo'lishi mumkin."
)
STUDENT_DELETED_MESSAGE_FAILED = "🗑 Talaba <b>{name}</b> o'chirildi, lekin xabar yuborilmadi (Telegram xatosi)."
FAREWELL_STALE = "Bu so'rov eskirgan — talaba allaqachon o'chirilgan, xabarni endi shu yerdan yuborib bo'lmaydi."
STUDENT_MESSAGE_PROMPT_TOAST = "✍️ Xabar matnini kiriting"
ASK_STUDENT_MESSAGE = "✍️ <b>{name}</b> uchun xabar matnini kiriting:"
STUDENT_MESSAGE_INVALID = "❗️ Xabar matni bo'sh bo'lmasligi va {max} belgidan oshmasligi kerak. Qaytadan kiriting:"
STUDENT_MESSAGE_TEXT_ONLY = (
    "❗️ Faqat matn yuborish mumkin (rasm, fayl yoki ovozli xabar emas). "
    "Xabar matnini yozing yoki ❌ Bekor qilish tugmasini bosing."
)
STUDENT_MESSAGE_SENT = "✅ Xabar yuborildi: <b>{name}</b>"
STUDENT_MESSAGE_BLOCKED = "❗️ Xabar yetib bormadi — talaba botni bloklagan bo'lishi mumkin."
STUDENT_MESSAGE_FAILED = "❗️ Xabar yuborilmadi. Birozdan keyin qaytadan urinib ko'ring."
# what the student receives; ``text`` is the sender's own words, HTML-escaped
MESSAGE_TO_STUDENT = (
    "✉️ <b>Sizga xabar</b>\n{sender}{note}\n\n{text}\n\n<i>ℹ️ Bu xabarga shu yerda javob yozib bo'lmaydi.</i>"
)
MESSAGE_SENDER_TUTOR = "👨‍🏫 Kimdan: tyutor {name}"
MESSAGE_SENDER_ADMIN = "👑 Kimdan: administratsiya"
MESSAGE_REMOVED_LINE = "\nℹ️ Siz <b>{group}</b> guruhi ro'yxatidan o'chirildingiz."  # ``{note}`` above


# ------------------------------------------------------------ registration

REG_NO_TUTORS = "Hozircha tyutorlar qo'shilmagan. Keyinroq urinib ko'ring."
REG_CHOOSE_TUTOR = "👨‍🏫 Tyutoringizni tanlang:"
REG_CHOOSE_GROUP = "👥 Guruhingizni tanlang:"
REG_TUTOR_NO_GROUPS = "Bu tyutorda hali guruhlar yo'q. Boshqa tyutorni tanlang yoki keyinroq urinib ko'ring."
REG_TUTOR_NOT_FOUND = "Tanlangan tyutor topilmadi, qaytadan boshlang."
REG_GROUP_NOT_FOUND = "Tanlangan guruh topilmadi, qaytadan boshlang."
REG_ASK_PHONE = "📞 Telefon raqamingizni yuboring:"
REG_PHONE_INVALID = "❗️ Raqam noto'g'ri. Namuna: +998901234567 yoki pastdagi tugmani bosing."
REG_CONTACT_NOT_OWN = "❗️ Faqat o'zingizning raqamingizni yuboring."
REG_ASK_FULL_NAME = "👤 F.I.SH ingizni kiriting (masalan: Aliyev Vali G'aniyevich):"
REG_NAME_INVALID = "❗️ F.I.SH noto'g'ri: kamida ikki so'z, raqamlarsiz, 3–150 belgi. Namuna: Aliyev Vali G'aniyevich"
REG_ASK_DIRECTION = "🎓 Yo'nalishingizni kiriting (masalan: Dasturiy injiniring):"
REG_DIRECTION_INVALID = "❗️ Yo'nalish 2–150 belgidan iborat bo'lishi kerak. Qaytadan kiriting:"
REG_ASK_RESIDENCE = "🏠 Qayerda turasiz?"
REG_RESIDENCE_INVALID = (
    "❗️ Pastdagi tugmalardan birini tanlang: 🏠 TTJ, 🏢 Kvartira, 🏡 O'zimning uyimda yoki 🏘️ Qarindoshinikida."
)
REG_ASK_ADDRESS = "📍 To'liq manzilingizni kiriting (shahar/tuman, ko'cha, uy):"
REG_ADDRESS_INVALID = "❗️ Manzil 5–300 belgidan iborat bo'lishi kerak. Qaytadan kiriting:"
REG_ASK_FATHER_NAME = "👨 Otangizning F.I.SH ini kiriting:"
REG_ASK_FATHER_PHONE = "📞 Otangizning telefon raqamini kiriting (+998901234567):"
REG_ASK_MOTHER_NAME = "👩 Onangizning F.I.SH ini kiriting:"
REG_ASK_MOTHER_PHONE = "📞 Onangizning telefon raqamini kiriting (+998901234567):"
REG_PARENT_PHONE_INVALID = "❗️ Raqam noto'g'ri. Namuna: +998901234567"
REG_PREVIEW_TITLE = "📋 Ma'lumotlaringizni tekshiring"
REG_SAVED = "✅ Ma'lumotlaringiz saqlandi. Rahmat!"
REG_RESTARTED = "🔄 Qaytadan boshlaymiz."

CARD_TITLE_NEW = "🆕 Yangi talaba ro'yxatdan o'tdi"
CARD_TITLE_UPDATE = "🔄 Talaba ma'lumotlarini yangiladi"

# ---------------------------------------------------- student self-service

STUDENT_HOME_TITLE = "📋 Sizning ma'lumotlaringiz"
STUDENT_HOME_HINT = "Ma'lumotlaringizni istalgan vaqtda o'zgartirishingiz mumkin."
STUDENT_NOT_REGISTERED = "Sizning ro'yxatdagi ma'lumotlaringiz topilmadi. Ro'yxatdan o'tishni boshlaymiz 👇"
EDIT_MENU = "✏️ Qaysi ma'lumotni o'zgartirasiz?"
EDIT_SAVED = "✅ Saqlandi."
EDIT_DONE = "✅ Ma'lumotlaringiz yangilandi. Rahmat!"
EDIT_NOTHING_CHANGED = "Hech narsa o'zgartirilmadi."
EDIT_GONE = (
    "❗️ Ma'lumotlaringiz topilmadi — tyutoringiz sizni ro'yxatdan o'chirgan yoki guruhingiz o'chirilgan "
    "bo'lishi mumkin. Qaytadan ro'yxatdan o'tishni boshlaymiz 👇"
)
EDIT_ASK_TUTOR = "👨‍🏫 Yangi tyutoringizni tanlang:"
EDIT_ASK_GROUP = "👥 Yangi guruhingizni tanlang:"


def student_card(title: str, student: Student) -> str:
    """Format the student card (§9). All user-supplied values are HTML-escaped."""
    telegram = f"@{hesc(student.username)} " if student.username else ""
    lines = [
        title,
        "",
        f"👨‍🏫 Tyutor: {hesc(student.tutor_name)}",
        f"👥 Guruh: {hesc(student.group_name)}",
        "",
        f"👤 F.I.SH: {hesc(student.full_name)}",
        f"📞 Telefon: {hesc(student.phone)}",
        f"🎓 Yo'nalish: {hesc(student.direction)}",
        f"🏠 Turar joy: {hesc(residence_label(student.residence))}",
        f"📍 Manzil: {hesc(student.address)}",
        "",
        f"👨 Otasi: {hesc(student.father_name)}",
        f"📞 Otasining tel: {hesc(student.father_phone)}",
        f"👩 Onasi: {hesc(student.mother_name)}",
        f"📞 Onasining tel: {hesc(student.mother_phone)}",
        "",
        f"🆔 Telegram: {telegram}(ID: {student.telegram_id})",
    ]
    if student.created_at:
        lines.append(f"🕒 Ro'yxatdan o'tgan: {hesc(student.created_at)}")
    if student.edited_at:
        lines.append(f"✏️ Yangilangan: {hesc(student.edited_at)}")
    return "\n".join(lines)
