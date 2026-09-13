"""Student registration FSM (§8) and registration notifications (§9)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, User

from .. import texts
from ..config import Settings
from ..db import Database
from ..filters import IsFreeText, get_roles
from ..keyboards import (
    EDT_DONE,
    EDT_FIELD,
    EDT_OPEN,
    EDT_REREGISTER,
    EDT_RESIDENCE,
    EDT_TUTOR_GROUP,
    REG_BACK,
    REG_CANCEL,
    REG_CONFIRM,
    REG_GROUP,
    REG_RESTART,
    REG_TUTOR,
    EditCb,
    RegCb,
    cancel_kb,
    main_menu_kb,
    phone_kb,
    reg_confirm_kb,
    reg_group_list_kb,
    reg_tutor_list_kb,
    residence_kb,
    student_edit_field_kb,
    student_home_kb,
)
from ..models import RESIDENCE_VALUES, Group, Student, Tutor
from ..states import Registration, StudentEdit
from ..utils import (
    clean_text,
    edit_or_send,
    hesc,
    is_valid_length,
    is_valid_name,
    is_valid_phone,
    normalize_phone,
    remove_inline_keyboard,
)

log = logging.getLogger(__name__)

DIRECTION_MIN, DIRECTION_MAX = 2, 150
ADDRESS_MIN, ADDRESS_MAX = 5, 300
_REQUIRED_KEYS = (
    "tutor_id",
    "group_id",
    "phone",
    "full_name",
    "direction",
    "residence",
    "address",
    "father_name",
    "father_phone",
    "mother_name",
    "mother_phone",
)


# ------------------------------------------------------------------ helpers


async def start_registration(bot: Bot, chat_id: int, state: FSMContext, db: Database) -> None:
    """Reset the FSM and show the tutor picker (or explain that no tutors exist yet)."""
    await state.clear()
    tutors = await db.list_tutors()
    if not tutors:
        await bot.send_message(chat_id, texts.REG_NO_TUTORS)
        return
    await state.set_state(Registration.choose_tutor)
    await bot.send_message(chat_id, texts.REG_CHOOSE_TUTOR, reply_markup=reg_tutor_list_kb(tutors))


async def _finish_markup(db: Database, settings: Settings, user_id: int) -> Any:
    is_admin, is_tutor = await get_roles(db, settings, user_id)
    if is_admin or is_tutor:
        return main_menu_kb(is_admin, is_tutor)
    return ReplyKeyboardRemove()


def _student_from_data(data: dict[str, Any], user: User, tutor: Tutor, group: Group) -> Student:
    """Build a transient Student (id=0, no timestamps) from FSM data for the preview card."""
    return Student(
        id=0,
        telegram_id=user.id,
        username=user.username,
        tutor_id=tutor.id,
        group_id=group.id,
        full_name=data["full_name"],
        phone=data["phone"],
        direction=data["direction"],
        residence=data["residence"],
        address=data["address"],
        father_name=data["father_name"],
        father_phone=data["father_phone"],
        mother_name=data["mother_name"],
        mother_phone=data["mother_phone"],
        created_at="",
        updated_at="",
        tutor_name=tutor.name,
        group_name=group.name,
    )


async def _resolve_selection(db: Database, data: dict[str, Any]) -> tuple[Tutor, Group] | None:
    """Return the chosen (tutor, group) if both still exist and belong together."""
    tutor = await db.get_tutor(int(data.get("tutor_id") or 0))
    group = await db.get_group(int(data.get("group_id") or 0))
    if tutor is None or group is None or group.tutor_id != tutor.id:
        return None
    return tutor, group


async def notify_registration(
    bot: Bot, settings: Settings, tutor: Tutor, student: Student, is_update: bool
) -> list[int]:
    """Send the student card to the tutor and every superadmin exactly once each.

    Delivery failures are logged and never propagated. Returns the chat IDs that were attempted.
    """
    title = texts.CARD_TITLE_UPDATE if is_update else texts.CARD_TITLE_NEW
    text = texts.student_card(title, student)
    recipients = sorted({tutor.telegram_id, *settings.superadmin_ids})
    for chat_id in recipients:
        try:
            await bot.send_message(chat_id, text)
        except TelegramAPIError as exc:
            log.warning("Could not deliver registration notification to %s: %s", chat_id, exc)
    return recipients


async def _show_preview(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    selection = await _resolve_selection(db, data)
    if selection is None or message.from_user is None:
        await message.answer(texts.REG_GROUP_NOT_FOUND, reply_markup=ReplyKeyboardRemove())
        await start_registration(bot, message.chat.id, state, db)
        return
    tutor, group = selection
    student = _student_from_data(data, message.from_user, tutor, group)
    await state.set_state(Registration.confirm)
    await message.answer(texts.student_card(texts.REG_PREVIEW_TITLE, student), reply_markup=reg_confirm_kb())


# ------------------------------------------------------------- entry points


async def register_button(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    if message.from_user is not None and await show_student_home(bot, message.from_user.id, state, db):
        return
    await start_registration(bot, message.chat.id, state, db)


async def reg_cancel(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    await remove_inline_keyboard(callback)
    is_admin, is_tutor = await get_roles(db, settings, callback.from_user.id)
    if is_admin or is_tutor:
        await bot.send_message(callback.from_user.id, texts.CANCELLED, reply_markup=main_menu_kb(is_admin, is_tutor))
    else:
        await bot.send_message(callback.from_user.id, texts.CANCELLED_STUDENT, reply_markup=ReplyKeyboardRemove())


async def reg_restart(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    await callback.answer()
    await remove_inline_keyboard(callback)
    await bot.send_message(callback.from_user.id, texts.REG_RESTARTED, reply_markup=ReplyKeyboardRemove())
    await start_registration(bot, callback.from_user.id, state, db)


# ------------------------------------------------------- tutor / group pick


async def reg_choose_tutor(
    callback: CallbackQuery, callback_data: RegCb, state: FSMContext, db: Database, bot: Bot
) -> None:
    tutor = await db.get_tutor(callback_data.id)
    if tutor is None:
        await callback.answer(texts.REG_TUTOR_NOT_FOUND, show_alert=True)
        await remove_inline_keyboard(callback)
        await start_registration(bot, callback.from_user.id, state, db)
        return
    await state.update_data(tutor_id=tutor.id)
    await state.set_state(Registration.choose_group)
    await callback.answer()
    groups = await db.list_groups(tutor.id)
    text = texts.REG_CHOOSE_GROUP if groups else texts.REG_TUTOR_NO_GROUPS
    await edit_or_send(callback, bot, text, reg_group_list_kb(groups))


async def reg_back_to_tutors(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    await callback.answer()
    tutors = await db.list_tutors()
    if not tutors:
        await state.clear()
        await edit_or_send(callback, bot, texts.REG_NO_TUTORS)
        return
    await state.set_state(Registration.choose_tutor)
    await edit_or_send(callback, bot, texts.REG_CHOOSE_TUTOR, reg_tutor_list_kb(tutors))


async def reg_choose_group(
    callback: CallbackQuery, callback_data: RegCb, state: FSMContext, db: Database, bot: Bot
) -> None:
    data = await state.get_data()
    group = await db.get_group(callback_data.id)
    tutor = await db.get_tutor(int(data.get("tutor_id") or 0))
    if group is None or tutor is None or group.tutor_id != tutor.id:
        await callback.answer(texts.REG_GROUP_NOT_FOUND, show_alert=True)
        await remove_inline_keyboard(callback)
        await start_registration(bot, callback.from_user.id, state, db)
        return
    await state.update_data(group_id=group.id)
    await state.set_state(Registration.phone)
    await callback.answer()
    await edit_or_send(callback, bot, f"👨‍🏫 Tyutor: {hesc(tutor.name)}\n👥 Guruh: {hesc(group.name)}")
    await bot.send_message(callback.from_user.id, texts.REG_ASK_PHONE, reply_markup=phone_kb())


async def reg_expect_buttons(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)


# ------------------------------------------------------------- text steps


async def reg_phone(message: Message, state: FSMContext) -> None:
    phone: str | None = None
    if message.contact is not None:
        if message.from_user is None or message.contact.user_id != message.from_user.id:
            await message.answer(texts.REG_CONTACT_NOT_OWN, reply_markup=phone_kb())
            return
        phone = normalize_phone(message.contact.phone_number)
    elif message.text and is_valid_phone(message.text):
        phone = message.text.strip()
    if phone is None:
        await message.answer(texts.REG_PHONE_INVALID, reply_markup=phone_kb())
        return
    await state.update_data(phone=phone)
    await state.set_state(Registration.full_name)
    await message.answer(texts.REG_ASK_FULL_NAME, reply_markup=cancel_kb())


async def reg_full_name(message: Message, state: FSMContext) -> None:
    if not is_valid_name(message.text):
        await message.answer(texts.REG_NAME_INVALID, reply_markup=cancel_kb())
        return
    await state.update_data(full_name=clean_text(message.text))
    await state.set_state(Registration.direction)
    await message.answer(texts.REG_ASK_DIRECTION, reply_markup=cancel_kb())


async def reg_direction(message: Message, state: FSMContext) -> None:
    if not is_valid_length(message.text, DIRECTION_MIN, DIRECTION_MAX):
        await message.answer(texts.REG_DIRECTION_INVALID, reply_markup=cancel_kb())
        return
    await state.update_data(direction=clean_text(message.text))
    await state.set_state(Registration.residence)
    await message.answer(texts.REG_ASK_RESIDENCE, reply_markup=residence_kb())


async def reg_residence(message: Message, state: FSMContext) -> None:
    residence = texts.parse_residence(message.text)
    if residence is None:
        await message.answer(texts.REG_RESIDENCE_INVALID, reply_markup=residence_kb())
        return
    if residence == "ttj":
        await state.update_data(residence="ttj", address="TTJ")
        await state.set_state(Registration.father_name)
        await message.answer(texts.REG_ASK_FATHER_NAME, reply_markup=cancel_kb())
        return
    await state.update_data(residence=residence)
    await state.set_state(Registration.address)
    await message.answer(texts.REG_ASK_ADDRESS, reply_markup=cancel_kb())


async def reg_address(message: Message, state: FSMContext) -> None:
    if not is_valid_length(message.text, ADDRESS_MIN, ADDRESS_MAX):
        await message.answer(texts.REG_ADDRESS_INVALID, reply_markup=cancel_kb())
        return
    await state.update_data(address=clean_text(message.text))
    await state.set_state(Registration.father_name)
    await message.answer(texts.REG_ASK_FATHER_NAME, reply_markup=cancel_kb())


async def reg_father_name(message: Message, state: FSMContext) -> None:
    if not is_valid_name(message.text):
        await message.answer(texts.REG_NAME_INVALID, reply_markup=cancel_kb())
        return
    await state.update_data(father_name=clean_text(message.text))
    await state.set_state(Registration.father_phone)
    await message.answer(texts.REG_ASK_FATHER_PHONE, reply_markup=cancel_kb())


async def reg_father_phone(message: Message, state: FSMContext) -> None:
    if not is_valid_phone(message.text):
        await message.answer(texts.REG_PARENT_PHONE_INVALID, reply_markup=cancel_kb())
        return
    await state.update_data(father_phone=(message.text or "").strip())
    await state.set_state(Registration.mother_name)
    await message.answer(texts.REG_ASK_MOTHER_NAME, reply_markup=cancel_kb())


async def reg_mother_name(message: Message, state: FSMContext) -> None:
    if not is_valid_name(message.text):
        await message.answer(texts.REG_NAME_INVALID, reply_markup=cancel_kb())
        return
    await state.update_data(mother_name=clean_text(message.text))
    await state.set_state(Registration.mother_phone)
    await message.answer(texts.REG_ASK_MOTHER_PHONE, reply_markup=cancel_kb())


async def reg_mother_phone(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    if not is_valid_phone(message.text):
        await message.answer(texts.REG_PARENT_PHONE_INVALID, reply_markup=cancel_kb())
        return
    await state.update_data(mother_phone=(message.text or "").strip())
    await _show_preview(message, state, db, bot)


# ---------------------------------------------------------------- confirm


async def reg_confirm(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    user = callback.from_user
    # Single-shot guard. ``StateFilter`` compares the state captured when the update entered the
    # dispatcher, so two concurrently handled taps both pass it; re-check the live state here and leave
    # ``confirm`` before the first DB await. MemoryStorage never yields, so check-and-leave is atomic
    # and the second tap is answered as stale instead of saving and notifying everyone twice.
    if await state.get_state() != Registration.confirm.state:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    data = await state.get_data()
    await state.set_state(None)
    selection = await _resolve_selection(db, data)
    if selection is None or any(key not in data for key in _REQUIRED_KEYS):
        await callback.answer(texts.REG_GROUP_NOT_FOUND, show_alert=True)
        await remove_inline_keyboard(callback)
        await start_registration(bot, user.id, state, db)
        return
    tutor, group = selection
    try:
        student, is_update = await db.upsert_student(
            telegram_id=user.id,
            username=user.username,
            tutor_id=tutor.id,
            group_id=group.id,
            full_name=data["full_name"],
            phone=data["phone"],
            direction=data["direction"],
            residence=data["residence"],
            address=data["address"],
            father_name=data["father_name"],
            father_phone=data["father_phone"],
            mother_name=data["mother_name"],
            mother_phone=data["mother_phone"],
        )
    except Exception:
        await state.set_state(Registration.confirm)  # nothing was saved: let the user tap ✅ again
        raise
    await state.clear()
    await callback.answer()
    await remove_inline_keyboard(callback)
    await bot.send_message(user.id, texts.REG_SAVED, reply_markup=await _finish_markup(db, settings, user.id))
    log.info(
        "Student %s %s (tutor=%s, group=%s)", user.id, "updated" if is_update else "registered", tutor.id, group.id
    )
    await notify_registration(bot, settings, tutor, student, is_update)


# ------------------------------------------------- editing a saved registration


def _strip(text: str | None) -> str:
    return (text or "").strip()


@dataclass(frozen=True, slots=True)
class _EditField:
    """One free-text student column: what to ask, what to say when it is wrong, how to check it."""

    prompt: str
    invalid: str
    validate: Callable[[str | None], bool]
    clean: Callable[[str | None], str]


EDIT_FIELDS: dict[str, _EditField] = {
    "full_name": _EditField(texts.REG_ASK_FULL_NAME, texts.REG_NAME_INVALID, is_valid_name, clean_text),
    "phone": _EditField(texts.REG_ASK_PHONE, texts.REG_PHONE_INVALID, is_valid_phone, _strip),
    "direction": _EditField(
        texts.REG_ASK_DIRECTION,
        texts.REG_DIRECTION_INVALID,
        lambda t: is_valid_length(t, DIRECTION_MIN, DIRECTION_MAX),
        clean_text,
    ),
    "address": _EditField(
        texts.REG_ASK_ADDRESS,
        texts.REG_ADDRESS_INVALID,
        lambda t: is_valid_length(t, ADDRESS_MIN, ADDRESS_MAX),
        clean_text,
    ),
    "father_name": _EditField(texts.REG_ASK_FATHER_NAME, texts.REG_NAME_INVALID, is_valid_name, clean_text),
    "father_phone": _EditField(texts.REG_ASK_FATHER_PHONE, texts.REG_PARENT_PHONE_INVALID, is_valid_phone, _strip),
    "mother_name": _EditField(texts.REG_ASK_MOTHER_NAME, texts.REG_NAME_INVALID, is_valid_name, clean_text),
    "mother_phone": _EditField(texts.REG_ASK_MOTHER_PHONE, texts.REG_PARENT_PHONE_INVALID, is_valid_phone, _strip),
}
"""Columns the student may retype, keyed by their ``students`` column name. Residence and the
tutor/group pair are not here: they are picked from keyboards, not typed."""


def _prompt_kb(field_name: str) -> Any:
    """The phone step offers the contact button; every other field just needs a way out."""
    return phone_kb() if field_name == "phone" else cancel_kb()


async def show_student_home(bot: Bot, user_id: int, state: FSMContext, db: Database) -> bool:
    """Show a registered student their own card plus the self-service buttons.

    Returns ``False`` without sending anything when nothing is saved for this user yet, so the
    caller can decide how to open the registration flow instead.
    """
    student = await db.get_student_by_telegram_id(user_id)
    if student is None:
        return False
    await state.clear()
    card = texts.student_card(texts.STUDENT_HOME_TITLE, student)
    can_reregister = await db.is_test_user(user_id)
    await bot.send_message(
        user_id,
        f"{card}\n\n{texts.STUDENT_HOME_HINT}",
        reply_markup=student_home_kb(can_reregister),
    )
    return True


async def _registration_gone(bot: Bot, user_id: int, state: FSMContext, db: Database) -> None:
    """The row vanished mid-edit (the tutor or group was deleted and cascaded): start over."""
    await state.clear()
    await bot.send_message(user_id, texts.EDIT_GONE, reply_markup=ReplyKeyboardRemove())
    await start_registration(bot, user_id, state, db)


async def _show_edit_menu(bot: Bot, user_id: int, state: FSMContext, db: Database) -> None:
    """(Re)draw the field picker under the student's current card."""
    student = await db.get_student_by_telegram_id(user_id)
    if student is None:
        await _registration_gone(bot, user_id, state, db)
        return
    await state.set_state(StudentEdit.menu)
    card = texts.student_card(texts.STUDENT_HOME_TITLE, student)
    await bot.send_message(
        user_id,
        f"{card}\n\n{texts.EDIT_MENU}",
        reply_markup=student_edit_field_kb(student.residence),
    )


async def _apply_edit(
    bot: Bot, user_id: int, state: FSMContext, db: Database, settings: Settings, **fields: Any
) -> None:
    """Persist one edit, remember that something changed and return to the field picker.

    The confirmation carries the user's normal reply keyboard because the step that was just
    answered replaced it with a cancel/contact keyboard.
    """
    student = await db.update_student(user_id, **fields)
    if student is None:
        await _registration_gone(bot, user_id, state, db)
        return
    await state.update_data(changed=True)
    await bot.send_message(user_id, texts.EDIT_SAVED, reply_markup=await _finish_markup(db, settings, user_id))
    await _show_edit_menu(bot, user_id, state, db)


# ------------------------------------------------------ edit: entry points


async def cmd_mydata(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    if message.from_user is None:
        return
    if await show_student_home(bot, message.from_user.id, state, db):
        return
    await message.answer(texts.STUDENT_NOT_REGISTERED, reply_markup=ReplyKeyboardRemove())
    await start_registration(bot, message.chat.id, state, db)


async def edit_open(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    await callback.answer()
    await remove_inline_keyboard(callback)
    await _show_edit_menu(bot, callback.from_user.id, state, db)


async def edit_reregister(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    """Run the whole flow again. Only testers may: for anyone else it would overwrite a real record."""
    user_id = callback.from_user.id
    if await db.get_student_by_telegram_id(user_id) is not None and not await db.is_test_user(user_id):
        await callback.answer(texts.REREGISTER_BLOCKED, show_alert=True)
        return
    await callback.answer()
    await remove_inline_keyboard(callback)
    await start_registration(bot, user_id, state, db)


async def edit_done(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    """Leave the edit menu and, if anything was saved, send the fresh card to tutor + superadmins."""
    user_id = callback.from_user.id
    data = await state.get_data()
    changed = bool(data.get("changed"))
    await state.clear()
    await callback.answer()
    await remove_inline_keyboard(callback)
    student = await db.get_student_by_telegram_id(user_id)
    if student is None:
        await _registration_gone(bot, user_id, state, db)
        return
    await bot.send_message(
        user_id,
        texts.EDIT_DONE if changed else texts.EDIT_NOTHING_CHANGED,
        reply_markup=await _finish_markup(db, settings, user_id),
    )
    if not changed:
        return
    tutor = await db.get_tutor(student.tutor_id)
    if tutor is not None:
        log.info("Student %s edited their data (tutor=%s, group=%s)", user_id, student.tutor_id, student.group_id)
        await notify_registration(bot, settings, tutor, student, True)


# ---------------------------------------------------------- edit: one field


async def edit_pick_field(
    callback: CallbackQuery, callback_data: EditCb, state: FSMContext, db: Database, bot: Bot
) -> None:
    field = EDIT_FIELDS.get(callback_data.field)
    if field is None:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    await callback.answer()
    await remove_inline_keyboard(callback)
    await state.update_data(field=callback_data.field)
    await state.set_state(StudentEdit.value)
    await bot.send_message(callback.from_user.id, field.prompt, reply_markup=_prompt_kb(callback_data.field))


async def edit_value(
    message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    data = await state.get_data()
    name = str(data.get("field") or "")
    field = EDIT_FIELDS.get(name)
    if field is None or message.from_user is None:  # FSM data lost (e.g. a restart): redraw the menu
        await _show_edit_menu(bot, message.chat.id, state, db)
        return
    value: str | None = None
    if name == "phone" and message.contact is not None:
        if message.contact.user_id != message.from_user.id:
            await message.answer(texts.REG_CONTACT_NOT_OWN, reply_markup=phone_kb())
            return
        value = normalize_phone(message.contact.phone_number)
    elif field.validate(message.text):
        value = field.clean(message.text)
    if value is None:
        await message.answer(field.invalid, reply_markup=_prompt_kb(name))
        return
    await _apply_edit(bot, message.from_user.id, state, db, settings, **{name: value})


# ----------------------------------------------------------- edit: residence


async def edit_pick_residence(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await remove_inline_keyboard(callback)
    await state.set_state(StudentEdit.residence)
    await bot.send_message(callback.from_user.id, texts.REG_ASK_RESIDENCE, reply_markup=residence_kb())


async def edit_residence(
    message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    residence = texts.parse_residence(message.text)
    if residence is None:
        await message.answer(texts.REG_RESIDENCE_INVALID, reply_markup=residence_kb())
        return
    if message.from_user is None:
        return
    if residence == "ttj":  # same rule as registration: the dormitory needs no street address
        await _apply_edit(bot, message.from_user.id, state, db, settings, residence="ttj", address="TTJ")
        return
    await state.update_data(residence=residence)
    await state.set_state(StudentEdit.address)
    await message.answer(texts.REG_ASK_ADDRESS, reply_markup=cancel_kb())


async def edit_residence_address(
    message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    """Address typed right after a non-TTJ residence: both columns are saved together."""
    if not is_valid_length(message.text, ADDRESS_MIN, ADDRESS_MAX):
        await message.answer(texts.REG_ADDRESS_INVALID, reply_markup=cancel_kb())
        return
    data = await state.get_data()
    residence = str(data.get("residence") or "")
    if residence not in RESIDENCE_VALUES or message.from_user is None:
        await _show_edit_menu(bot, message.chat.id, state, db)
        return
    await _apply_edit(
        bot, message.from_user.id, state, db, settings, residence=residence, address=clean_text(message.text)
    )


# -------------------------------------------------------- edit: tutor/group


async def edit_pick_tutor_group(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    tutors = await db.list_tutors()
    if not tutors:
        await callback.answer(texts.REG_NO_TUTORS, show_alert=True)
        return
    await callback.answer()
    await state.set_state(StudentEdit.choose_tutor)
    await edit_or_send(callback, bot, texts.EDIT_ASK_TUTOR, reg_tutor_list_kb(tutors))


async def edit_choose_tutor(
    callback: CallbackQuery, callback_data: RegCb, state: FSMContext, db: Database, bot: Bot
) -> None:
    tutor = await db.get_tutor(callback_data.id)
    if tutor is None:
        await callback.answer(texts.REG_TUTOR_NOT_FOUND, show_alert=True)
        await remove_inline_keyboard(callback)
        await _show_edit_menu(bot, callback.from_user.id, state, db)
        return
    await state.update_data(tutor_id=tutor.id)
    await state.set_state(StudentEdit.choose_group)
    await callback.answer()
    groups = await db.list_groups(tutor.id)
    text = texts.EDIT_ASK_GROUP if groups else texts.REG_TUTOR_NO_GROUPS
    await edit_or_send(callback, bot, text, reg_group_list_kb(groups))


async def edit_back_to_tutors(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    tutors = await db.list_tutors()
    if not tutors:
        await callback.answer(texts.REG_NO_TUTORS, show_alert=True)
        return
    await callback.answer()
    await state.set_state(StudentEdit.choose_tutor)
    await edit_or_send(callback, bot, texts.EDIT_ASK_TUTOR, reg_tutor_list_kb(tutors))


async def edit_choose_group(
    callback: CallbackQuery,
    callback_data: RegCb,
    state: FSMContext,
    db: Database,
    settings: Settings,
    bot: Bot,
) -> None:
    data = await state.get_data()
    group = await db.get_group(callback_data.id)
    tutor = await db.get_tutor(int(data.get("tutor_id") or 0))
    if group is None or tutor is None or group.tutor_id != tutor.id:
        await callback.answer(texts.REG_GROUP_NOT_FOUND, show_alert=True)
        await remove_inline_keyboard(callback)
        await _show_edit_menu(bot, callback.from_user.id, state, db)
        return
    await callback.answer()
    await remove_inline_keyboard(callback)
    await _apply_edit(bot, callback.from_user.id, state, db, settings, tutor_id=tutor.id, group_id=group.id)


# ------------------------------------------------------------- registration


def create_router() -> Router:
    """Build the student registration router. A fresh instance is returned on every call."""
    router = Router(name="student")
    msg = router.message
    cb = router.callback_query
    free_text = IsFreeText()

    msg.register(register_button, F.text == texts.BTN_REGISTER)
    msg.register(cmd_mydata, Command("mydata"))
    cb.register(reg_cancel, RegCb.filter(F.action == REG_CANCEL))
    cb.register(reg_restart, StateFilter(Registration), RegCb.filter(F.action == REG_RESTART))

    cb.register(reg_choose_tutor, Registration.choose_tutor, RegCb.filter(F.action == REG_TUTOR))
    cb.register(reg_back_to_tutors, Registration.choose_group, RegCb.filter(F.action == REG_BACK))
    cb.register(reg_choose_group, Registration.choose_group, RegCb.filter(F.action == REG_GROUP))
    msg.register(
        reg_expect_buttons,
        StateFilter(Registration.choose_tutor, Registration.choose_group, Registration.confirm),
    )

    msg.register(reg_phone, Registration.phone)
    msg.register(reg_full_name, Registration.full_name)
    msg.register(reg_direction, Registration.direction)
    msg.register(reg_residence, Registration.residence)
    msg.register(reg_address, Registration.address)
    msg.register(reg_father_name, Registration.father_name)
    msg.register(reg_father_phone, Registration.father_phone)
    msg.register(reg_mother_name, Registration.mother_name)
    msg.register(reg_mother_phone, Registration.mother_phone)

    cb.register(reg_confirm, Registration.confirm, RegCb.filter(F.action == REG_CONFIRM))

    # Self-service editing. The tutor/group pickers reuse the registration keyboards (and therefore
    # ``RegCb``); the state filter is what keeps the two flows apart.
    cb.register(edit_open, EditCb.filter(F.action == EDT_OPEN))
    cb.register(edit_reregister, EditCb.filter(F.action == EDT_REREGISTER))
    cb.register(edit_pick_field, StudentEdit.menu, EditCb.filter(F.action == EDT_FIELD))
    cb.register(edit_pick_residence, StudentEdit.menu, EditCb.filter(F.action == EDT_RESIDENCE))
    cb.register(edit_pick_tutor_group, StudentEdit.menu, EditCb.filter(F.action == EDT_TUTOR_GROUP))
    cb.register(edit_done, StudentEdit.menu, EditCb.filter(F.action == EDT_DONE))
    cb.register(edit_choose_tutor, StudentEdit.choose_tutor, RegCb.filter(F.action == REG_TUTOR))
    cb.register(edit_back_to_tutors, StudentEdit.choose_group, RegCb.filter(F.action == REG_BACK))
    cb.register(edit_choose_group, StudentEdit.choose_group, RegCb.filter(F.action == REG_GROUP))

    msg.register(edit_value, StudentEdit.value, free_text)
    msg.register(edit_residence, StudentEdit.residence)
    msg.register(edit_residence_address, StudentEdit.address, free_text)
    msg.register(
        reg_expect_buttons,
        StateFilter(StudentEdit.menu, StudentEdit.choose_tutor, StudentEdit.choose_group),
    )
    return router
