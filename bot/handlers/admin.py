"""Superadmin panel (§6): tutor CRUD and global Excel export. Every handler is guarded by ``IsSuperAdmin``."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    MessageOriginUser,
)

from .. import texts
from ..commands import refresh_user_commands
from ..config import Settings
from ..db import Database, DuplicateError
from ..excel import build_all_tutors_workbook, build_full_all_tutors_workbook
from ..filters import IsFreeText, IsSuperAdmin, get_roles
from ..keyboards import (
    ADM_ADD,
    ADM_CANCEL,
    ADM_CONFIRM_DELETE,
    ADM_DELETE,
    ADM_EDIT_NAME,
    ADM_EDIT_PICK,
    ADM_EDIT_TG,
    ADM_EXCEL_ALL,
    ADM_EXCEL_ALL_FULL,
    ADM_EXCEL_PICK,
    ADM_EXCEL_TUTOR,
    ADM_EXCEL_TUTOR_FULL,
    ADM_GROUPS,
    ADM_LIST,
    ADM_PANEL,
    ADM_SAVE,
    ADM_VIEW,
    TST_ADD,
    TST_DELETE,
    TST_LIST,
    AdminCb,
    TestCb,
    UsersCb,
    admin_back_kb,
    admin_confirm_delete_kb,
    admin_edit_field_kb,
    admin_group_list_kb,
    admin_panel_kb,
    admin_save_kb,
    admin_tutor_card_kb,
    admin_test_users_kb,
    admin_tutor_list_kb,
    admin_users_kb,
    cancel_kb,
    main_menu_kb,
)
from ..models import Tutor
from ..states import AdminTestUserAdd, AdminTutorAdd, AdminTutorEdit
from ..utils import clean_text, edit_or_send, hesc, parse_telegram_id, remove_inline_keyboard, today_str
from .tutor import send_full_tutor_workbook, send_tutor_workbook

log = logging.getLogger(__name__)

TUTOR_NAME_MAX_LEN = 100
USERS_PAGE_SIZE = 20


# ------------------------------------------------------------------ helpers


async def _tutor_list(
    db: Database, action: str = ADM_VIEW, title: str | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    tutors = await db.list_tutors()
    if not tutors:
        return texts.TUTOR_LIST_EMPTY, admin_back_kb()
    return title or texts.TUTOR_LIST_TITLE.format(n=len(tutors)), admin_tutor_list_kb(tutors, action=action)


async def _users_page(db: Database, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Render one page of /users, clamping ``page`` into range so a stale arrow cannot overshoot."""
    total, registered = await db.count_users()
    if total == 0:
        return texts.USERS_EMPTY, admin_back_kb()
    pages = (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE
    page = min(max(page, 0), pages - 1)
    offset = page * USERS_PAGE_SIZE
    users = await db.list_users(USERS_PAGE_SIZE, offset)
    return texts.users_page(users, total, registered, page, pages, offset), admin_users_kb(page, pages)


async def _tutor_card(db: Database, tutor: Tutor) -> str:
    groups, students, profiles = await db.count_tutor_groups_and_students(tutor.id)
    return texts.tutor_card(tutor, groups, students, profiles)


async def _load_tutor(callback: CallbackQuery, db: Database, tutor_id: int) -> Tutor | None:
    """Load a tutor by id; answers the callback with a 'not found' alert when it no longer exists."""
    tutor = await db.get_tutor(tutor_id)
    if tutor is None:
        await callback.answer(texts.TUTOR_NOT_FOUND, show_alert=True)
    return tutor


async def _send_saved(bot: Bot, db: Database, settings: Settings, chat_id: int, text: str, tutor: Tutor) -> None:
    is_admin, is_tutor = await get_roles(db, settings, chat_id)
    await bot.send_message(chat_id, text, reply_markup=main_menu_kb(is_admin, is_tutor))
    await bot.send_message(chat_id, await _tutor_card(db, tutor), reply_markup=admin_tutor_card_kb(tutor.id))


def _forwarded_user_name(message: Message) -> str:
    """Display name of a forwarded message's sender, so a new tester is not listed as a bare id."""
    origin = message.forward_origin
    if isinstance(origin, MessageOriginUser):
        return origin.sender_user.full_name
    if message.forward_from is not None:
        return message.forward_from.full_name
    return ""


def _telegram_id_from_message(message: Message) -> tuple[int | None, bool]:
    """Extract a Telegram user ID from typed text or a forwarded message.

    Returns ``(user_id, forwarded_but_hidden)``.
    """
    origin = message.forward_origin
    if isinstance(origin, MessageOriginUser):
        return origin.sender_user.id, False
    if message.forward_from is not None:
        return message.forward_from.id, False
    if origin is not None or message.forward_sender_name:
        return None, True
    return parse_telegram_id(message.text), False


# -------------------------------------------------------------------- panel


async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.ADMIN_PANEL, reply_markup=admin_panel_kb())


async def _test_users_view(db: Database) -> tuple[str, InlineKeyboardMarkup]:
    users = await db.list_test_users()
    return texts.test_users_text(users), admin_test_users_kb(users)


async def cmd_test_users(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, markup = await _test_users_view(db)
    await message.answer(text, reply_markup=markup)


async def cb_test_users(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    text, markup = await _test_users_view(db)
    await edit_or_send(callback, bot, text, markup)


async def cb_add_test_user(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(AdminTestUserAdd.telegram_id)
    await callback.answer()
    await bot.send_message(callback.from_user.id, texts.ASK_TEST_USER_TG, reply_markup=cancel_kb())


async def add_test_user_id(
    message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    telegram_id, hidden = _telegram_id_from_message(message)
    if hidden:
        await message.answer(texts.TUTOR_TG_HIDDEN, reply_markup=cancel_kb())
        return
    if telegram_id is None:
        await message.answer(texts.TUTOR_TG_INVALID, reply_markup=cancel_kb())
        return
    added = await db.add_test_user(telegram_id, _forwarded_user_name(message))
    await state.clear()
    admin_id = message.from_user.id if message.from_user is not None else message.chat.id
    is_admin, is_tutor = await get_roles(db, settings, admin_id)
    await message.answer(
        texts.TEST_USER_ADDED.format(telegram_id=telegram_id) if added else texts.TEST_USER_DUPLICATE,
        reply_markup=main_menu_kb(is_admin, is_tutor),
    )
    if added:
        log.info("Superadmin %s added test user %s", admin_id, telegram_id)
    text, markup = await _test_users_view(db)
    await message.answer(text, reply_markup=markup)


async def cb_delete_test_user(
    callback: CallbackQuery, callback_data: TestCb, state: FSMContext, db: Database, bot: Bot
) -> None:
    await state.clear()
    removed = await db.remove_test_user(callback_data.user_id)
    await callback.answer(texts.TEST_USER_REMOVED if removed else texts.STALE_BUTTON, show_alert=not removed)
    if removed:
        log.info("Superadmin %s removed test user %s", callback.from_user.id, callback_data.user_id)
    text, markup = await _test_users_view(db)
    await edit_or_send(callback, bot, text, markup)


async def cmd_users(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, markup = await _users_page(db, 0)
    await message.answer(text, reply_markup=markup)


async def cb_users(callback: CallbackQuery, callback_data: UsersCb, state: FSMContext, db: Database, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    text, markup = await _users_page(db, callback_data.page)
    await edit_or_send(callback, bot, text, markup)


async def cb_panel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    await edit_or_send(callback, bot, texts.ADMIN_PANEL, admin_panel_kb())


# --------------------------------------------------------------- tutor list


async def cmd_tutors(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = await _tutor_list(db)
    await message.answer(text, reply_markup=kb)


async def cb_list(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    await callback.answer()
    text, kb = await _tutor_list(db)
    await edit_or_send(callback, bot, text, kb)


async def cb_view(callback: CallbackQuery, callback_data: AdminCb, db: Database, bot: Bot) -> None:
    tutor = await _load_tutor(callback, db, callback_data.tutor_id)
    if tutor is None:
        return
    await callback.answer()
    await edit_or_send(callback, bot, await _tutor_card(db, tutor), admin_tutor_card_kb(tutor.id))


async def cb_groups(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext, db: Database, bot: Bot) -> None:
    """A tutor's groups; each opens its students in admin mode (``bot.handlers.manage``)."""
    tutor = await _load_tutor(callback, db, callback_data.tutor_id)
    if tutor is None:
        return
    await state.clear()
    await callback.answer()
    groups = await db.list_groups(tutor.id)
    if groups:
        text = texts.TUTOR_GROUP_LIST_TITLE.format(name=hesc(tutor.name), n=len(groups))
    else:
        text = texts.TUTOR_GROUP_LIST_EMPTY.format(name=hesc(tutor.name))
    await edit_or_send(callback, bot, text, admin_group_list_kb(groups, tutor.id))


# ---------------------------------------------------------------- add tutor


async def _start_add_tutor(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminTutorAdd.name)
    await bot.send_message(chat_id, texts.ASK_TUTOR_NAME, reply_markup=cancel_kb())


async def cmd_add_tutor(message: Message, state: FSMContext, bot: Bot) -> None:
    await _start_add_tutor(bot, message.chat.id, state)


async def cb_add_tutor(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _start_add_tutor(bot, callback.from_user.id, state)


async def add_tutor_name(message: Message, state: FSMContext) -> None:
    name = clean_text(message.text)
    if not name or len(name) > TUTOR_NAME_MAX_LEN:
        await message.answer(texts.TUTOR_NAME_INVALID, reply_markup=cancel_kb())
        return
    await state.update_data(name=name)
    await state.set_state(AdminTutorAdd.telegram_id)
    await message.answer(texts.ASK_TUTOR_TG, reply_markup=cancel_kb())


async def add_tutor_telegram_id(message: Message, state: FSMContext, db: Database) -> None:
    telegram_id, hidden = _telegram_id_from_message(message)
    if hidden:
        await message.answer(texts.TUTOR_TG_HIDDEN, reply_markup=cancel_kb())
        return
    if telegram_id is None:
        await message.answer(texts.TUTOR_TG_INVALID, reply_markup=cancel_kb())
        return
    if await db.get_tutor_by_telegram_id(telegram_id) is not None:
        await message.answer(texts.TUTOR_TG_DUPLICATE, reply_markup=cancel_kb())
        return
    await state.update_data(telegram_id=telegram_id)
    await state.set_state(AdminTutorAdd.confirm)
    data = await state.get_data()
    await message.answer(
        texts.TUTOR_CONFIRM_ADD.format(name=hesc(data["name"]), telegram_id=telegram_id),
        reply_markup=admin_save_kb(),
    )


async def add_tutor_save(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    # Single-shot guard against a double-tap (see ``student.reg_confirm`` for why the live state is
    # re-checked): the second tap must not race the first one into a duplicate error / broken state.
    if await state.get_state() != AdminTutorAdd.confirm.state:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    data = await state.get_data()
    await state.set_state(None)
    await callback.answer()
    await remove_inline_keyboard(callback)
    try:
        tutor = await db.add_tutor(data["name"], int(data["telegram_id"]))
    except DuplicateError:
        await state.set_state(AdminTutorAdd.telegram_id)
        await bot.send_message(callback.from_user.id, texts.TUTOR_TG_DUPLICATE, reply_markup=cancel_kb())
        return
    await state.clear()
    log.info("Superadmin %s added tutor %s (%r, tg=%s)", callback.from_user.id, tutor.id, tutor.name, tutor.telegram_id)
    await _send_saved(bot, db, settings, callback.from_user.id, texts.TUTOR_SAVED, tutor)
    await refresh_user_commands(bot, db, settings, tutor.telegram_id)


async def add_tutor_cancel(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    await state.clear()
    await callback.answer()
    await remove_inline_keyboard(callback)
    is_admin, is_tutor = await get_roles(db, settings, callback.from_user.id)
    await bot.send_message(callback.from_user.id, texts.CANCELLED, reply_markup=main_menu_kb(is_admin, is_tutor))


async def add_tutor_expect_buttons(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)


# --------------------------------------------------------------- edit tutor


async def cmd_edit_tutor(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = await _tutor_list(db, action=ADM_EDIT_PICK, title=texts.TUTOR_PICK_EDIT)
    await message.answer(text, reply_markup=kb)


async def cb_edit_pick(callback: CallbackQuery, callback_data: AdminCb, db: Database, bot: Bot) -> None:
    tutor = await _load_tutor(callback, db, callback_data.tutor_id)
    if tutor is None:
        return
    await callback.answer()
    await edit_or_send(
        callback, bot, texts.TUTOR_EDIT_FIELD.format(name=hesc(tutor.name)), admin_edit_field_kb(tutor.id)
    )


async def cb_edit_field(
    callback: CallbackQuery, callback_data: AdminCb, state: FSMContext, db: Database, bot: Bot
) -> None:
    tutor = await _load_tutor(callback, db, callback_data.tutor_id)
    if tutor is None:
        return
    await state.clear()
    await state.update_data(tutor_id=tutor.id)
    if callback_data.action == ADM_EDIT_NAME:
        await state.set_state(AdminTutorEdit.name)
        prompt = texts.ASK_TUTOR_NEW_NAME
    else:
        await state.set_state(AdminTutorEdit.telegram_id)
        prompt = texts.ASK_TUTOR_NEW_TG
    await callback.answer()
    await bot.send_message(callback.from_user.id, prompt, reply_markup=cancel_kb())


async def _tutor_gone(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    await state.clear()
    is_admin, is_tutor = await get_roles(db, settings, message.chat.id)
    await message.answer(texts.TUTOR_NOT_FOUND, reply_markup=main_menu_kb(is_admin, is_tutor))


async def edit_tutor_name(message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    name = clean_text(message.text)
    if not name or len(name) > TUTOR_NAME_MAX_LEN:
        await message.answer(texts.TUTOR_NAME_INVALID, reply_markup=cancel_kb())
        return
    data = await state.get_data()
    tutor_id = int(data.get("tutor_id") or 0)
    if not await db.update_tutor_name(tutor_id, name):
        await _tutor_gone(message, state, db, settings)
        return
    await state.clear()
    tutor = await db.get_tutor(tutor_id)
    assert tutor is not None
    await _send_saved(bot, db, settings, message.chat.id, texts.TUTOR_UPDATED, tutor)


async def edit_tutor_telegram_id(
    message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    telegram_id, hidden = _telegram_id_from_message(message)
    if hidden:
        await message.answer(texts.TUTOR_TG_HIDDEN, reply_markup=cancel_kb())
        return
    if telegram_id is None:
        await message.answer(texts.TUTOR_TG_INVALID, reply_markup=cancel_kb())
        return
    data = await state.get_data()
    tutor_id = int(data.get("tutor_id") or 0)
    tutor = await db.get_tutor(tutor_id)
    if tutor is None:
        await _tutor_gone(message, state, db, settings)
        return
    try:
        await db.update_tutor_telegram_id(tutor.id, telegram_id)
    except DuplicateError:
        await message.answer(texts.TUTOR_TG_DUPLICATE, reply_markup=cancel_kb())
        return
    await state.clear()
    updated = await db.get_tutor(tutor.id)
    assert updated is not None
    await _send_saved(bot, db, settings, message.chat.id, texts.TUTOR_UPDATED, updated)
    for user_id in {tutor.telegram_id, updated.telegram_id}:
        await refresh_user_commands(bot, db, settings, user_id)


# ------------------------------------------------------------- delete tutor


async def cmd_delete_tutor(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, kb = await _tutor_list(db, action=ADM_DELETE, title=texts.TUTOR_PICK_DELETE)
    await message.answer(text, reply_markup=kb)


async def cb_delete(callback: CallbackQuery, callback_data: AdminCb, db: Database, bot: Bot) -> None:
    tutor = await _load_tutor(callback, db, callback_data.tutor_id)
    if tutor is None:
        return
    groups, students, profiles = await db.count_tutor_groups_and_students(tutor.id)
    await callback.answer()
    await edit_or_send(
        callback,
        bot,
        texts.TUTOR_DELETE_CONFIRM.format(name=hesc(tutor.name), groups=groups, students=students + profiles),
        admin_confirm_delete_kb(tutor.id),
    )


async def cb_confirm_delete(
    callback: CallbackQuery, callback_data: AdminCb, db: Database, settings: Settings, bot: Bot
) -> None:
    tutor = await _load_tutor(callback, db, callback_data.tutor_id)
    if tutor is None:
        return
    if not await db.delete_tutor(tutor.id):  # a concurrent tap already deleted it
        await callback.answer(texts.TUTOR_NOT_FOUND, show_alert=True)
        return
    log.info("Superadmin %s deleted tutor %s (%r)", callback.from_user.id, tutor.id, tutor.name)
    await callback.answer(texts.TUTOR_DELETED)
    text, kb = await _tutor_list(db)
    await edit_or_send(callback, bot, f"{texts.TUTOR_DELETED}\n\n{text}", kb)
    await refresh_user_commands(bot, db, settings, tutor.telegram_id)


# -------------------------------------------------------------------- excel


async def cb_excel_all(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    await callback.answer()
    students = await db.list_students()
    if not students:
        await bot.send_message(callback.from_user.id, texts.NO_DATA)
        return
    tutors = await db.list_tutors()
    data = await asyncio.to_thread(build_all_tutors_workbook, tutors, students)
    await bot.send_document(
        callback.from_user.id,
        BufferedInputFile(data, filename=f"barcha_tyutorlar_{today_str()}.xlsx"),
        caption=texts.EXCEL_CAPTION.format(title="Barcha tyutorlar", count=len(students)),
    )


async def cb_excel_pick(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    await callback.answer()
    text, kb = await _tutor_list(db, action=ADM_EXCEL_TUTOR, title=texts.TUTOR_PICK_EXCEL)
    await edit_or_send(callback, bot, text, kb)


async def cb_excel_tutor(callback: CallbackQuery, callback_data: AdminCb, db: Database, bot: Bot) -> None:
    tutor = await _load_tutor(callback, db, callback_data.tutor_id)
    if tutor is None:
        return
    await callback.answer()
    await send_tutor_workbook(bot, callback.from_user.id, db, tutor)


async def cb_excel_all_full(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    """The full survey of every tutor: ``Barchasi`` plus one sheet per tutor."""
    await callback.answer()
    profiles = await db.list_full_profiles()
    if not profiles:
        await bot.send_message(callback.from_user.id, texts.NO_DATA)
        return
    tutors = await db.list_tutors()
    data = await asyncio.to_thread(build_full_all_tutors_workbook, tutors, profiles)
    await bot.send_document(
        callback.from_user.id,
        BufferedInputFile(data, filename=f"toliq_anketa_{today_str()}.xlsx"),
        caption=texts.EXCEL_CAPTION.format(title="To'liq anketa — barcha tyutorlar", count=len(profiles)),
    )


async def cb_excel_tutor_full(callback: CallbackQuery, callback_data: AdminCb, db: Database, bot: Bot) -> None:
    tutor = await _load_tutor(callback, db, callback_data.tutor_id)
    if tutor is None:
        return
    await callback.answer()
    await send_full_tutor_workbook(bot, callback.from_user.id, db, tutor)


# ------------------------------------------------------------- registration


def create_router() -> Router:
    """Build the superadmin router. A fresh instance is returned on every call (routers cannot be shared)."""
    router = Router(name="admin")
    router.message.filter(IsSuperAdmin())
    router.callback_query.filter(IsSuperAdmin())

    msg = router.message
    cb = router.callback_query

    # Slash commands and the panel button come first so they pre-empt every admin FSM step.
    msg.register(cmd_admin, Command("admin"))
    msg.register(cmd_admin, F.text == texts.BTN_ADMIN_PANEL)
    msg.register(cmd_tutors, Command("tutors"))
    msg.register(cmd_users, Command("users"))
    msg.register(cmd_test_users, Command("test_users"))
    msg.register(cmd_add_tutor, Command("add_tutor"))
    msg.register(cmd_edit_tutor, Command("edit_tutor"))
    msg.register(cmd_delete_tutor, Command("delete_tutor"))

    cb.register(cb_users, UsersCb.filter())
    cb.register(cb_test_users, TestCb.filter(F.action == TST_LIST))
    cb.register(cb_add_test_user, TestCb.filter(F.action == TST_ADD))
    cb.register(cb_delete_test_user, TestCb.filter(F.action == TST_DELETE))
    cb.register(cb_panel, AdminCb.filter(F.action == ADM_PANEL))
    cb.register(cb_list, AdminCb.filter(F.action == ADM_LIST))
    cb.register(cb_view, AdminCb.filter(F.action == ADM_VIEW))
    cb.register(cb_groups, AdminCb.filter(F.action == ADM_GROUPS))

    # FSM text steps only take free text: other routers' commands/buttons must fall through to them.
    free_text = IsFreeText()
    cb.register(cb_add_tutor, AdminCb.filter(F.action == ADM_ADD))
    msg.register(add_test_user_id, AdminTestUserAdd.telegram_id, free_text)
    msg.register(add_tutor_name, AdminTutorAdd.name, free_text)
    msg.register(add_tutor_telegram_id, AdminTutorAdd.telegram_id, free_text)
    cb.register(add_tutor_save, AdminTutorAdd.confirm, AdminCb.filter(F.action == ADM_SAVE))
    cb.register(add_tutor_cancel, AdminTutorAdd.confirm, AdminCb.filter(F.action == ADM_CANCEL))
    msg.register(add_tutor_expect_buttons, AdminTutorAdd.confirm, free_text)

    cb.register(cb_edit_pick, AdminCb.filter(F.action == ADM_EDIT_PICK))
    cb.register(cb_edit_field, AdminCb.filter(F.action.in_({ADM_EDIT_NAME, ADM_EDIT_TG})))
    msg.register(edit_tutor_name, AdminTutorEdit.name, free_text)
    msg.register(edit_tutor_telegram_id, AdminTutorEdit.telegram_id, free_text)

    cb.register(cb_delete, AdminCb.filter(F.action == ADM_DELETE))
    cb.register(cb_confirm_delete, AdminCb.filter(F.action == ADM_CONFIRM_DELETE))

    cb.register(cb_excel_all, AdminCb.filter(F.action == ADM_EXCEL_ALL))
    cb.register(cb_excel_pick, AdminCb.filter(F.action == ADM_EXCEL_PICK))
    cb.register(cb_excel_tutor, AdminCb.filter(F.action == ADM_EXCEL_TUTOR))
    cb.register(cb_excel_all_full, AdminCb.filter(F.action == ADM_EXCEL_ALL_FULL))
    cb.register(cb_excel_tutor_full, AdminCb.filter(F.action == ADM_EXCEL_TUTOR_FULL))
    return router
