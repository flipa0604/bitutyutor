"""Handler smoke tests through the real Dispatcher and routers with a recording fake session."""

from __future__ import annotations

from io import BytesIO

from aiogram import Bot, Dispatcher
from aiogram.types import (
    InlineKeyboardMarkup,
    InputFile,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    User,
)
from openpyxl import load_workbook

from bot import texts
from bot.db import Database
from bot.excel import ALL_SHEET_NAME, build_all_tutors_workbook
from tests.conftest import SECOND_SUPERADMIN_ID, SUPERADMIN_ID
from tests.helpers import FakeSession, callback_update, contact_update, make_user, text_update

TUTOR_TG = 2001
OTHER_TUTOR_TG = 2002
STUDENT_TG = 3001
OTHER_TG = 3002


async def feed(dp: Dispatcher, bot: Bot, *updates: Update) -> None:
    for update in updates:
        await dp.feed_update(bot, update)


def reply_button_texts(markup: object) -> list[str]:
    if not isinstance(markup, ReplyKeyboardMarkup):
        return []
    return [b.text for row in markup.keyboard for b in row if isinstance(b, KeyboardButton)]


def inline_data(markup: object) -> set[str]:
    return (
        {b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data}
        if isinstance(markup, InlineKeyboardMarkup)
        else set()
    )


async def register_and_open_editor(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database, user: User, tutor_id: int, group_id: int
) -> None:
    """Register ``user`` (TTJ) and leave them sitting in the edit menu with a cleared session."""
    await register_ttj(dp, bot, session, user, tutor_id, group_id)
    session.clear()
    await feed(dp, bot, text_update(user, "/mydata"), callback_update(user, "edt:open:"))


async def register_ttj(
    dp: Dispatcher,
    bot: Bot,
    session: FakeSession,
    user: User,
    tutor_id: int,
    group_id: int,
    start_text: str = "/start",
    *,
    already_registered: bool = False,
) -> None:
    """Drive a complete TTJ registration for ``user`` up to and including confirmation.

    Plain students start with ``/start``; role users must press the register button instead. A
    student who already has a saved row sees their own card first and reopens the flow with the
    "register again" button.
    """
    await feed(dp, bot, text_update(user, start_text))
    if already_registered:
        await feed(dp, bot, callback_update(user, "edt:again:"))
    await feed(
        dp,
        bot,
        callback_update(user, f"reg:tutor:{tutor_id}"),
        callback_update(user, f"reg:group:{group_id}"),
        text_update(user, "+998901234567"),
        text_update(user, "Aliyev Vali G'aniyevich"),
        text_update(user, "Dasturiy injiniring"),
        text_update(user, texts.BTN_RES_TTJ),
        text_update(user, "Aliyev G'ani"),
        text_update(user, "+998901111111"),
        text_update(user, "Aliyeva Zulfiya"),
        text_update(user, "+998902222222"),
    )
    assert texts.REG_PREVIEW_TITLE in session.last_text(user.id)
    await feed(dp, bot, callback_update(user, "reg:confirm:0"))


async def test_registration_ttj_path_and_deduplicated_notifications(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    # tutor is ALSO a superadmin -> must receive exactly one notification
    tutor = await db.add_tutor("Karimov Aziz", SUPERADMIN_ID)
    group = await db.add_group(tutor.id, "DI-21")
    student = make_user(STUDENT_TG, username="vali")

    await feed(dp, bot, text_update(student, "/start"))
    assert session.last_text(STUDENT_TG) == texts.REG_CHOOSE_TUTOR

    await register_ttj(dp, bot, session, student, tutor.id, group.id)

    row = await db.get_student_by_telegram_id(STUDENT_TG)
    assert row is not None
    assert row.residence == "ttj" and row.address == "TTJ"
    assert row.full_name == "Aliyev Vali G'aniyevich" and row.phone == "+998901234567"
    assert row.group_id == group.id and row.tutor_id == tutor.id

    # confirmation to the student, keyboard removed (plain student has no roles)
    saved = [m for m in session.of("SendMessage") if m.chat_id == STUDENT_TG and m.text == texts.REG_SAVED]
    assert len(saved) == 1 and isinstance(saved[0].reply_markup, ReplyKeyboardRemove)

    # notifications: tutor(=superadmin 1001) once, second superadmin once, nobody else
    cards = [m for m in session.of("SendMessage") if m.text and m.text.startswith(texts.CARD_TITLE_NEW)]
    assert sorted(m.chat_id for m in cards) == [SUPERADMIN_ID, SECOND_SUPERADMIN_ID]
    assert "@vali" in cards[0].text and "Aliyev Vali G'aniyevich" in cards[0].text
    assert "🏠 Turar joy: TTJ" in cards[0].text

    # every callback was answered
    assert len(session.of("AnswerCallbackQuery")) == 3

    # registering again is an update
    session.clear()
    await register_ttj(dp, bot, session, student, tutor.id, group.id, already_registered=True)
    updates = [m for m in session.of("SendMessage") if m.text and m.text.startswith(texts.CARD_TITLE_UPDATE)]
    assert sorted(m.chat_id for m in updates) == [SUPERADMIN_ID, SECOND_SUPERADMIN_ID]
    assert len(await db.list_students()) == 1


async def test_registration_kvartira_asks_address_and_escapes_html(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Tutor One", TUTOR_TG)
    group = await db.add_group(tutor.id, "AI-22")
    student = make_user(STUDENT_TG)

    await feed(
        dp,
        bot,
        text_update(student, "/start"),
        callback_update(student, f"reg:tutor:{tutor.id}"),
        callback_update(student, f"reg:group:{group.id}"),
        text_update(student, "+998901234567"),
        text_update(student, "<b>Aliyev</b> Vali"),
        text_update(student, "Dasturiy injiniring"),
        text_update(student, texts.BTN_RES_KVARTIRA),
    )
    assert session.last_text(STUDENT_TG) == texts.REG_ASK_ADDRESS
    await feed(dp, bot, text_update(student, "Tosh"))  # too short
    assert session.last_text(STUDENT_TG) == texts.REG_ADDRESS_INVALID
    await feed(
        dp,
        bot,
        text_update(student, "Toshkent, Chilonzor 5, 12-uy"),
        text_update(student, "Aliyev G'ani"),
        text_update(student, "+998901111111"),
        text_update(student, "Aliyeva Zulfiya"),
        text_update(student, "+998902222222"),
    )
    preview = session.last_text(STUDENT_TG)
    assert "&lt;b&gt;Aliyev&lt;/b&gt; Vali" in preview and "<b>Aliyev</b>" not in preview
    await feed(dp, bot, callback_update(student, "reg:confirm:0"))

    row = await db.get_student_by_telegram_id(STUDENT_TG)
    assert row is not None and row.residence == "kvartira" and row.address == "Toshkent, Chilonzor 5, 12-uy"
    cards = [m for m in session.of("SendMessage") if m.text and m.text.startswith(texts.CARD_TITLE_NEW)]
    assert sorted(m.chat_id for m in cards) == [SUPERADMIN_ID, SECOND_SUPERADMIN_ID, TUTOR_TG]


async def test_phone_validation_and_contact_ownership(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Tutor One", TUTOR_TG)
    group = await db.add_group(tutor.id, "AI-22")
    student = make_user(STUDENT_TG)
    await feed(
        dp,
        bot,
        text_update(student, "/start"),
        callback_update(student, f"reg:tutor:{tutor.id}"),
        callback_update(student, f"reg:group:{group.id}"),
    )
    assert session.last_text(STUDENT_TG) == texts.REG_ASK_PHONE

    await feed(dp, bot, text_update(student, "998901234567"))
    assert session.last_text(STUDENT_TG) == texts.REG_PHONE_INVALID
    await feed(dp, bot, text_update(student, "+998 90 123 45 67"))
    assert session.last_text(STUDENT_TG) == texts.REG_PHONE_INVALID
    await feed(dp, bot, contact_update(student, "998901234567", OTHER_TG))
    assert session.last_text(STUDENT_TG) == texts.REG_CONTACT_NOT_OWN
    await feed(dp, bot, contact_update(student, "+49123456789", STUDENT_TG))
    assert session.last_text(STUDENT_TG) == texts.REG_PHONE_INVALID

    await feed(dp, bot, contact_update(student, "998901234567", STUDENT_TG))
    assert session.last_text(STUDENT_TG) == texts.REG_ASK_FULL_NAME
    data = await dp.fsm.get_context(bot, STUDENT_TG, STUDENT_TG).get_data()
    assert data["phone"] == "+998901234567"


async def test_cancel_and_unknown_input(dp: Dispatcher, bot: Bot, session: FakeSession, db: Database) -> None:
    tutor = await db.add_tutor("Tutor One", TUTOR_TG)
    await db.add_group(tutor.id, "AI-22")
    student = make_user(STUDENT_TG)
    await feed(dp, bot, text_update(student, "/start"), callback_update(student, f"reg:tutor:{tutor.id}"))
    await feed(dp, bot, text_update(student, texts.BTN_CANCEL))
    assert session.last_text(STUDENT_TG) == texts.CANCELLED_STUDENT
    assert await dp.fsm.get_context(bot, STUDENT_TG, STUDENT_TG).get_state() is None

    await feed(dp, bot, text_update(student, "salom"))
    assert session.last_text(STUDENT_TG) == texts.UNKNOWN
    await feed(dp, bot, text_update(student, "/tutor"))
    assert session.last_text(STUDENT_TG) == texts.TUTOR_ONLY
    await feed(dp, bot, text_update(student, "/admin"))
    assert session.last_text(STUDENT_TG) == texts.ADMIN_ONLY


async def test_roles_are_additive_in_main_menu(dp: Dispatcher, bot: Bot, session: FakeSession, db: Database) -> None:
    admin = make_user(SUPERADMIN_ID)
    await feed(dp, bot, text_update(admin, "/start"))
    greeting = session.of("SendMessage")[-1]
    assert reply_button_texts(greeting.reply_markup) == [texts.BTN_ADMIN_PANEL, texts.BTN_REGISTER]

    await db.add_tutor("Admin Tutor", SUPERADMIN_ID)
    await feed(dp, bot, text_update(admin, "/start"))
    greeting = session.of("SendMessage")[-1]
    assert reply_button_texts(greeting.reply_markup) == [
        texts.BTN_ADMIN_PANEL,
        texts.BTN_TUTOR_PANEL,
        texts.BTN_REGISTER,
    ]

    await feed(dp, bot, text_update(admin, texts.BTN_TUTOR_PANEL))
    assert "Tyutor panel" in session.last_text(SUPERADMIN_ID)
    await feed(dp, bot, text_update(admin, texts.BTN_ADMIN_PANEL))
    assert "Admin panel" in session.last_text(SUPERADMIN_ID)


async def test_superadmin_adds_tutor_via_command(dp: Dispatcher, bot: Bot, session: FakeSession, db: Database) -> None:
    admin = make_user(SUPERADMIN_ID)
    await feed(dp, bot, text_update(admin, "/add_tutor"))
    assert session.last_text(SUPERADMIN_ID) == texts.ASK_TUTOR_NAME
    await feed(dp, bot, text_update(admin, "   "))
    assert session.last_text(SUPERADMIN_ID) == texts.TUTOR_NAME_INVALID
    await feed(dp, bot, text_update(admin, "Karimov Aziz"))
    assert session.last_text(SUPERADMIN_ID) == texts.ASK_TUTOR_TG
    await feed(dp, bot, text_update(admin, "abc"))
    assert session.last_text(SUPERADMIN_ID) == texts.TUTOR_TG_INVALID
    await feed(dp, bot, text_update(admin, str(TUTOR_TG)))
    assert "Karimov Aziz" in session.last_text(SUPERADMIN_ID)
    await feed(dp, bot, callback_update(admin, "adm:save:0"))

    tutor = await db.get_tutor_by_telegram_id(TUTOR_TG)
    assert tutor is not None and tutor.name == "Karimov Aziz"
    assert texts.TUTOR_SAVED in session.sent_texts(SUPERADMIN_ID)
    # command menu refreshed for the new tutor's chat
    assert any(getattr(m.scope, "chat_id", None) == TUTOR_TG for m in session.of("SetMyCommands"))

    # duplicate telegram id is rejected while adding another tutor
    await feed(
        dp,
        bot,
        text_update(admin, "/add_tutor"),
        text_update(admin, "Boshqa Tyutor"),
        text_update(admin, str(TUTOR_TG)),
    )
    assert session.last_text(SUPERADMIN_ID) == texts.TUTOR_TG_DUPLICATE

    # non-admin cannot start the flow
    stranger = make_user(OTHER_TG)
    await feed(dp, bot, text_update(stranger, "/add_tutor"))
    assert session.last_text(OTHER_TG) == texts.ADMIN_ONLY


async def test_tutor_group_flow_and_excel_export(dp: Dispatcher, bot: Bot, session: FakeSession, db: Database) -> None:
    tutor_user = make_user(TUTOR_TG)
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)

    await feed(dp, bot, text_update(tutor_user, "/add_group"))
    assert session.last_text(TUTOR_TG) == texts.ASK_GROUP_NAME
    await feed(dp, bot, text_update(tutor_user, "DI-21"))
    groups = await db.list_groups(tutor.id)
    assert [g.name for g in groups] == ["DI-21"]
    assert texts.GROUP_SAVED in session.sent_texts(TUTOR_TG)

    await feed(dp, bot, text_update(tutor_user, "/add_group"), text_update(tutor_user, "DI-21"))
    assert session.last_text(TUTOR_TG) == texts.GROUP_DUPLICATE
    await feed(dp, bot, text_update(tutor_user, "/cancel"))

    group = groups[0]
    # empty group -> "no data", no document
    await feed(dp, bot, callback_update(tutor_user, f"tut:excel_group:{group.id}:"))
    assert session.last_text(TUTOR_TG) == texts.NO_DATA
    assert not session.of("SendDocument")

    student = make_user(STUDENT_TG)
    await register_ttj(dp, bot, session, student, tutor.id, group.id)
    session.clear()

    await feed(dp, bot, callback_update(tutor_user, f"tut:excel_group:{group.id}:"))
    docs = session.of("SendDocument")
    assert len(docs) == 1 and docs[0].chat_id == TUTOR_TG
    assert isinstance(docs[0].document, InputFile)
    assert docs[0].document.filename.endswith(".xlsx") and "Karimov_Aziz" in docs[0].document.filename

    await feed(dp, bot, callback_update(tutor_user, "tut:excel_res_pick:0:ttj"))
    assert len(session.of("SendDocument")) == 2
    await feed(dp, bot, callback_update(tutor_user, "tut:excel_res_pick:0:uy"))
    assert len(session.of("SendDocument")) == 2 and session.last_text(TUTOR_TG) == texts.NO_DATA
    await feed(dp, bot, callback_update(tutor_user, "tut:excel_all:0:"))
    assert len(session.of("SendDocument")) == 3

    # superadmin export of all tutors
    admin = make_user(SUPERADMIN_ID)
    await feed(dp, bot, callback_update(admin, "adm:excel_all:0"))
    assert len(session.of("SendDocument")) == 4
    assert session.of("SendDocument")[-1].document.filename.startswith("barcha_tyutorlar_")


async def test_tutor_cannot_touch_other_tutors_group(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    owner = await db.add_tutor("Owner", TUTOR_TG)
    other = await db.add_tutor("Other", OTHER_TG)
    group = await db.add_group(owner.id, "DI-21")
    student = make_user(STUDENT_TG)
    await register_ttj(dp, bot, session, student, owner.id, group.id)
    session.clear()

    intruder = make_user(OTHER_TG)
    for data in (
        f"tut:excel_group:{group.id}:",
        f"tut:view:{group.id}:",
        f"tut:delete:{group.id}:",
        f"tut:confirm_delete:{group.id}:",
        f"tut:rename:{group.id}:",
    ):
        await feed(dp, bot, callback_update(intruder, data))
    assert not session.of("SendDocument")
    answers = session.of("AnswerCallbackQuery")
    assert len(answers) == 5 and all(a.text == texts.NO_PERMISSION for a in answers)
    assert await db.get_group(group.id) is not None
    assert other.id != owner.id

    # a stranger with no tutor role is refused outright
    stranger = make_user(4004)
    await feed(dp, bot, text_update(stranger, "/tutor"))
    assert session.last_text(4004) == texts.TUTOR_ONLY
    await feed(dp, bot, callback_update(stranger, f"tut:excel_group:{group.id}:"))
    assert session.of("AnswerCallbackQuery")[-1].text == texts.STALE_BUTTON
    assert not session.of("SendDocument")


async def test_deleted_tutor_loses_access_immediately(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Temp", TUTOR_TG)
    user = make_user(TUTOR_TG)
    await feed(dp, bot, text_update(user, "/tutor"))
    assert "Tyutor panel" in session.last_text(TUTOR_TG)
    await db.delete_tutor(tutor.id)
    await feed(dp, bot, text_update(user, "/tutor"))
    assert session.last_text(TUTOR_TG) == texts.TUTOR_ONLY


async def test_admin_delete_tutor_cascades(dp: Dispatcher, bot: Bot, session: FakeSession, db: Database) -> None:
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    await register_ttj(dp, bot, session, make_user(STUDENT_TG), tutor.id, group.id)
    session.clear()

    admin = make_user(SUPERADMIN_ID)
    await feed(dp, bot, callback_update(admin, f"adm:delete:{tutor.id}"))
    assert "1 ta guruh va 1 ta talaba" in session.last_text(SUPERADMIN_ID)
    await feed(dp, bot, callback_update(admin, f"adm:confirm_delete:{tutor.id}"))
    assert await db.get_tutor(tutor.id) is None
    assert await db.get_student_by_telegram_id(STUDENT_TG) is None
    assert texts.TUTOR_DELETED in session.last_text(SUPERADMIN_ID)
    # the removed tutor's command menu is reset
    assert any(getattr(m.scope, "chat_id", None) == TUTOR_TG for m in session.of("DeleteMyCommands"))


def forwarded_update(user: User, sender_id: int) -> Update:
    from datetime import datetime

    from aiogram.types import Chat, Message, MessageOriginUser

    message = Message(
        message_id=999,
        date=datetime.now(),
        chat=Chat(id=user.id, type="private"),
        from_user=user,
        text="hello",
        forward_origin=MessageOriginUser(type="user", date=datetime.now(), sender_user=make_user(sender_id)),
    )
    return Update(update_id=999_999, message=message)


async def test_admin_edit_tutor_name_and_forwarded_telegram_id(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    admin = make_user(SUPERADMIN_ID)
    tutor = await db.add_tutor("Eski Ism", TUTOR_TG)

    await feed(dp, bot, text_update(admin, "/edit_tutor"))
    assert session.last_text(SUPERADMIN_ID) == texts.TUTOR_PICK_EDIT
    await feed(dp, bot, callback_update(admin, f"adm:edit_pick:{tutor.id}"))
    assert "nimani o'zgartirasiz" in session.last_text(SUPERADMIN_ID)
    await feed(dp, bot, callback_update(admin, f"adm:edit_name:{tutor.id}"), text_update(admin, "Yangi Ism"))
    updated = await db.get_tutor(tutor.id)
    assert updated is not None and updated.name == "Yangi Ism"
    assert texts.TUTOR_UPDATED in session.sent_texts(SUPERADMIN_ID)

    await feed(dp, bot, callback_update(admin, f"adm:edit_tg:{tutor.id}"), forwarded_update(admin, 5005))
    updated = await db.get_tutor(tutor.id)
    assert updated is not None and updated.telegram_id == 5005
    scopes = {getattr(m.scope, "chat_id", None) for m in session.of("SetMyCommands") + session.of("DeleteMyCommands")}
    assert {TUTOR_TG, 5005} <= scopes


async def test_tutor_rename_and_delete_group(dp: Dispatcher, bot: Bot, session: FakeSession, db: Database) -> None:
    user = make_user(TUTOR_TG)
    tutor = await db.add_tutor("Tutor", TUTOR_TG)
    g1 = await db.add_group(tutor.id, "G1")
    g2 = await db.add_group(tutor.id, "G2")

    await feed(dp, bot, text_update(user, "/edit_group"), callback_update(user, f"tut:rename:{g1.id}:"))
    assert "yangi nom" in session.last_text(TUTOR_TG)
    await feed(dp, bot, text_update(user, "G2"))
    assert session.last_text(TUTOR_TG) == texts.GROUP_DUPLICATE
    await feed(dp, bot, text_update(user, "G1-yangi"))
    renamed = await db.get_group(g1.id)
    assert renamed is not None and renamed.name == "G1-yangi"

    await feed(dp, bot, text_update(user, "/delete_group"), callback_update(user, f"tut:delete:{g2.id}:"))
    assert "0 ta talaba" in session.last_text(TUTOR_TG)
    await feed(dp, bot, callback_update(user, f"tut:confirm_delete:{g2.id}:"))
    assert await db.get_group(g2.id) is None
    assert texts.GROUP_DELETED in session.last_text(TUTOR_TG)

    await feed(dp, bot, text_update(user, "/groups"), callback_update(user, f"tut:view:{g1.id}:"))
    assert "G1-yangi" in session.last_text(TUTOR_TG)
    await feed(dp, bot, text_update(user, "/excel"), callback_update(user, "tut:excel_res:0:"))
    assert session.last_text(TUTOR_TG) == texts.EXCEL_PICK_RESIDENCE


async def test_registration_navigation_and_role_user_finish(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    empty_tutor = await db.add_tutor("Bo'sh Tyutor", 7007)
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    admin = make_user(SUPERADMIN_ID)

    await feed(dp, bot, text_update(admin, texts.BTN_REGISTER), callback_update(admin, f"reg:tutor:{empty_tutor.id}"))
    assert session.last_text(SUPERADMIN_ID) == texts.REG_TUTOR_NO_GROUPS
    await feed(dp, bot, callback_update(admin, "reg:back:0"))
    assert session.last_text(SUPERADMIN_ID) == texts.REG_CHOOSE_TUTOR
    await feed(dp, bot, text_update(admin, "salom"))
    assert session.last_text(SUPERADMIN_ID) == texts.USE_BUTTONS
    await feed(
        dp, bot, callback_update(admin, f"reg:tutor:{tutor.id}"), callback_update(admin, f"reg:group:{group.id}")
    )
    await feed(dp, bot, text_update(admin, "+998901234567"), text_update(admin, "Admin Talaba"))
    await feed(dp, bot, callback_update(admin, "reg:restart:0"))
    assert session.last_text(SUPERADMIN_ID) == texts.REG_CHOOSE_TUTOR
    assert await dp.fsm.get_context(bot, SUPERADMIN_ID, SUPERADMIN_ID).get_data() == {}

    session.clear()
    await register_ttj(dp, bot, session, admin, tutor.id, group.id, start_text=texts.BTN_REGISTER)
    saved = [m for m in session.of("SendMessage") if m.chat_id == SUPERADMIN_ID and m.text == texts.REG_SAVED]
    assert reply_button_texts(saved[0].reply_markup) == [texts.BTN_ADMIN_PANEL, texts.BTN_REGISTER]
    cards = [m for m in session.of("SendMessage") if m.text and m.text.startswith(texts.CARD_TITLE_NEW)]
    assert sorted(m.chat_id for m in cards) == [SUPERADMIN_ID, SECOND_SUPERADMIN_ID, TUTOR_TG]

    # cancel via inline button and "no tutors" start
    await feed(dp, bot, text_update(admin, texts.BTN_REGISTER), callback_update(admin, "reg:cancel:0"))
    assert session.last_text(SUPERADMIN_ID) == texts.CANCELLED
    for t in await db.list_tutors():
        await db.delete_tutor(t.id)
    stranger = make_user(8008)
    await feed(dp, bot, text_update(stranger, "/start"))
    assert session.last_text(8008) == texts.REG_NO_TUTORS


async def test_group_deleted_mid_registration_restarts(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    student = make_user(STUDENT_TG)
    await feed(
        dp,
        bot,
        text_update(student, "/start"),
        callback_update(student, f"reg:tutor:{tutor.id}"),
        callback_update(student, f"reg:group:{group.id}"),
        text_update(student, "+998901234567"),
        text_update(student, "Aliyev Vali"),
        text_update(student, "Dasturiy injiniring"),
        text_update(student, texts.BTN_RES_TTJ),
        text_update(student, "Aliyev G'ani"),
        text_update(student, "+998901111111"),
        text_update(student, "Aliyeva Zulfiya"),
    )
    await db.delete_group(group.id)
    await feed(dp, bot, text_update(student, "+998902222222"))
    assert texts.REG_GROUP_NOT_FOUND in session.sent_texts(STUDENT_TG)
    assert session.last_text(STUDENT_TG) == texts.REG_CHOOSE_TUTOR
    assert await db.get_student_by_telegram_id(STUDENT_TG) is None


# ------------------------------------------------- student edits their data


async def test_registered_student_sees_their_card_instead_of_a_new_registration(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    student = make_user(STUDENT_TG, username="vali")
    await register_ttj(dp, bot, session, student, tutor.id, group.id)
    session.clear()

    await feed(dp, bot, text_update(student, "/start"))
    card = session.of("SendMessage")[-1]
    assert texts.STUDENT_HOME_TITLE in str(card.text)
    assert "Aliyev Vali G'aniyevich" in str(card.text)
    assert inline_data(card.reply_markup) == {"edt:open:", "edt:again:"}

    # the whole flow is still one button away
    await feed(dp, bot, callback_update(student, "edt:again:"))
    assert session.last_text(STUDENT_TG) == texts.REG_CHOOSE_TUTOR


async def test_mydata_starts_registration_when_nothing_is_saved(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    await db.add_group(tutor.id, "DI-21")

    await feed(dp, bot, text_update(make_user(STUDENT_TG), "/mydata"))
    assert texts.STUDENT_NOT_REGISTERED in session.sent_texts(STUDENT_TG)
    assert session.last_text(STUDENT_TG) == texts.REG_CHOOSE_TUTOR


async def test_student_edits_one_field_and_everyone_is_notified_once(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    student = make_user(STUDENT_TG, username="vali")
    await register_ttj(dp, bot, session, student, tutor.id, group.id)
    before = await db.get_student_by_telegram_id(STUDENT_TG)
    assert before is not None and before.edited_at is None
    session.clear()

    await feed(dp, bot, text_update(student, "/mydata"), callback_update(student, "edt:open:"))
    menu = session.of("SendMessage")[-1]
    assert texts.EDIT_MENU in str(menu.text)
    buttons = inline_data(menu.reply_markup)
    assert {"edt:field:phone", "edt:field:full_name", "edt:res:", "edt:tg:", "edt:done:"} <= buttons
    assert "edt:field:address" not in buttons  # a TTJ resident has no street address to edit

    await feed(dp, bot, callback_update(student, "edt:field:phone"))
    assert session.last_text(STUDENT_TG) == texts.REG_ASK_PHONE
    await feed(dp, bot, text_update(student, "12345"))
    assert session.last_text(STUDENT_TG) == texts.REG_PHONE_INVALID  # rejected, still asking
    await feed(dp, bot, text_update(student, "+998905555555"))

    after = await db.get_student_by_telegram_id(STUDENT_TG)
    assert after is not None
    assert after.phone == "+998905555555"
    assert after.full_name == before.full_name and after.created_at == before.created_at
    assert after.edited_at  # marked as changed after registration
    assert texts.EDIT_SAVED in session.sent_texts(STUDENT_TG)

    session.clear()
    await feed(dp, bot, callback_update(student, "edt:done:"))
    cards = [m for m in session.of("SendMessage") if m.text and m.text.startswith(texts.CARD_TITLE_UPDATE)]
    assert sorted(m.chat_id for m in cards) == [SUPERADMIN_ID, SECOND_SUPERADMIN_ID, TUTOR_TG]
    assert "+998905555555" in str(cards[0].text)
    assert texts.EDIT_DONE in session.sent_texts(STUDENT_TG)


async def test_student_edit_switches_residence_and_address_together(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    student = make_user(STUDENT_TG, username="vali")
    await register_and_open_editor(dp, bot, session, db, student, tutor.id, group.id)

    await feed(dp, bot, callback_update(student, "edt:res:"))
    assert session.last_text(STUDENT_TG) == texts.REG_ASK_RESIDENCE
    await feed(dp, bot, text_update(student, texts.BTN_RES_KVARTIRA))
    assert session.last_text(STUDENT_TG) == texts.REG_ASK_ADDRESS
    await feed(dp, bot, text_update(student, "Toshkent, Yakkasaroy 7"))

    row = await db.get_student_by_telegram_id(STUDENT_TG)
    assert row is not None and row.residence == "kvartira" and row.address == "Toshkent, Yakkasaroy 7"
    assert "edt:field:address" in inline_data(session.of("SendMessage")[-1].reply_markup)

    # back to the dormitory: the address is filled in without asking
    await feed(dp, bot, callback_update(student, "edt:res:"), text_update(student, texts.BTN_RES_TTJ))
    row = await db.get_student_by_telegram_id(STUDENT_TG)
    assert row is not None and row.residence == "ttj" and row.address == "TTJ"


async def test_student_edit_moves_to_another_tutor_and_group(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    first = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    second = await db.add_tutor("Aliyev Bobur", OTHER_TUTOR_TG)
    g1 = await db.add_group(first.id, "DI-21")
    g2 = await db.add_group(second.id, "AI-22")
    student = make_user(STUDENT_TG, username="vali")
    await register_and_open_editor(dp, bot, session, db, student, first.id, g1.id)

    await feed(dp, bot, callback_update(student, "edt:tg:"))
    assert texts.EDIT_ASK_TUTOR in session.sent_texts(STUDENT_TG)
    await feed(dp, bot, callback_update(student, f"reg:tutor:{second.id}"))
    assert texts.EDIT_ASK_GROUP in session.sent_texts(STUDENT_TG)
    await feed(dp, bot, callback_update(student, f"reg:group:{g2.id}"))

    row = await db.get_student_by_telegram_id(STUDENT_TG)
    assert row is not None
    assert row.tutor_id == second.id and row.group_id == g2.id and row.group_name == "AI-22"
    assert await db.count_group_students(g1.id) == 0
    assert await db.count_group_students(g2.id) == 1

    # the new tutor is the one who hears about the next save
    session.clear()
    await feed(dp, bot, callback_update(student, "edt:done:"))
    cards = [m for m in session.of("SendMessage") if m.text and m.text.startswith(texts.CARD_TITLE_UPDATE)]
    assert sorted(m.chat_id for m in cards) == [SUPERADMIN_ID, SECOND_SUPERADMIN_ID, OTHER_TUTOR_TG]


async def test_leaving_the_editor_untouched_notifies_nobody(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    student = make_user(STUDENT_TG, username="vali")
    await register_and_open_editor(dp, bot, session, db, student, tutor.id, group.id)

    session.clear()
    await feed(dp, bot, callback_update(student, "edt:done:"))
    assert texts.EDIT_NOTHING_CHANGED in session.sent_texts(STUDENT_TG)
    assert not [m for m in session.of("SendMessage") if m.text and m.text.startswith(texts.CARD_TITLE_UPDATE)]
    row = await db.get_student_by_telegram_id(STUDENT_TG)
    assert row is not None and row.edited_at is None


async def test_edited_values_reach_the_admin_export(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    """What the admin downloads must be what the student last saved."""
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    student = make_user(STUDENT_TG, username="vali")
    await register_and_open_editor(dp, bot, session, db, student, tutor.id, group.id)

    await feed(
        dp,
        bot,
        callback_update(student, "edt:field:full_name"),
        text_update(student, "Aliyev Vali Yangi"),
        callback_update(student, "edt:field:direction"),
        text_update(student, "Sun'iy intellekt"),
        callback_update(student, "edt:done:"),
    )

    workbook = load_workbook(BytesIO(build_all_tutors_workbook([tutor], await db.list_students())))
    sheet = workbook[ALL_SHEET_NAME]
    header = [c.value for c in sheet[1]]
    row = dict(zip(header, [c.value for c in sheet[2]]))
    assert row["F.I.SH"] == "Aliyev Vali Yangi"
    assert row["Yo'nalish"] == "Sun'iy intellekt"
    assert row["Oxirgi tahrir"]  # filled only once the row has been edited
    assert row["Ro'yxatdan o'tgan vaqt"]


# --------------------------------------------------------------- /users


async def test_users_lists_everyone_who_pressed_start(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    tutor = await db.add_tutor("Karimov Aziz", TUTOR_TG)
    group = await db.add_group(tutor.id, "DI-21")
    await register_ttj(dp, bot, session, make_user(STUDENT_TG, username="vali"), tutor.id, group.id)
    # started the bot but walked away before finishing
    await feed(dp, bot, text_update(make_user(OTHER_TG, username="kimdir"), "/start"))
    session.clear()

    await feed(dp, bot, text_update(make_user(SUPERADMIN_ID), "/users"))
    listing = session.of("SendMessage")[-1]
    text = str(listing.text)
    assert "Jami: <b>2</b> ta" in text
    assert "ro'yxatdan o'tgan: <b>1</b> ta" in text and "o'tmagan: <b>1</b> ta" in text
    assert f"<code>{STUDENT_TG}</code>" in text and f"<code>{OTHER_TG}</code>" in text
    assert "@vali" in text and "@kimdir" in text
    assert "✅" in text and "🕗" in text
    assert inline_data(listing.reply_markup) == {"adm:panel:0"}  # single page: no arrows


async def test_users_pages_and_refuses_non_admins(
    dp: Dispatcher, bot: Bot, session: FakeSession, db: Database
) -> None:
    for index in range(25):
        await db.touch_user(9000 + index, f"user{index}", f"Foydalanuvchi {index}")

    admin = make_user(SUPERADMIN_ID)
    await feed(dp, bot, text_update(admin, "/users"))
    first = session.of("SendMessage")[-1]
    assert "Jami: <b>25</b> ta" in str(first.text) and "1/2-sahifa" in str(first.text)
    assert "<code>9000</code>" in str(first.text) and "<code>9020</code>" not in str(first.text)
    assert inline_data(first.reply_markup) == {"usr:1", "adm:panel:0"}  # forward only

    session.clear()
    await feed(dp, bot, callback_update(admin, "usr:1"))
    second = session.sent_texts(SUPERADMIN_ID)[-1]
    assert "2/2-sahifa" in second and "<code>9020</code>" in second
    assert "21. " in second and "25. " in second  # numbering continues across pages

    session.clear()
    await feed(dp, bot, text_update(make_user(STUDENT_TG), "/users"))
    assert session.last_text(STUDENT_TG) == texts.ADMIN_ONLY
