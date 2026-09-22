"""Tutor panel (§7): own groups CRUD and Excel exports. Every handler is guarded by ``IsTutor``."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from .. import texts
from ..config import Settings
from ..db import Database, DuplicateError
from ..excel import (
    build_full_group_workbook,
    build_full_tutor_workbook,
    build_group_workbook,
    build_residence_workbook,
    build_tutor_workbook,
)
from ..filters import IsFreeText, IsTutor, get_roles
from ..keyboards import (
    TUT_ADD,
    TUT_CONFIRM_DELETE,
    TUT_DELETE,
    TUT_EXCEL_ALL,
    TUT_EXCEL_FULL_ALL,
    TUT_EXCEL_FULL_GROUP,
    TUT_EXCEL_FULL_PICK,
    TUT_EXCEL_GROUP,
    TUT_EXCEL_MENU,
    TUT_EXCEL_PICK_GROUP,
    TUT_EXCEL_RES,
    TUT_EXCEL_RES_PICK,
    TUT_GROUPS,
    TUT_PANEL,
    TUT_PHONE,
    TUT_RENAME,
    TUT_STUDENTS,
    TUT_VIEW,
    TutorCb,
    cancel_kb,
    main_menu_kb,
    phone_kb,
    tutor_confirm_delete_kb,
    tutor_excel_menu_kb,
    tutor_group_card_kb,
    tutor_group_list_kb,
    tutor_panel_kb,
    tutor_residence_kb,
)
from ..models import RESIDENCE_VALUES, Group, Tutor
from ..states import TutorGroupAdd, TutorGroupEdit, TutorPhone
from ..utils import clean_text, edit_or_send, hesc, normalize_phone, safe_filename_part, today_str

log = logging.getLogger(__name__)

GROUP_NAME_MAX_LEN = 64


# ------------------------------------------------------------------ helpers


def _panel_text(tutor: Tutor) -> str:
    """The panel; a tutor without a phone number is reminded, it is a column of the full survey."""
    text = texts.TUTOR_PANEL.format(name=hesc(tutor.name))
    return text if tutor.phone else f"{text}\n\n{texts.TUTOR_PHONE_MISSING}"


def _group_card(group: Group) -> str:
    return texts.GROUP_CARD.format(
        name=hesc(group.name),
        count=group.student_count,
        profiles=group.profile_count,
        created_at=hesc(group.created_at),
    )


async def _group_list(
    db: Database, tutor: Tutor, action: str = TUT_VIEW, title: str | None = None, back_action: str = TUT_PANEL
) -> tuple[str, InlineKeyboardMarkup]:
    groups = await db.list_groups(tutor.id)
    text = texts.GROUP_LIST_EMPTY if not groups else (title or texts.GROUP_LIST_TITLE.format(n=len(groups)))
    return text, tutor_group_list_kb(groups, action=action, back_action=back_action)


async def _own_group(callback: CallbackQuery, db: Database, tutor: Tutor, group_id: int) -> Group | None:
    """Load a group and verify it belongs to the calling tutor; answers the callback on failure."""
    group = await db.get_group(group_id)
    if group is None:
        await callback.answer(texts.GROUP_NOT_FOUND, show_alert=True)
        return None
    if group.tutor_id != tutor.id:
        log.warning("Tutor %s tried to access group %s owned by tutor %s", tutor.id, group.id, group.tutor_id)
        await callback.answer(texts.NO_PERMISSION, show_alert=True)
        return None
    return group


async def _send_saved(bot: Bot, db: Database, settings: Settings, chat_id: int, text: str, group: Group) -> None:
    is_admin, is_tutor = await get_roles(db, settings, chat_id)
    await bot.send_message(chat_id, text, reply_markup=main_menu_kb(is_admin, is_tutor))
    await bot.send_message(chat_id, _group_card(group), reply_markup=tutor_group_card_kb(group.id))


async def _send_document(bot: Bot, chat_id: int, data: bytes, filename: str, title: str, count: int) -> None:
    await bot.send_document(
        chat_id,
        BufferedInputFile(data, filename=filename),
        caption=texts.EXCEL_CAPTION.format(title=hesc(title), count=count),
    )


def _filename(tutor: Tutor, scope: str) -> str:
    return f"{safe_filename_part(tutor.name)}_{safe_filename_part(scope)}_{today_str()}.xlsx"


async def send_tutor_workbook(bot: Bot, chat_id: int, db: Database, tutor: Tutor) -> bool:
    """Send the tutor's full workbook (``Barchasi`` + one sheet per group). Returns False when empty."""
    students = await db.list_students(tutor_id=tutor.id)
    if not students:
        await bot.send_message(chat_id, texts.NO_DATA)
        return False
    groups = await db.list_groups(tutor.id)
    data = await asyncio.to_thread(build_tutor_workbook, groups, students)
    await _send_document(
        bot, chat_id, data, _filename(tutor, "barcha_guruhlar"), f"{tutor.name} — barcha guruhlar", len(students)
    )
    return True


# -------------------------------------------------------------------- panel


async def cmd_tutor(message: Message, state: FSMContext, tutor: Tutor) -> None:
    await state.clear()
    await message.answer(_panel_text(tutor), reply_markup=tutor_panel_kb())


async def cb_panel(callback: CallbackQuery, state: FSMContext, tutor: Tutor, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    await edit_or_send(callback, bot, _panel_text(tutor), tutor_panel_kb())


# -------------------------------------------------------------------- groups


async def cmd_groups(message: Message, state: FSMContext, db: Database, tutor: Tutor) -> None:
    await state.clear()
    text, kb = await _group_list(db, tutor)
    await message.answer(text, reply_markup=kb)


async def cb_groups(callback: CallbackQuery, db: Database, tutor: Tutor, bot: Bot) -> None:
    await callback.answer()
    text, kb = await _group_list(db, tutor)
    await edit_or_send(callback, bot, text, kb)


async def cb_view(callback: CallbackQuery, callback_data: TutorCb, db: Database, tutor: Tutor, bot: Bot) -> None:
    group = await _own_group(callback, db, tutor, callback_data.group_id)
    if group is None:
        return
    await callback.answer()
    await edit_or_send(callback, bot, _group_card(group), tutor_group_card_kb(group.id))


# ----------------------------------------------------------- students entry


async def cmd_students(message: Message, state: FSMContext, db: Database, tutor: Tutor) -> None:
    """/students: pick a group, then a student to write to or delete (``bot.handlers.manage``)."""
    await state.clear()
    text, kb = await _group_list(db, tutor, action=TUT_STUDENTS, title=texts.STUDENT_PICK_GROUP)
    await message.answer(text, reply_markup=kb)


async def cb_students(callback: CallbackQuery, state: FSMContext, db: Database, tutor: Tutor, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    text, kb = await _group_list(db, tutor, action=TUT_STUDENTS, title=texts.STUDENT_PICK_GROUP)
    await edit_or_send(callback, bot, text, kb)


# ----------------------------------------------------------------- add group


async def _start_add_group(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(TutorGroupAdd.name)
    await bot.send_message(chat_id, texts.ASK_GROUP_NAME, reply_markup=cancel_kb())


async def cmd_add_group(message: Message, state: FSMContext, bot: Bot) -> None:
    await _start_add_group(bot, message.chat.id, state)


async def cb_add_group(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _start_add_group(bot, callback.from_user.id, state)


async def add_group_name(
    message: Message, state: FSMContext, db: Database, settings: Settings, tutor: Tutor, bot: Bot
) -> None:
    name = clean_text(message.text)
    if not name or len(name) > GROUP_NAME_MAX_LEN:
        await message.answer(texts.GROUP_NAME_INVALID, reply_markup=cancel_kb())
        return
    try:
        group = await db.add_group(tutor.id, name)
    except DuplicateError:
        await message.answer(texts.GROUP_DUPLICATE, reply_markup=cancel_kb())
        return
    await state.clear()
    log.info("Tutor %s created group %s (%r)", tutor.id, group.id, group.name)
    await _send_saved(bot, db, settings, message.chat.id, texts.GROUP_SAVED, group)


# -------------------------------------------------------------- rename group


async def cmd_edit_group(message: Message, state: FSMContext, db: Database, tutor: Tutor) -> None:
    await state.clear()
    text, kb = await _group_list(db, tutor, action=TUT_RENAME, title=texts.GROUP_PICK_EDIT)
    await message.answer(text, reply_markup=kb)


async def cb_rename(
    callback: CallbackQuery, callback_data: TutorCb, state: FSMContext, db: Database, tutor: Tutor, bot: Bot
) -> None:
    group = await _own_group(callback, db, tutor, callback_data.group_id)
    if group is None:
        return
    await state.clear()
    await state.update_data(group_id=group.id)
    await state.set_state(TutorGroupEdit.name)
    await callback.answer()
    await bot.send_message(
        callback.from_user.id, texts.ASK_GROUP_NEW_NAME.format(name=hesc(group.name)), reply_markup=cancel_kb()
    )


async def rename_group_name(
    message: Message, state: FSMContext, db: Database, settings: Settings, tutor: Tutor, bot: Bot
) -> None:
    name = clean_text(message.text)
    if not name or len(name) > GROUP_NAME_MAX_LEN:
        await message.answer(texts.GROUP_NAME_INVALID, reply_markup=cancel_kb())
        return
    data = await state.get_data()
    group = await db.get_group(int(data.get("group_id") or 0))
    if group is None or group.tutor_id != tutor.id:
        await state.clear()
        is_admin, is_tutor = await get_roles(db, settings, message.chat.id)
        await message.answer(texts.GROUP_NOT_FOUND, reply_markup=main_menu_kb(is_admin, is_tutor))
        return
    try:
        await db.rename_group(group.id, name)
    except DuplicateError:
        await message.answer(texts.GROUP_DUPLICATE, reply_markup=cancel_kb())
        return
    await state.clear()
    updated = await db.get_group(group.id)
    assert updated is not None
    await _send_saved(bot, db, settings, message.chat.id, texts.GROUP_RENAMED, updated)


# -------------------------------------------------------------- delete group


async def cmd_delete_group(message: Message, state: FSMContext, db: Database, tutor: Tutor) -> None:
    await state.clear()
    text, kb = await _group_list(db, tutor, action=TUT_DELETE, title=texts.GROUP_PICK_DELETE)
    await message.answer(text, reply_markup=kb)


async def cb_delete(callback: CallbackQuery, callback_data: TutorCb, db: Database, tutor: Tutor, bot: Bot) -> None:
    group = await _own_group(callback, db, tutor, callback_data.group_id)
    if group is None:
        return
    await callback.answer()
    await edit_or_send(
        callback,
        bot,
        texts.GROUP_DELETE_CONFIRM.format(
            name=hesc(group.name), count=group.student_count, profiles=group.profile_count
        ),
        tutor_confirm_delete_kb(group.id),
    )


async def cb_confirm_delete(
    callback: CallbackQuery, callback_data: TutorCb, db: Database, tutor: Tutor, bot: Bot
) -> None:
    group = await _own_group(callback, db, tutor, callback_data.group_id)
    if group is None:
        return
    if not await db.delete_group(group.id):  # a concurrent tap already deleted it
        await callback.answer(texts.GROUP_NOT_FOUND, show_alert=True)
        return
    log.info("Tutor %s deleted group %s (%r)", tutor.id, group.id, group.name)
    await callback.answer(texts.GROUP_DELETED)
    text, kb = await _group_list(db, tutor)
    await edit_or_send(callback, bot, f"{texts.GROUP_DELETED}\n\n{text}", kb)


# -------------------------------------------------------------------- excel


async def cmd_excel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.EXCEL_MENU, reply_markup=tutor_excel_menu_kb())


async def cb_excel_menu(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await edit_or_send(callback, bot, texts.EXCEL_MENU, tutor_excel_menu_kb())


async def cb_excel_pick_group(callback: CallbackQuery, db: Database, tutor: Tutor, bot: Bot) -> None:
    await callback.answer()
    text, kb = await _group_list(
        db, tutor, action=TUT_EXCEL_GROUP, title=texts.GROUP_PICK_EXCEL, back_action=TUT_EXCEL_MENU
    )
    await edit_or_send(callback, bot, text, kb)


async def cb_excel_group(callback: CallbackQuery, callback_data: TutorCb, db: Database, tutor: Tutor, bot: Bot) -> None:
    group = await _own_group(callback, db, tutor, callback_data.group_id)
    if group is None:
        return
    await callback.answer()
    students = await db.list_students(tutor_id=tutor.id, group_id=group.id)
    if not students:
        await bot.send_message(callback.from_user.id, texts.NO_DATA)
        return
    data = await asyncio.to_thread(build_group_workbook, group, students)
    await _send_document(
        bot, callback.from_user.id, data, _filename(tutor, group.name), f"{group.name} guruhi", len(students)
    )


async def cb_excel_residence(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    await edit_or_send(callback, bot, texts.EXCEL_PICK_RESIDENCE, tutor_residence_kb())


async def cb_excel_residence_pick(
    callback: CallbackQuery, callback_data: TutorCb, db: Database, tutor: Tutor, bot: Bot
) -> None:
    residence = callback_data.value
    if residence not in RESIDENCE_VALUES:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await callback.answer()
    students = await db.list_students(tutor_id=tutor.id, residence=residence)
    if not students:
        await bot.send_message(callback.from_user.id, texts.NO_DATA)
        return
    label = texts.residence_label(residence)
    data = await asyncio.to_thread(build_residence_workbook, residence, students)
    await _send_document(
        bot, callback.from_user.id, data, _filename(tutor, label), f"Turar joy: {label}", len(students)
    )


async def cb_excel_all(callback: CallbackQuery, db: Database, tutor: Tutor, bot: Bot) -> None:
    await callback.answer()
    await send_tutor_workbook(bot, callback.from_user.id, db, tutor)


async def send_full_tutor_workbook(bot: Bot, chat_id: int, db: Database, tutor: Tutor) -> bool:
    """Send the tutor's full-survey workbook (``Barchasi`` + one sheet per group)."""
    profiles = await db.list_full_profiles(tutor_id=tutor.id)
    if not profiles:
        await bot.send_message(chat_id, texts.NO_DATA)
        return False
    groups = await db.list_groups(tutor.id)
    data = await asyncio.to_thread(build_full_tutor_workbook, groups, profiles)
    await _send_document(
        bot, chat_id, data, _filename(tutor, "toliq_anketa"), f"{tutor.name} — to'liq anketa", len(profiles)
    )
    return True


async def cb_excel_full_pick(callback: CallbackQuery, db: Database, tutor: Tutor, bot: Bot) -> None:
    await callback.answer()
    text, kb = await _group_list(
        db, tutor, action=TUT_EXCEL_FULL_GROUP, title=texts.EXCEL_FULL_PICK_GROUP, back_action=TUT_EXCEL_MENU
    )
    await edit_or_send(callback, bot, text, kb)


async def cb_excel_full_group(
    callback: CallbackQuery, callback_data: TutorCb, db: Database, tutor: Tutor, bot: Bot
) -> None:
    group = await _own_group(callback, db, tutor, callback_data.group_id)
    if group is None:
        return
    await callback.answer()
    profiles = await db.list_full_profiles(tutor_id=tutor.id, group_id=group.id)
    if not profiles:
        await bot.send_message(callback.from_user.id, texts.NO_DATA)
        return
    data = await asyncio.to_thread(build_full_group_workbook, group, profiles)
    await _send_document(
        bot,
        callback.from_user.id,
        data,
        _filename(tutor, f"{group.name}_toliq"),
        f"{group.name} — to'liq anketa",
        len(profiles),
    )


async def cb_excel_full_all(callback: CallbackQuery, db: Database, tutor: Tutor, bot: Bot) -> None:
    await callback.answer()
    await send_full_tutor_workbook(bot, callback.from_user.id, db, tutor)


# ------------------------------------------------------------ tutor's phone


async def _phone_prompt(tutor: Tutor) -> str:
    return texts.TUTOR_PHONE_CURRENT.format(phone=hesc(tutor.phone)) if tutor.phone else texts.TUTOR_ASK_PHONE


async def cb_phone(callback: CallbackQuery, state: FSMContext, tutor: Tutor, bot: Bot) -> None:
    await state.clear()
    await state.set_state(TutorPhone.phone)
    await callback.answer()
    await bot.send_message(callback.from_user.id, await _phone_prompt(tutor), reply_markup=phone_kb())


async def cmd_phone(message: Message, state: FSMContext, tutor: Tutor) -> None:
    await state.clear()
    await state.set_state(TutorPhone.phone)
    await message.answer(await _phone_prompt(tutor), reply_markup=phone_kb())


async def save_phone(
    message: Message, state: FSMContext, db: Database, settings: Settings, tutor: Tutor, bot: Bot
) -> None:
    """The tutor's own number: shared as a contact or typed as ``+998XXXXXXXXX``."""
    raw = message.contact.phone_number if message.contact is not None else message.text
    phone = normalize_phone(raw)
    if phone is None:
        await message.answer(texts.REG_PHONE_INVALID, reply_markup=phone_kb())
        return
    await db.update_tutor_phone(tutor.id, phone)
    await state.clear()
    log.info("Tutor %s set their phone number", tutor.id)
    is_admin, is_tutor = await get_roles(db, settings, message.chat.id)
    await message.answer(
        texts.TUTOR_PHONE_SAVED.format(phone=hesc(phone)), reply_markup=main_menu_kb(is_admin, is_tutor)
    )
    await message.answer(_panel_text(tutor), reply_markup=tutor_panel_kb())


# ------------------------------------------------------------- registration


def create_router() -> Router:
    """Build the tutor router. A fresh instance is returned on every call (routers cannot be shared)."""
    router = Router(name="tutor")
    router.message.filter(IsTutor())
    router.callback_query.filter(IsTutor())

    msg = router.message
    cb = router.callback_query

    # Slash commands and the panel button come first so they pre-empt every tutor FSM step.
    msg.register(cmd_tutor, Command("tutor"))
    msg.register(cmd_tutor, F.text == texts.BTN_TUTOR_PANEL)
    msg.register(cmd_groups, Command("groups"))
    msg.register(cmd_add_group, Command("add_group"))
    msg.register(cmd_edit_group, Command("edit_group"))
    msg.register(cmd_delete_group, Command("delete_group"))
    msg.register(cmd_excel, Command("excel"))
    msg.register(cmd_students, Command("students"))
    msg.register(cmd_phone, Command("phone"))

    cb.register(cb_panel, TutorCb.filter(F.action == TUT_PANEL))
    cb.register(cb_groups, TutorCb.filter(F.action == TUT_GROUPS))
    cb.register(cb_view, TutorCb.filter(F.action == TUT_VIEW))
    cb.register(cb_students, TutorCb.filter(F.action == TUT_STUDENTS))

    # FSM text steps only take free text: other routers' commands/buttons must fall through to them.
    free_text = IsFreeText()
    cb.register(cb_add_group, TutorCb.filter(F.action == TUT_ADD))
    msg.register(add_group_name, TutorGroupAdd.name, free_text)

    cb.register(cb_rename, TutorCb.filter(F.action == TUT_RENAME))
    msg.register(rename_group_name, TutorGroupEdit.name, free_text)

    cb.register(cb_delete, TutorCb.filter(F.action == TUT_DELETE))
    cb.register(cb_confirm_delete, TutorCb.filter(F.action == TUT_CONFIRM_DELETE))

    cb.register(cb_excel_menu, TutorCb.filter(F.action == TUT_EXCEL_MENU))
    cb.register(cb_excel_pick_group, TutorCb.filter(F.action == TUT_EXCEL_PICK_GROUP))
    cb.register(cb_excel_group, TutorCb.filter(F.action == TUT_EXCEL_GROUP))
    cb.register(cb_excel_residence, TutorCb.filter(F.action == TUT_EXCEL_RES))
    cb.register(cb_excel_residence_pick, TutorCb.filter(F.action == TUT_EXCEL_RES_PICK))
    cb.register(cb_excel_all, TutorCb.filter(F.action == TUT_EXCEL_ALL))
    cb.register(cb_excel_full_pick, TutorCb.filter(F.action == TUT_EXCEL_FULL_PICK))
    cb.register(cb_excel_full_group, TutorCb.filter(F.action == TUT_EXCEL_FULL_GROUP))
    cb.register(cb_excel_full_all, TutorCb.filter(F.action == TUT_EXCEL_FULL_ALL))

    cb.register(cb_phone, TutorCb.filter(F.action == TUT_PHONE))
    msg.register(save_phone, TutorPhone.phone, F.contact)
    msg.register(save_phone, TutorPhone.phone, free_text)
    return router
