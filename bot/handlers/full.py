"""The full questionnaire: 22 questions a student answers once, and edits afterwards.

Everything about a question -- its state, its prompt, the keyboard under it, how the answer is
validated and which ``full_profiles`` column it lands in -- lives in one table (:data:`STEPS`), and a
single engine walks it. The same engine serves both modes:

* **filling in** (``mode = "reg"``) walks :data:`ORDER` from the first question to the preview,
  skipping the blocks that do not apply (the work block unless the student works, and so on);
* **editing** (``mode = "edit"``) walks the short chain of one picked field (see :data:`EDIT_CHAINS`)
  and returns to the field picker, saving what changed.

The answers are held in the FSM data under ``answers`` (keys are column names), together with the
``trail`` of visited steps that ⬅️ Orqaga pops. Nothing reaches the database until the student
confirms the preview (filling in) or finishes one chain (editing).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, User

from .. import texts
from ..config import Settings
from ..db import Database, DuplicateError
from ..filters import IsFreeText, get_roles
from ..keyboards import (
    FL_CANCEL,
    FL_CONFIRM,
    FL_DONE,
    FL_FIELD,
    FL_OPEN,
    FL_REFILL,
    FL_RESTART,
    FL_SOCIAL,
    FL_SOCIAL_DONE,
    FL_SOCIAL_NONE,
    REG_BACK,
    REG_GROUP,
    REG_TUTOR,
    FullCb,
    RegCb,
    full_citizenship_kb,
    full_confirm_kb,
    full_course_kb,
    full_edit_field_kb,
    full_employed_kb,
    full_home_kb,
    full_married_kb,
    full_nav_kb,
    full_parent_kb,
    full_phone_kb,
    full_region_kb,
    full_social_kb,
    main_menu_kb,
    reg_group_list_kb,
    reg_tutor_list_kb,
)
from ..models import (
    COURSE_MAX,
    COURSE_MIN,
    REGION_VALUES,
    SOCIAL_VALUES,
    FullProfile,
    Group,
    Tutor,
)
from ..states import FullSurvey
from ..utils import (
    STUDENT_MAX_AGE,
    STUDENT_MIN_AGE,
    clean_text,
    edit_or_send,
    is_valid_length,
    is_valid_name,
    is_valid_phone,
    normalize_passport,
    normalize_phone,
    normalize_pinfl,
    parse_birth_date,
    remove_inline_keyboard,
)

log = logging.getLogger(__name__)

TEXT_MIN, TEXT_MAX = 2, 200
ADDRESS_MIN, ADDRESS_MAX = 5, 200

Answers = dict[str, Any]
Validated = tuple[Any, str | None]
"""``(value, error)``: exactly one of the two is set."""


# ------------------------------------------------------------- validators


def _text(min_len: int = TEXT_MIN, max_len: int = TEXT_MAX) -> Callable[[str, Answers], Validated]:
    def check(raw: str, _answers: Answers) -> Validated:
        if not is_valid_length(raw, min_len, max_len):
            return None, texts.FULL_TEXT_INVALID.format(min=min_len, max=max_len)
        return clean_text(raw), None

    return check


def _name(raw: str, _answers: Answers) -> Validated:
    if not is_valid_name(raw):
        return None, texts.REG_NAME_INVALID
    return clean_text(raw), None


def _phone(raw: str, _answers: Answers) -> Validated:
    normalized = normalize_phone(raw) if not is_valid_phone(raw) else raw.strip()
    if normalized is None or not is_valid_phone(normalized):
        return None, texts.REG_PARENT_PHONE_INVALID
    return normalized, None


def _parent_text(raw: str, answers: Answers) -> Validated:
    """A parent field may legitimately be unknown: the ⚠️ button stores a dash instead."""
    if clean_text(raw) == texts.BTN_FULL_SKIP_PARENT:
        return texts.NO_DATA_VALUE, None
    return _text()(raw, answers)


def _parent_name(raw: str, answers: Answers) -> Validated:
    if clean_text(raw) == texts.BTN_FULL_SKIP_PARENT:
        return texts.NO_DATA_VALUE, None
    return _name(raw, answers)


def _parent_phone(raw: str, answers: Answers) -> Validated:
    if clean_text(raw) == texts.BTN_FULL_SKIP_PARENT:
        return texts.NO_DATA_VALUE, None
    return _phone(raw, answers)


def _birth(raw: str, _answers: Answers) -> Validated:
    value = parse_birth_date(raw)
    if value is None:
        return None, texts.FULL_BIRTH_INVALID.format(min=STUDENT_MIN_AGE, max=STUDENT_MAX_AGE)
    return value.strftime("%d.%m.%Y"), None


def _passport(raw: str, _answers: Answers) -> Validated:
    value = normalize_passport(raw)
    if value is None:
        return None, texts.FULL_PASSPORT_INVALID
    return value, None


def _pinfl(raw: str, answers: Answers) -> Validated:
    birth = parse_birth_date(answers.get("birth_date"))
    if birth is None:  # cannot happen: the birth date is asked first and validated there
        return None, texts.FULL_BIRTH_INVALID.format(min=STUDENT_MIN_AGE, max=STUDENT_MAX_AGE)
    value = normalize_pinfl(raw, birth)
    if value is None:
        return None, texts.FULL_PINFL_INVALID.format(birth=answers.get("birth_date", ""))
    return value, None


def _course(raw: str, _answers: Answers) -> Validated:
    digits = "".join(ch for ch in clean_text(raw) if ch.isdigit())
    if digits.isdigit() and COURSE_MIN <= int(digits) <= COURSE_MAX:
        return int(digits), None
    return None, texts.FULL_COURSE_INVALID


def _region(raw: str, _answers: Answers) -> Validated:
    value = clean_text(raw)
    for region in REGION_VALUES:
        if value.casefold() == region.casefold():
            return region, None
    return None, texts.FULL_REGION_INVALID


def _choice(mapping: dict[str, Any]) -> Callable[[str, Answers], Validated]:
    def check(raw: str, _answers: Answers) -> Validated:
        value = clean_text(raw)
        if value in mapping:
            return mapping[value], None
        return None, texts.FULL_USE_BUTTONS

    return check


_CITIZENSHIP = _choice({texts.BTN_CITIZEN_UZ: texts.CITIZENSHIP_UZ, texts.BTN_CITIZEN_OTHER: ""})
_EMPLOYED = _choice({texts.BTN_EMPLOYED_YES: True, texts.BTN_EMPLOYED_NO: False})
_MARRIED = _choice({texts.BTN_MARRIED_YES: True, texts.BTN_MARRIED_NO: False})


# ------------------------------------------------------------- step table


@dataclass(frozen=True, slots=True)
class Step:
    """One question: where it lives, what it asks, and what a valid answer looks like."""

    name: str  # also the ``full_profiles`` column, except for the pickers and ``social``
    state: State
    prompt: str
    keyboard: Callable[[], ReplyKeyboardMarkup] | None = None
    validate: Callable[[str, Answers], Validated] | None = None
    hint: str = ""  # appended under the prompt


def _plain_kb() -> ReplyKeyboardMarkup:
    return full_nav_kb()


STEPS: tuple[Step, ...] = (
    Step("phone", FullSurvey.phone, texts.FULL_ASK_PHONE, full_phone_kb),
    Step("full_name", FullSurvey.full_name, texts.FULL_ASK_FULL_NAME, _plain_kb, _name),
    Step("direction", FullSurvey.direction, texts.FULL_ASK_DIRECTION, _plain_kb, _text()),
    Step("course", FullSurvey.course, texts.FULL_ASK_COURSE, full_course_kb, _course),
    Step("birth_date", FullSurvey.birth_date, texts.FULL_ASK_BIRTH, _plain_kb, _birth),
    Step("passport", FullSurvey.passport, texts.FULL_ASK_PASSPORT, _plain_kb, _passport),
    Step("pinfl", FullSurvey.pinfl, texts.FULL_ASK_PINFL, _plain_kb, _pinfl),
    Step("citizenship", FullSurvey.citizenship, texts.FULL_ASK_CITIZENSHIP, full_citizenship_kb, _CITIZENSHIP),
    Step(
        "citizenship_other",
        FullSurvey.citizenship_other,
        texts.FULL_ASK_CITIZENSHIP_OTHER,
        _plain_kb,
        _text(),
    ),
    Step("region", FullSurvey.region, texts.FULL_ASK_REGION, full_region_kb, _region),
    Step("district", FullSurvey.district, texts.FULL_ASK_DISTRICT, _plain_kb, _text()),
    Step("mfy", FullSurvey.mfy, texts.FULL_ASK_MFY, _plain_kb, _text()),
    Step("mfy_contact", FullSurvey.mfy_contact, texts.FULL_ASK_MFY_CONTACT, _plain_kb, _phone),
    Step("street", FullSurvey.street, texts.FULL_ASK_STREET, _plain_kb, _text(ADDRESS_MIN, ADDRESS_MAX)),
    Step("employed", FullSurvey.employed, texts.FULL_ASK_EMPLOYED, full_employed_kb, _EMPLOYED),
    Step("work_place", FullSurvey.work_place, texts.FULL_ASK_WORK_PLACE, _plain_kb, _text()),
    Step("work_position", FullSurvey.work_position, texts.FULL_ASK_WORK_POSITION, _plain_kb, _text()),
    Step("work_address", FullSurvey.work_address, texts.FULL_ASK_WORK_ADDRESS, _plain_kb, _text()),
    Step("work_phone", FullSurvey.work_phone, texts.FULL_ASK_WORK_PHONE, _plain_kb, _phone),
    Step("married", FullSurvey.married, texts.FULL_ASK_MARRIED, full_married_kb, _MARRIED),
    Step("spouse_name", FullSurvey.spouse_name, texts.FULL_ASK_SPOUSE_NAME, _plain_kb, _name),
    Step("spouse_work", FullSurvey.spouse_work, texts.FULL_ASK_SPOUSE_WORK, _plain_kb, _text()),
    Step("spouse_phone", FullSurvey.spouse_phone, texts.FULL_ASK_SPOUSE_PHONE, _plain_kb, _phone),
    Step("social", FullSurvey.social, texts.FULL_ASK_SOCIAL),  # inline multi-select
    Step(
        "father_name",
        FullSurvey.father_name,
        texts.FULL_ASK_FATHER_NAME,
        full_parent_kb,
        _parent_name,
        texts.FULL_PARENT_SKIP_HINT,
    ),
    Step("father_phone", FullSurvey.father_phone, texts.FULL_ASK_FATHER_PHONE, full_parent_kb, _parent_phone),
    Step("father_work", FullSurvey.father_work, texts.FULL_ASK_FATHER_WORK, full_parent_kb, _parent_text),
    Step("mother_name", FullSurvey.mother_name, texts.FULL_ASK_MOTHER_NAME, full_parent_kb, _parent_name),
    Step("mother_phone", FullSurvey.mother_phone, texts.FULL_ASK_MOTHER_PHONE, full_parent_kb, _parent_phone),
    Step("mother_work", FullSurvey.mother_work, texts.FULL_ASK_MOTHER_WORK, full_parent_kb, _parent_text),
)
BY_NAME: dict[str, Step] = {step.name: step for step in STEPS}
BY_STATE: dict[str, Step] = {step.state.state: step for step in STEPS}
ORDER: tuple[str, ...] = tuple(step.name for step in STEPS)

_SUB_STEPS = frozenset(
    {"citizenship_other", "work_place", "work_position", "work_address", "work_phone",
     "spouse_name", "spouse_work", "spouse_phone"}
)
NUMBERED: tuple[str, ...] = tuple(name for name in ORDER if name not in _SUB_STEPS)
assert len(NUMBERED) == texts.FULL_TOTAL_STEPS, "the intro promises a number of questions"

TEXT_STATES = tuple(step.state for step in STEPS if step.name != "social")
CHOICE_DEFAULTS: dict[str, Any] = {
    "work_place": "", "work_position": "", "work_address": "", "work_phone": "",
    "spouse_name": "", "spouse_work": "", "spouse_phone": "",
    "citizenship_other": "", "social_status": "",
}

GATE_BLOCKS: dict[str, tuple[str, ...]] = {
    "employed": ("work_place", "work_position", "work_address", "work_phone"),
    "married": ("spouse_name", "spouse_work", "spouse_phone"),
    "citizenship": ("citizenship_other",),
}
"""Answers that open a block of follow-up questions when they turn out to apply."""

EDIT_CHAINS: dict[str, tuple[str, ...]] = {
    # the PNFL encodes the birth date, so changing one means re-entering the other
    "birth_date": ("birth_date", "pinfl"),
    "citizenship": ("citizenship",),
    "employed": ("employed",),
    "married": ("married",),
}
"""Fields whose edit asks more than the field itself; anything else is a one-step chain."""


def _applies(name: str, answers: Answers) -> bool:
    if name == "citizenship_other":
        return not answers.get("citizenship")
    if name.startswith("work_"):
        return bool(answers.get("employed"))
    if name.startswith("spouse_"):
        return bool(answers.get("married"))
    return True


def _chain_for(field: str, answers: Answers) -> list[str]:
    """The steps one edit asks, in order (the conditional tail is decided while walking)."""
    return [name for name in EDIT_CHAINS.get(field, (field,)) if _applies(name, answers)]


def _step_header(name: str, answers: Answers) -> str:
    """``📊 14/22`` for a main question, plus the position inside a block for its sub-questions."""
    if name in NUMBERED:
        return texts.FULL_STEP_PREFIX.format(n=NUMBERED.index(name) + 1, total=texts.FULL_TOTAL_STEPS)
    parent = "employed" if name.startswith("work_") else "married" if name.startswith("spouse_") else "citizenship"
    block = [n for n in ORDER if n.startswith(name.split("_")[0] + "_")] if name != "citizenship_other" else [name]
    position = f" · {block.index(name) + 1}/{len(block)}" if len(block) > 1 else ""
    return texts.FULL_STEP_PREFIX.format(n=NUMBERED.index(parent) + 1, total=texts.FULL_TOTAL_STEPS) + position


# ------------------------------------------------------------------ engine


async def _ask(bot: Bot, chat_id: int, state: FSMContext, name: str) -> None:
    """Show one step: set its state, print the prompt with its position and keyboard."""
    step = BY_NAME[name]
    data = await state.get_data()
    answers: Answers = data.get("answers") or {}
    await state.set_state(step.state)
    body = f"{_step_header(name, answers)}\n\n{step.prompt}"
    if step.hint:
        body += f"\n\n{step.hint}"
    if step.name == "social":
        selected = list(answers.get("social_codes") or [])
        await bot.send_message(chat_id, body, reply_markup=ReplyKeyboardRemove())
        await bot.send_message(chat_id, texts.FULL_ASK_SOCIAL, reply_markup=full_social_kb(selected))
        return
    markup = step.keyboard() if step.keyboard else _plain_kb()
    await bot.send_message(chat_id, body, reply_markup=markup)


async def _advance(bot: Bot, chat_id: int, state: FSMContext, db: Database, settings: Settings) -> None:
    """Move to the next step of the current mode, or finish (preview / save)."""
    data = await state.get_data()
    answers: Answers = data.get("answers") or {}
    if data.get("mode") == "edit":
        chain: list[str] = list(data.get("chain") or [])
        while chain:
            name = chain.pop(0)
            if _applies(name, answers):
                await state.update_data(chain=chain)
                await _push_trail(state, name)
                await _ask(bot, chat_id, state, name)
                return
        await _save_edit(bot, chat_id, state, db, settings)
        return
    current = data.get("current") or ""
    start = ORDER.index(current) + 1 if current in BY_NAME else 0
    for name in ORDER[start:]:
        if _applies(name, answers):
            await _push_trail(state, name)
            await _ask(bot, chat_id, state, name)
            return
    await _show_preview(bot, chat_id, state, db)


async def _push_trail(state: FSMContext, name: str) -> None:
    data = await state.get_data()
    trail: list[str] = list(data.get("trail") or [])
    if not trail or trail[-1] != name:
        trail.append(name)
    await state.update_data(trail=trail, current=name)


async def _go_back(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """⬅️ Orqaga: drop the current step and ask the one before it again."""
    data = await state.get_data()
    trail: list[str] = list(data.get("trail") or [])
    if len(trail) < 2:
        await bot.send_message(chat_id, texts.FULL_NOTHING_TO_GO_BACK)
        return
    trail.pop()
    previous = trail[-1]
    if data.get("mode") == "edit":  # the step we left is due again after the one we return to
        chain = [data.get("current") or "", *(data.get("chain") or [])]
        await state.update_data(chain=[name for name in chain if name and name != previous])
    await state.update_data(trail=trail, current=previous)
    await _ask(bot, chat_id, state, previous)


# ------------------------------------------------------------------ saving


def _payload(answers: Answers) -> dict[str, Any]:
    """The answers as ``full_profiles`` columns: unasked blocks fall back to their empty defaults."""
    payload = dict(CHOICE_DEFAULTS)
    payload.update({name: value for name, value in answers.items() if name in BY_NAME or name in CHOICE_DEFAULTS})
    payload.pop("citizenship_other", None)
    payload.pop("social_codes", None)
    payload["citizenship"] = answers.get("citizenship") or answers.get("citizenship_other") or ""
    payload["social_status"] = ",".join(answers.get("social_codes") or [])
    payload["employed"] = bool(answers.get("employed"))
    payload["married"] = bool(answers.get("married"))
    if not payload["employed"]:
        for name in ("work_place", "work_position", "work_address", "work_phone"):
            payload[name] = ""
    if not payload["married"]:
        for name in ("spouse_name", "spouse_work", "spouse_phone"):
            payload[name] = ""
    payload.pop("social", None)
    return payload


def _transient(answers: Answers, user: User, tutor: Tutor, group: Group) -> FullProfile:
    """A FullProfile built from the answers, for the preview card (id 0, no timestamps)."""
    payload = _payload(answers)
    return FullProfile(
        id=0,
        telegram_id=user.id,
        username=user.username,
        tutor_id=tutor.id,
        group_id=group.id,
        created_at="",
        updated_at="",
        tutor_name=tutor.name,
        tutor_phone=tutor.phone,
        group_name=group.name,
        **payload,
    )


async def _selection(db: Database, answers: Answers) -> tuple[Tutor, Group] | None:
    tutor = await db.get_tutor(int(answers.get("tutor_id") or 0))
    group = await db.get_group(int(answers.get("group_id") or 0))
    if tutor is None or group is None or group.tutor_id != tutor.id:
        return None
    return tutor, group


async def _show_preview(bot: Bot, chat_id: int, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    answers: Answers = data.get("answers") or {}
    selection = await _selection(db, answers)
    if selection is None:
        await state.clear()
        await bot.send_message(chat_id, texts.REG_GROUP_NOT_FOUND, reply_markup=ReplyKeyboardRemove())
        await start_full_survey(bot, chat_id, state, db, chat_id)
        return
    tutor, group = selection
    user = User(id=chat_id, is_bot=False, first_name="", username=data.get("username"))
    await state.set_state(FullSurvey.confirm)
    card = texts.full_student_card(texts.FULL_PREVIEW_TITLE, _transient(answers, user, tutor, group))
    await bot.send_message(chat_id, card, reply_markup=ReplyKeyboardRemove())
    await bot.send_message(chat_id, texts.FULL_PREVIEW_TITLE, reply_markup=full_confirm_kb())


async def notify_full(bot: Bot, settings: Settings, tutor: Tutor, profile: FullProfile, is_update: bool) -> None:
    """Send the filled-in card to the tutor and every superadmin exactly once each."""
    title = texts.FULL_CARD_TITLE_UPDATE if is_update else texts.FULL_CARD_TITLE_NEW
    text = texts.full_student_card(title, profile)
    for chat_id in sorted({tutor.telegram_id, *settings.superadmin_ids}):
        try:
            await bot.send_message(chat_id, text)
        except TelegramAPIError as exc:
            log.warning("Could not deliver full-survey notification to %s: %s", chat_id, exc)


async def _finish_markup(db: Database, settings: Settings, user_id: int) -> Any:
    is_admin, is_tutor = await get_roles(db, settings, user_id)
    return main_menu_kb(is_admin, is_tutor) if (is_admin or is_tutor) else ReplyKeyboardRemove()


async def _save_edit(bot: Bot, chat_id: int, state: FSMContext, db: Database, settings: Settings) -> None:
    """One edit chain is done: write the changed columns and return to the field picker."""
    data = await state.get_data()
    answers: Answers = data.get("answers") or {}
    touched = list(data.get("touched") or [])
    payload = _payload(answers)
    changed = {name: value for name, value in payload.items() if name in touched}
    # the tutor/group pair is not a step of the table, so it is carried over by name
    changed.update({name: answers[name] for name in ("tutor_id", "group_id") if name in touched})
    if "employed" in touched:  # turning the job off clears the block it filled
        changed.update({name: payload[name] for name in ("work_place", "work_position", "work_address", "work_phone")})
    if "married" in touched:
        changed.update({name: payload[name] for name in ("spouse_name", "spouse_work", "spouse_phone")})
    if not changed:
        await _show_edit_menu(bot, chat_id, state, db)
        return
    try:
        profile = await db.update_full_profile(chat_id, **changed)
    except DuplicateError:
        await bot.send_message(chat_id, texts.FULL_IDENTITY_TAKEN)
        await _show_edit_menu(bot, chat_id, state, db)
        return
    if profile is None:
        await state.clear()
        await bot.send_message(chat_id, texts.FULL_GONE, reply_markup=await _finish_markup(db, settings, chat_id))
        return
    await state.update_data(touched=[], answers={}, chain=[], trail=[], current="", dirty=True)
    await bot.send_message(chat_id, texts.EDIT_SAVED, reply_markup=await _finish_markup(db, settings, chat_id))
    await _show_edit_menu(bot, chat_id, state, db)


# --------------------------------------------------------------- entry points


async def start_full_survey(
    bot: Bot, chat_id: int, state: FSMContext, db: Database, user_id: int, username: str | None = None
) -> None:
    """Reset the FSM and show the tutor picker of the full survey."""
    await state.clear()
    tutors = await db.list_tutors()
    if not tutors:
        await bot.send_message(chat_id, texts.REG_NO_TUTORS, reply_markup=ReplyKeyboardRemove())
        return
    await state.set_state(FullSurvey.choose_tutor)
    await state.update_data(mode="reg", answers={}, trail=[], current="", username=username)
    await bot.send_message(
        chat_id,
        texts.FULL_INTRO.format(n=texts.FULL_TOTAL_STEPS),
        reply_markup=ReplyKeyboardRemove(),
    )
    await bot.send_message(chat_id, texts.REG_CHOOSE_TUTOR, reply_markup=reg_tutor_list_kb(tutors))


async def show_full_home(bot: Bot, user_id: int, state: FSMContext, db: Database) -> bool:
    """Show a saved full survey with its edit buttons; ``False`` when there is nothing saved."""
    profile = await db.get_full_profile_by_telegram_id(user_id)
    if profile is None:
        return False
    await state.clear()
    can_refill = await db.is_test_user(user_id)
    card = texts.full_student_card(texts.FULL_HOME_TITLE, profile)
    await bot.send_message(
        user_id,
        f"{card}\n\n{texts.STUDENT_HOME_HINT}",
        reply_markup=full_home_kb(can_refill),
    )
    return True


# ------------------------------------------------------- tutor / group pick


async def cb_choose_tutor(
    callback: CallbackQuery, callback_data: RegCb, state: FSMContext, db: Database, bot: Bot, settings: Settings
) -> None:
    tutor = await db.get_tutor(callback_data.id)
    if tutor is None:
        await callback.answer(texts.REG_TUTOR_NOT_FOUND, show_alert=True)
        await remove_inline_keyboard(callback)
        await start_full_survey(bot, callback.from_user.id, state, db, callback.from_user.id)
        return
    await _update_answers(state, tutor_id=tutor.id)
    await state.set_state(FullSurvey.choose_group)
    await callback.answer()
    groups = await db.list_groups(tutor.id)
    text = texts.REG_CHOOSE_GROUP if groups else texts.REG_TUTOR_NO_GROUPS
    await edit_or_send(callback, bot, text, reg_group_list_kb(groups))


async def cb_back_to_tutors(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    await callback.answer()
    tutors = await db.list_tutors()
    if not tutors:
        await state.clear()
        await edit_or_send(callback, bot, texts.REG_NO_TUTORS)
        return
    await state.set_state(FullSurvey.choose_tutor)
    await edit_or_send(callback, bot, texts.REG_CHOOSE_TUTOR, reg_tutor_list_kb(tutors))


async def cb_choose_group(
    callback: CallbackQuery, callback_data: RegCb, state: FSMContext, db: Database, bot: Bot, settings: Settings
) -> None:
    data = await state.get_data()
    answers: Answers = data.get("answers") or {}
    group = await db.get_group(callback_data.id)
    tutor = await db.get_tutor(int(answers.get("tutor_id") or 0))
    if group is None or tutor is None or group.tutor_id != tutor.id:
        await callback.answer(texts.REG_GROUP_NOT_FOUND, show_alert=True)
        await remove_inline_keyboard(callback)
        await start_full_survey(bot, callback.from_user.id, state, db, callback.from_user.id)
        return
    await _update_answers(state, group_id=group.id)
    await callback.answer()
    await remove_inline_keyboard(callback)
    if data.get("mode") == "edit":  # the tutor/group edit is one chain of its own
        await _touch(state, "tutor_id", "group_id")
        await _save_edit(bot, callback.from_user.id, state, db, settings)
        return
    await state.update_data(username=callback.from_user.username)
    await _advance(bot, callback.from_user.id, state, db, settings)


# ------------------------------------------------------------ answering steps


async def _update_answers(state: FSMContext, **values: Any) -> None:
    data = await state.get_data()
    answers: Answers = dict(data.get("answers") or {})
    answers.update(values)
    await state.update_data(answers=answers)


async def _touch(state: FSMContext, *names: str) -> None:
    """Remember which columns this edit chain changed, so only those are written."""
    data = await state.get_data()
    touched = list(data.get("touched") or [])
    touched.extend(name for name in names if name not in touched)
    await state.update_data(touched=touched)


async def on_contact(message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    """The phone step accepts nothing but the student's own shared contact."""
    contact = message.contact
    user_id = message.from_user.id if message.from_user else message.chat.id
    if contact is None or contact.user_id != user_id:
        await message.answer(texts.REG_CONTACT_NOT_OWN, reply_markup=full_phone_kb())
        return
    phone = normalize_phone(contact.phone_number)
    if phone is None:
        await message.answer(texts.REG_PHONE_INVALID, reply_markup=full_phone_kb())
        return
    await _update_answers(state, phone=phone)
    await _touch(state, "phone")
    await _advance(bot, message.chat.id, state, db, settings)


async def on_text(message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    """Every typed answer of the full survey: ⬅️ Orqaga, then the step's own validation."""
    current = await state.get_state()
    step = BY_STATE.get(current or "")
    if step is None:  # pragma: no cover - the router only sends us the table's states
        return
    raw = message.text or ""
    if clean_text(raw) == texts.BTN_BACK:
        await _go_back(bot, message.chat.id, state)
        return
    if step.name == "phone":  # a typed number cannot prove whose it is
        await message.answer(texts.FULL_PHONE_BUTTON_ONLY, reply_markup=full_phone_kb())
        return
    data = await state.get_data()
    answers: Answers = data.get("answers") or {}
    assert step.validate is not None
    value, error = step.validate(raw, answers)
    if error is not None:
        markup = step.keyboard() if step.keyboard else _plain_kb()
        await message.answer(error, reply_markup=markup)
        return
    user_id = message.from_user.id if message.from_user else message.chat.id
    if step.name == "pinfl":
        owner = await db.find_full_profile_owner(passport=str(answers.get("passport") or ""), pinfl=str(value))
        if owner is not None and owner != user_id:
            await message.answer(texts.FULL_IDENTITY_TAKEN, reply_markup=_plain_kb())
            return
    if step.name == "citizenship_other":
        await _update_answers(state, citizenship=value, citizenship_other=value)
        await _touch(state, "citizenship")
    else:
        await _update_answers(state, **{step.name: value})
        await _touch(state, step.name)
    if data.get("mode") == "edit" and step.name in GATE_BLOCKS:
        # "Ishlayman" / "Oila qurganman" picked while editing: ask the block it opens, right here
        opened = {**answers, step.name: value}
        extra = [name for name in GATE_BLOCKS[step.name] if _applies(name, opened)]
        await state.update_data(chain=extra + list((await state.get_data()).get("chain") or []))
    await _advance(bot, message.chat.id, state, db, settings)


async def on_unexpected(message: Message) -> None:
    await message.answer(texts.FULL_USE_BUTTONS)


# ------------------------------------------------------------ social status


async def cb_social_toggle(
    callback: CallbackQuery, callback_data: FullCb, state: FSMContext, bot: Bot
) -> None:
    if callback_data.value not in SOCIAL_VALUES:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    data = await state.get_data()
    answers: Answers = data.get("answers") or {}
    selected = list(answers.get("social_codes") or [])
    if callback_data.value in selected:
        selected.remove(callback_data.value)
    else:
        selected.append(callback_data.value)
    await _update_answers(state, social_codes=selected)
    await callback.answer()
    await edit_or_send(callback, bot, texts.FULL_ASK_SOCIAL, full_social_kb(selected))


async def cb_social_none(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await _update_answers(state, social_codes=[])
    await callback.answer()
    await edit_or_send(callback, bot, texts.FULL_ASK_SOCIAL, full_social_kb([]))


async def cb_social_done(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    await callback.answer()
    await remove_inline_keyboard(callback)
    await _touch(state, "social_status")
    await _advance(bot, callback.from_user.id, state, db, settings)


# ------------------------------------------------------------------ confirm


async def cb_confirm(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    # Single-shot guard (see ``student.reg_confirm``): two taps must not save and notify twice.
    if await state.get_state() != FullSurvey.confirm.state:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    data = await state.get_data()
    answers: Answers = data.get("answers") or {}
    await state.set_state(None)
    user = callback.from_user
    selection = await _selection(db, answers)
    if selection is None:
        await callback.answer(texts.REG_GROUP_NOT_FOUND, show_alert=True)
        await remove_inline_keyboard(callback)
        await start_full_survey(bot, user.id, state, db, user.id, user.username)
        return
    tutor, group = selection
    try:
        profile, is_update = await db.upsert_full_profile(
            telegram_id=user.id,
            username=user.username,
            tutor_id=tutor.id,
            group_id=group.id,
            **_payload(answers),
        )
    except DuplicateError:
        await state.set_state(FullSurvey.confirm)
        await callback.answer(texts.FULL_IDENTITY_TAKEN, show_alert=True)
        return
    except Exception:
        await state.set_state(FullSurvey.confirm)  # nothing was saved: let the student tap ✅ again
        raise
    await state.clear()
    await callback.answer()
    await remove_inline_keyboard(callback)
    await bot.send_message(user.id, texts.FULL_SAVED, reply_markup=await _finish_markup(db, settings, user.id))
    log.info("Student %s %s the full survey (tutor=%s, group=%s)", user.id, "updated" if is_update else "filled", tutor.id, group.id)
    await notify_full(bot, settings, tutor, profile, is_update)


async def cb_restart(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    await callback.answer()
    await remove_inline_keyboard(callback)
    await bot.send_message(callback.from_user.id, texts.FULL_RESTARTED, reply_markup=ReplyKeyboardRemove())
    await start_full_survey(bot, callback.from_user.id, state, db, callback.from_user.id, callback.from_user.username)


async def cb_cancel(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    await state.clear()
    await callback.answer()
    await remove_inline_keyboard(callback)
    await bot.send_message(
        callback.from_user.id, texts.CANCELLED_STUDENT, reply_markup=await _finish_markup(db, settings, callback.from_user.id)
    )


# ------------------------------------------------------------------ editing


async def _show_edit_menu(bot: Bot, user_id: int, state: FSMContext, db: Database) -> None:
    profile = await db.get_full_profile_by_telegram_id(user_id)
    if profile is None:
        await state.clear()
        await bot.send_message(user_id, texts.FULL_GONE, reply_markup=ReplyKeyboardRemove())
        return
    data = await state.get_data()
    await state.set_state(FullSurvey.menu)
    await state.update_data(mode="edit", dirty=data.get("dirty", False))
    card = texts.full_student_card(texts.FULL_HOME_TITLE, profile)
    await bot.send_message(user_id, f"{card}\n\n{texts.FULL_EDIT_MENU}", reply_markup=full_edit_field_kb())


async def cb_open_edit(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    await callback.answer()
    await remove_inline_keyboard(callback)
    await state.clear()
    await _show_edit_menu(bot, callback.from_user.id, state, db)


async def cb_refill(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    """Test users only (the button is shown to nobody else): fill the whole survey again."""
    if not await db.is_test_user(callback.from_user.id):
        await callback.answer(texts.REREGISTER_BLOCKED, show_alert=True)
        return
    await callback.answer()
    await remove_inline_keyboard(callback)
    await start_full_survey(bot, callback.from_user.id, state, db, callback.from_user.id, callback.from_user.username)


def _profile_answers(profile: FullProfile) -> Answers:
    """The saved profile as engine answers, so an edit chain starts from what is already there."""
    return {
        "tutor_id": profile.tutor_id,
        "group_id": profile.group_id,
        "birth_date": profile.birth_date,
        "passport": profile.passport,
        "employed": profile.employed,
        "married": profile.married,
        "citizenship": profile.citizenship,
        "social_codes": profile.social_codes,
    }


async def cb_edit_field(
    callback: CallbackQuery, callback_data: FullCb, state: FSMContext, db: Database, bot: Bot, settings: Settings
) -> None:
    profile = await db.get_full_profile_by_telegram_id(callback.from_user.id)
    if profile is None:
        await state.clear()
        await callback.answer(texts.FULL_GONE, show_alert=True)
        return
    field = callback_data.value
    await callback.answer()
    await remove_inline_keyboard(callback)
    if field == "tg":
        tutors = await db.list_tutors()
        if not tutors:
            await bot.send_message(callback.from_user.id, texts.REG_NO_TUTORS)
            return
        await state.set_state(FullSurvey.choose_tutor)
        await state.update_data(mode="edit", answers=_profile_answers(profile), touched=[], trail=[], current="")
        await bot.send_message(callback.from_user.id, texts.EDIT_ASK_TUTOR, reply_markup=reg_tutor_list_kb(tutors))
        return
    if field not in BY_NAME:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    answers = _profile_answers(profile)
    await state.update_data(
        mode="edit", answers=answers, touched=[], trail=[], current="", chain=_chain_for(field, answers)
    )
    await _advance(bot, callback.from_user.id, state, db, settings)


async def cb_edit_done(
    callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot
) -> None:
    data = await state.get_data()
    dirty = bool(data.get("dirty"))
    await state.clear()
    await callback.answer()
    await remove_inline_keyboard(callback)
    user_id = callback.from_user.id
    profile = await db.get_full_profile_by_telegram_id(user_id)
    if profile is None:
        await bot.send_message(user_id, texts.FULL_GONE, reply_markup=await _finish_markup(db, settings, user_id))
        return
    await bot.send_message(
        user_id,
        texts.EDIT_DONE if dirty else texts.EDIT_NOTHING_CHANGED,
        reply_markup=await _finish_markup(db, settings, user_id),
    )
    if dirty:
        tutor = await db.get_tutor(profile.tutor_id)
        if tutor is not None:
            await notify_full(bot, settings, tutor, profile, is_update=True)


# ------------------------------------------------------------- registration


def create_router() -> Router:
    """Build the full-survey router. A fresh instance is returned on every call."""
    router = Router(name="full")
    msg = router.message
    cb = router.callback_query
    free_text = IsFreeText()

    cb.register(cb_choose_tutor, FullSurvey.choose_tutor, RegCb.filter(F.action == REG_TUTOR))
    cb.register(cb_back_to_tutors, FullSurvey.choose_group, RegCb.filter(F.action == REG_BACK))
    cb.register(cb_choose_group, FullSurvey.choose_group, RegCb.filter(F.action == REG_GROUP))

    msg.register(on_contact, FullSurvey.phone, F.contact)
    msg.register(on_text, StateFilter(*TEXT_STATES), F.text, free_text)
    msg.register(
        on_unexpected,
        StateFilter(*TEXT_STATES, FullSurvey.social, FullSurvey.confirm, FullSurvey.menu),
        ~F.text,
    )

    cb.register(cb_social_toggle, FullSurvey.social, FullCb.filter(F.action == FL_SOCIAL))
    cb.register(cb_social_none, FullSurvey.social, FullCb.filter(F.action == FL_SOCIAL_NONE))
    cb.register(cb_social_done, FullSurvey.social, FullCb.filter(F.action == FL_SOCIAL_DONE))

    cb.register(cb_confirm, FullSurvey.confirm, FullCb.filter(F.action == FL_CONFIRM))
    cb.register(cb_restart, FullSurvey.confirm, FullCb.filter(F.action == FL_RESTART))
    cb.register(cb_cancel, FullCb.filter(F.action == FL_CANCEL))

    cb.register(cb_open_edit, FullCb.filter(F.action == FL_OPEN))
    cb.register(cb_refill, FullCb.filter(F.action == FL_REFILL))
    cb.register(cb_edit_field, FullSurvey.menu, FullCb.filter(F.action == FL_FIELD))
    cb.register(cb_edit_done, FullSurvey.menu, FullCb.filter(F.action == FL_DONE))
    return router
