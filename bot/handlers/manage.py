"""Student management shared by the tutor and superadmin panels: browse a group's students, write to
one, or delete one (and optionally write to them afterwards).

Every screen here is addressed by ``StuCb``. The router-level ``IsStaff`` filter admits superadmins
and tutors and injects ``is_admin`` / ``tutor``; *which* students the sender may touch is decided per
handler by :meth:`Actor.may_manage` -- a superadmin anyone, a tutor only students of their own
groups. ``StuCb.via`` only asks for tutor-style or admin-style navigation; the mode actually used
comes from :meth:`Actor.mode_for`, so a tutor cannot forge admin mode and a superadmin looking at
someone else's student always gets admin navigation. A message is signed by the student's own tutor
when that is who sends it, and by "the administration" otherwise.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from .. import texts
from ..config import Settings
from ..db import Database
from ..filters import IsFreeText, IsStaff, get_roles
from ..keyboards import (
    STU_BYE_NO,
    STU_BYE_YES,
    STU_CONFIRM_DELETE,
    STU_DELETE,
    STU_LIST,
    STU_MESSAGE,
    STU_SURVEYS,
    STU_VIEW,
    VIA_ADMIN,
    VIA_TUTOR,
    StuCb,
    cancel_kb,
    main_menu_kb,
    group_surveys_kb,
    student_confirm_delete_kb,
    student_farewell_kb,
    student_list_kb,
    student_manage_kb,
)
from ..models import SURVEY_BASIC, SURVEY_FULL, SURVEY_VALUES, FullProfile, Group, Student, Tutor
from ..states import StudentManage
from ..utils import edit_or_send, hesc, remove_inline_keyboard

log = logging.getLogger(__name__)

MESSAGE_MAX_LEN = 3500  # Telegram caps a message at 4096 characters; the rest is our header

# outcomes of one delivery attempt
SENT = "sent"
BLOCKED = "blocked"  # the student blocked or deleted the bot
FAILED = "failed"  # any other Telegram error


# ------------------------------------------------------------------ actor


@dataclass(frozen=True, slots=True)
class Actor:
    """The sender's roles plus the navigation style their button asked for (already normalised)."""

    user_id: int
    is_admin: bool
    tutor: Tutor | None
    via: str

    def owns(self, owner_tutor_id: int) -> bool:
        return self.tutor is not None and self.tutor.id == owner_tutor_id

    def may_manage(self, owner_tutor_id: int) -> bool:
        return self.is_admin or self.owns(owner_tutor_id)

    def mode_for(self, owner_tutor_id: int) -> str:
        """Tutor-style screens only for one's own student reached outside the admin panel; a
        superadmin on anyone else's student gets admin-style screens whatever the button said."""
        return VIA_TUTOR if self.owns(owner_tutor_id) and self.via == VIA_TUTOR else VIA_ADMIN

    def sender_line(self, owner_tutor_id: int) -> str:
        """The student's own tutor signs by name; anyone else allowed here is the administration."""
        if self.owns(owner_tutor_id) and self.tutor is not None:
            return texts.MESSAGE_SENDER_TUTOR.format(name=hesc(self.tutor.name))
        return texts.MESSAGE_SENDER_ADMIN


def _actor(user_id: int, is_admin: bool, tutor: Tutor | None, via: str) -> Actor:
    """Only a superadmin may ask for admin mode; anything else (including garbage) means tutor mode."""
    requested = VIA_ADMIN if via == VIA_ADMIN and is_admin else VIA_TUTOR
    return Actor(user_id=user_id, is_admin=is_admin, tutor=tutor, via=requested)


def _role(mode: str) -> str:
    return "Superadmin" if mode == VIA_ADMIN else "Tutor"


async def _menu(db: Database, settings: Settings, user_id: int) -> ReplyKeyboardMarkup:
    is_admin, is_tutor = await get_roles(db, settings, user_id)
    return main_menu_kb(is_admin, is_tutor)


def _sender_id(message: Message) -> int:
    return message.from_user.id if message.from_user is not None else message.chat.id


# ------------------------------------------------------------------- rows


@dataclass(frozen=True, slots=True)
class Row:
    """One student as the management screens see them, whichever questionnaire they come from."""

    survey: str
    id: int
    telegram_id: int
    full_name: str
    tutor_id: int
    group_id: int
    group_name: str
    card: str


def _basic_row(student: Student) -> Row:
    return Row(
        survey=SURVEY_BASIC,
        id=student.id,
        telegram_id=student.telegram_id,
        full_name=student.full_name,
        tutor_id=student.tutor_id,
        group_id=student.group_id,
        group_name=student.group_name,
        card=texts.student_card(texts.STUDENT_CARD_TITLE, student),
    )


def _full_row(profile: FullProfile) -> Row:
    return Row(
        survey=SURVEY_FULL,
        id=profile.id,
        telegram_id=profile.telegram_id,
        full_name=profile.full_name,
        tutor_id=profile.tutor_id,
        group_id=profile.group_id,
        group_name=profile.group_name,
        card=texts.full_student_card(texts.STUDENT_CARD_TITLE, profile),
    )


def _survey(code: str) -> str:
    return code if code in SURVEY_VALUES else SURVEY_BASIC


async def _get_row(db: Database, survey: str, row_id: int) -> Row | None:
    if survey == SURVEY_FULL:
        profile = await db.get_full_profile(row_id)
        return _full_row(profile) if profile else None
    student = await db.get_student(row_id)
    return _basic_row(student) if student else None


async def _list_rows(db: Database, survey: str, group_id: int) -> list[Row]:
    if survey == SURVEY_FULL:
        return [_full_row(p) for p in await db.list_full_profiles(group_id=group_id)]
    return [_basic_row(s) for s in await db.list_students(group_id=group_id)]


async def _delete_row(db: Database, survey: str, row_id: int, tutor_id: int | None) -> bool:
    if survey == SURVEY_FULL:
        return await db.delete_full_profile(row_id, tutor_id=tutor_id)
    return await db.delete_student(row_id, tutor_id=tutor_id)


# ---------------------------------------------------------------- loaders


async def _load_group(callback: CallbackQuery, db: Database, actor: Actor, group_id: int) -> Group | None:
    """Load a group the actor may manage; answers the callback and returns ``None`` otherwise."""
    group = await db.get_group(group_id)
    if group is None:
        await callback.answer(texts.GROUP_NOT_FOUND, show_alert=True)
        return None
    if not actor.may_manage(group.tutor_id):
        log.warning("User %s denied on group %s owned by tutor %s", actor.user_id, group.id, group.tutor_id)
        await callback.answer(texts.NO_PERMISSION, show_alert=True)
        return None
    return group


async def _load_student(
    callback: CallbackQuery, db: Database, actor: Actor, student_id: int, survey: str = SURVEY_BASIC
) -> Row | None:
    """Load a student the actor may manage; answers the callback and returns ``None`` otherwise."""
    row = await _get_row(db, survey, student_id)
    if row is None:
        await callback.answer(texts.STUDENT_NOT_FOUND, show_alert=True)
        return None
    if not actor.may_manage(row.tutor_id):
        log.warning("User %s denied on student %s owned by tutor %s", actor.user_id, row.id, row.tutor_id)
        await callback.answer(texts.NO_PERMISSION, show_alert=True)
        return None
    return row


# ---------------------------------------------------------------- screens


async def _tutor_line(db: Database, group: Group, mode: str) -> str:
    """Group names are unique per tutor only, so an admin's screen says whose group this is."""
    if mode != VIA_ADMIN:
        return ""
    owner = await db.get_tutor(group.tutor_id)
    return texts.STUDENT_LIST_TUTOR_LINE.format(tutor=hesc(owner.name)) if owner is not None else ""


async def _student_list(
    db: Database, group: Group, actor: Actor, survey: str = SURVEY_BASIC
) -> tuple[str, InlineKeyboardMarkup]:
    mode = actor.mode_for(group.tutor_id)
    rows = await _list_rows(db, survey, group.id)
    tutor_line = await _tutor_line(db, group, mode)
    label = texts.SURVEY_SHORT_LABELS[survey]
    if rows:
        text = texts.STUDENT_LIST_TITLE.format(group=hesc(group.name), n=len(rows), tutor=tutor_line)
    else:
        text = texts.STUDENT_LIST_EMPTY.format(group=hesc(group.name), tutor=tutor_line)
    return f"{text}\n\n🗂 {label}", student_list_kb(rows, group, mode, survey)


async def _surveys_screen(db: Database, group: Group, actor: Actor) -> tuple[str, InlineKeyboardMarkup]:
    """The two student lists of one group, with how many filled each questionnaire in."""
    mode = actor.mode_for(group.tutor_id)
    basic_n = len(await db.list_students(group_id=group.id))
    full_n = await db.count_group_profiles(group.id)
    text = texts.STUDENT_PICK_SURVEY.format(group=hesc(group.name), tutor=await _tutor_line(db, group, mode))
    return text, group_surveys_kb(group, mode, basic_n, full_n)


def _message_body(text: str) -> str | None:
    """The sender's words as typed (line breaks kept), or ``None`` when empty / too long."""
    value = text.strip()
    return value if 0 < len(value) <= MESSAGE_MAX_LEN else None


async def _deliver(bot: Bot, chat_id: int, sender: str, text: str, removed_from: str | None = None) -> str:
    """Send ``text`` to the student under a header naming the sender. Never raises."""
    note = texts.MESSAGE_REMOVED_LINE.format(group=hesc(removed_from)) if removed_from else ""
    body = texts.MESSAGE_TO_STUDENT.format(sender=sender, note=note, text=hesc(text))
    try:
        await bot.send_message(chat_id, body)
    except TelegramForbiddenError as exc:
        log.warning("Message to %s not delivered (blocked): %s", chat_id, exc)
        return BLOCKED
    except TelegramAPIError as exc:
        log.warning("Message to %s failed: %s", chat_id, exc)
        return FAILED
    return SENT


# ------------------------------------------------------------ list / card


async def cb_surveys(
    callback: CallbackQuery,
    callback_data: StuCb,
    state: FSMContext,
    db: Database,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    """🎓 Talabalar: which questionnaire's list of this group to open."""
    actor = _actor(callback.from_user.id, is_admin, tutor, callback_data.via)
    group = await _load_group(callback, db, actor, callback_data.id)
    if group is None:
        return
    await state.clear()
    await callback.answer()
    text, kb = await _surveys_screen(db, group, actor)
    await edit_or_send(callback, bot, text, kb)


async def cb_list(
    callback: CallbackQuery,
    callback_data: StuCb,
    state: FSMContext,
    db: Database,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    actor = _actor(callback.from_user.id, is_admin, tutor, callback_data.via)
    group = await _load_group(callback, db, actor, callback_data.id)
    if group is None:
        return
    await state.clear()  # navigating away from a pending text prompt abandons it
    await callback.answer()
    text, kb = await _student_list(db, group, actor, _survey(callback_data.s))
    await edit_or_send(callback, bot, text, kb)


async def cb_view(
    callback: CallbackQuery,
    callback_data: StuCb,
    state: FSMContext,
    db: Database,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    actor = _actor(callback.from_user.id, is_admin, tutor, callback_data.via)
    survey = _survey(callback_data.s)
    student = await _load_student(callback, db, actor, callback_data.id, survey)
    if student is None:
        return
    await state.clear()
    await callback.answer()
    await edit_or_send(
        callback, bot, student.card, student_manage_kb(student, actor.mode_for(student.tutor_id), survey)
    )


# --------------------------------------------------------- message a student


async def cb_message(
    callback: CallbackQuery,
    callback_data: StuCb,
    state: FSMContext,
    db: Database,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    actor = _actor(callback.from_user.id, is_admin, tutor, callback_data.via)
    survey = _survey(callback_data.s)
    student = await _load_student(callback, db, actor, callback_data.id, survey)
    if student is None:
        return
    await state.set_state(StudentManage.message_text)
    await state.set_data({"student_id": student.id, "via": actor.via, "survey": survey})
    await callback.answer()
    # The card's buttons go away so a stray tap on them cannot race the open prompt; commands, menu
    # buttons and ❌ Bekor qilish still cancel it.
    await remove_inline_keyboard(callback)
    await bot.send_message(
        callback.from_user.id,
        texts.ASK_STUDENT_MESSAGE.format(name=hesc(student.full_name)),
        reply_markup=cancel_kb(),
    )


async def message_text(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    if message.text is None:  # ``IsFreeText`` lets photos, stickers and voice notes through
        await message.answer(texts.STUDENT_MESSAGE_TEXT_ONLY, reply_markup=cancel_kb())
        return
    text = _message_body(message.text)
    if text is None:
        await message.answer(texts.STUDENT_MESSAGE_INVALID.format(max=MESSAGE_MAX_LEN), reply_markup=cancel_kb())
        return
    user_id = _sender_id(message)
    data = await state.get_data()
    actor = _actor(user_id, is_admin, tutor, str(data.get("via") or VIA_TUTOR))
    survey = _survey(str(data.get("survey") or SURVEY_BASIC))
    # Re-read the student: they may have been deleted, or moved to another tutor, while the prompt was open.
    student = await _get_row(db, survey, int(data.get("student_id") or 0))
    if student is None or not actor.may_manage(student.tutor_id):
        await state.clear()
        if student is not None:
            log.warning("User %s denied on student %s owned by tutor %s", user_id, student.id, student.tutor_id)
        refusal = texts.STUDENT_NOT_FOUND if student is None else texts.NO_PERMISSION
        await message.answer(refusal, reply_markup=await _menu(db, settings, user_id))
        return
    mode = actor.mode_for(student.tutor_id)
    outcome = await _deliver(bot, student.telegram_id, actor.sender_line(student.tutor_id), text)
    await state.clear()
    log.info("%s %s messaged student %s (tg=%s): %s", _role(mode), user_id, student.id, student.telegram_id, outcome)
    result = {
        SENT: texts.STUDENT_MESSAGE_SENT.format(name=hesc(student.full_name)),
        BLOCKED: texts.STUDENT_MESSAGE_BLOCKED,
        FAILED: texts.STUDENT_MESSAGE_FAILED,
    }[outcome]
    await message.answer(result, reply_markup=await _menu(db, settings, user_id))
    await message.answer(student.card, reply_markup=student_manage_kb(student, mode, survey))


# ----------------------------------------------------------- delete a student


async def cb_delete(
    callback: CallbackQuery,
    callback_data: StuCb,
    state: FSMContext,
    db: Database,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    actor = _actor(callback.from_user.id, is_admin, tutor, callback_data.via)
    survey = _survey(callback_data.s)
    student = await _load_student(callback, db, actor, callback_data.id, survey)
    if student is None:
        return
    await state.clear()
    await callback.answer()
    await edit_or_send(
        callback,
        bot,
        texts.STUDENT_DELETE_CONFIRM.format(
            name=hesc(student.full_name),
            group=hesc(student.group_name),
            survey=texts.SURVEY_SHORT_LABELS[survey],
        ),
        student_confirm_delete_kb(student, actor.mode_for(student.tutor_id), survey),
    )


async def cb_confirm_delete(
    callback: CallbackQuery,
    callback_data: StuCb,
    state: FSMContext,
    db: Database,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    actor = _actor(callback.from_user.id, is_admin, tutor, callback_data.via)
    survey = _survey(callback_data.s)
    student = await _load_student(callback, db, actor, callback_data.id, survey)
    if student is None:
        return
    # A tutor's delete is scoped to their own students in the statement itself, so a student who
    # moved to another tutor after the check above is not removed; a superadmin is not scoped.
    scope = None if actor.is_admin or actor.tutor is None else actor.tutor.id
    if not await _delete_row(db, survey, student.id, scope):  # gone already (double tap) or moved
        await callback.answer(texts.STUDENT_NOT_FOUND, show_alert=True)
        return
    mode = actor.mode_for(student.tutor_id)
    log.info(
        "%s %s deleted student %s (tg=%s) from group %s of tutor %s",
        _role(mode), actor.user_id, student.id, student.telegram_id, student.group_id, student.tutor_id,
    )
    await callback.answer(texts.STUDENT_DELETED_TOAST)
    # The row is gone; whatever the farewell step needs about the student now lives in the FSM data.
    # ``set_data`` (not ``update_data``) so nothing from an earlier flow can leak into this one.
    await state.set_state(StudentManage.farewell)
    await state.set_data(
        {
            "student_id": student.id,
            "farewell_tg": student.telegram_id,
            "farewell_name": student.full_name,
            "farewell_group": student.group_name,
            "sender": actor.sender_line(student.tutor_id),
            "group_id": student.group_id,
            "via": actor.via,
            "survey": survey,
        }
    )
    await edit_or_send(
        callback,
        bot,
        texts.STUDENT_DELETED_ASK_MESSAGE.format(name=hesc(student.full_name)),
        student_farewell_kb(student.id, mode, survey),
    )


async def _show_list_after(
    callback: CallbackQuery, bot: Bot, db: Database, actor: Actor, group_id: int, lead: str, survey: str
) -> None:
    """Replace the farewell question with ``lead`` and the group's (now shorter) student list."""
    group = await db.get_group(group_id)
    if group is None or not actor.may_manage(group.tutor_id):
        await edit_or_send(callback, bot, lead)
        return
    text, kb = await _student_list(db, group, actor, survey)
    await edit_or_send(callback, bot, f"{lead}\n\n{text}", kb)


async def cb_farewell(
    callback: CallbackQuery,
    callback_data: StuCb,
    state: FSMContext,
    db: Database,
    settings: Settings,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    """✉️ Ha / ❌ Yo'q under "the student was deleted -- message them?".

    Registered without a state filter on purpose: a tap that arrives after the tutor has moved on
    (state cleared) gets a specific explanation instead of the generic "stale or no permission".
    The button carries the deleted row's id, which must match the question currently open -- so a
    button left over from an earlier deletion cannot answer for a later one. A stale tap only gets
    an alert: the tapped message may by now be the freshly drawn student list (double tap on ❌),
    whose keyboard must stay.
    """
    current = await state.get_state()
    data = await state.get_data()
    same_student = bool(data.get("farewell_tg")) and int(data.get("student_id") or 0) == callback_data.id
    prompt_open = current == StudentManage.farewell_text.state and same_student
    if not prompt_open and (current != StudentManage.farewell.state or not same_student):
        await callback.answer(texts.FAREWELL_STALE, show_alert=True)
        return
    actor = _actor(callback.from_user.id, is_admin, tutor, str(data.get("via") or VIA_TUTOR))
    name = hesc(str(data.get("farewell_name") or ""))
    if callback_data.action == STU_BYE_YES:
        if prompt_open:  # ✉️ Ha tapped twice: the prompt is already up
            await callback.answer(texts.STUDENT_MESSAGE_PROMPT_TOAST)
            return
        await state.set_state(StudentManage.farewell_text)
        await callback.answer()
        await remove_inline_keyboard(callback)
        await bot.send_message(
            callback.from_user.id, texts.ASK_STUDENT_MESSAGE.format(name=name), reply_markup=cancel_kb()
        )
        return
    await state.clear()
    await callback.answer()
    if prompt_open:  # ❌ Yo'q after ✉️ Ha: drop the open prompt (and its cancel keyboard) first
        await bot.send_message(callback.from_user.id, texts.CANCELLED, reply_markup=await _menu(db, settings, actor.user_id))
    await _show_list_after(
        callback,
        bot,
        db,
        actor,
        int(data.get("group_id") or 0),
        texts.STUDENT_DELETED_NO_MESSAGE.format(name=name),
        _survey(str(data.get("survey") or SURVEY_BASIC)),
    )


async def farewell_text(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
    bot: Bot,
    is_admin: bool,
    tutor: Tutor | None,
) -> None:
    if message.text is None:
        await message.answer(texts.STUDENT_MESSAGE_TEXT_ONLY, reply_markup=cancel_kb())
        return
    text = _message_body(message.text)
    if text is None:
        await message.answer(texts.STUDENT_MESSAGE_INVALID.format(max=MESSAGE_MAX_LEN), reply_markup=cancel_kb())
        return
    user_id = _sender_id(message)
    data = await state.get_data()
    recipient = int(data.get("farewell_tg") or 0)
    if not recipient:  # cannot normally happen: the state and its data live and die together
        await state.clear()
        await message.answer(texts.FAREWELL_STALE, reply_markup=await _menu(db, settings, user_id))
        return
    actor = _actor(user_id, is_admin, tutor, str(data.get("via") or VIA_TUTOR))
    # The recipient is deliberately taken from the FSM data, not the live table: the permission was
    # checked at deletion time, and the farewell belongs to that deletion even if the student has
    # already registered again somewhere (the note about the old group stays true).
    sender = str(data.get("sender") or texts.MESSAGE_SENDER_ADMIN)
    outcome = await _deliver(bot, recipient, sender, text, removed_from=str(data.get("farewell_group") or ""))
    await state.clear()
    log.info("User %s messaged deleted student tg=%s: %s", user_id, recipient, outcome)
    name = hesc(str(data.get("farewell_name") or ""))
    result = {
        SENT: texts.STUDENT_DELETED_MESSAGE_SENT,
        BLOCKED: texts.STUDENT_DELETED_MESSAGE_BLOCKED,
        FAILED: texts.STUDENT_DELETED_MESSAGE_FAILED,
    }[outcome].format(name=name)
    await message.answer(result, reply_markup=await _menu(db, settings, user_id))
    group = await db.get_group(int(data.get("group_id") or 0))
    if group is not None and actor.may_manage(group.tutor_id):
        list_text, kb = await _student_list(db, group, actor, _survey(str(data.get("survey") or SURVEY_BASIC)))
        await message.answer(list_text, reply_markup=kb)


async def farewell_expect_buttons(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)


# ------------------------------------------------------------- registration


def create_router() -> Router:
    """Build the student-management router. A fresh instance is returned on every call."""
    router = Router(name="manage")
    router.message.filter(IsStaff())
    router.callback_query.filter(IsStaff())

    msg = router.message
    cb = router.callback_query
    free_text = IsFreeText()

    cb.register(cb_surveys, StuCb.filter(F.action == STU_SURVEYS))
    cb.register(cb_list, StuCb.filter(F.action == STU_LIST))
    cb.register(cb_view, StuCb.filter(F.action == STU_VIEW))
    cb.register(cb_message, StuCb.filter(F.action == STU_MESSAGE))
    cb.register(cb_delete, StuCb.filter(F.action == STU_DELETE))
    cb.register(cb_confirm_delete, StuCb.filter(F.action == STU_CONFIRM_DELETE))
    cb.register(cb_farewell, StuCb.filter(F.action.in_({STU_BYE_YES, STU_BYE_NO})))

    # Free text only: slash commands and main-menu buttons keep falling through to their owners.
    msg.register(message_text, StudentManage.message_text, free_text)
    msg.register(farewell_text, StudentManage.farewell_text, free_text)
    msg.register(farewell_expect_buttons, StateFilter(StudentManage.farewell), free_text)
    return router
