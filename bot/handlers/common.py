"""System commands (/start, /help, /cancel), the cancel button, block tracking and catch-all fallbacks.

The system router must be included *before* the role routers so that ``/start``, ``/cancel`` and
the cancel button pre-empt any FSM state; the common router must be included *last* (catch-alls).
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message, ReplyKeyboardRemove

from .. import texts
from ..commands import ADMIN_COMMANDS, TUTOR_COMMANDS
from ..config import Settings
from ..db import Database
from ..filters import get_roles
from ..keyboards import main_menu_kb
from ..utils import hesc
from .student import show_survey_picker

log = logging.getLogger(__name__)


async def cmd_start(message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    await state.clear()
    user = message.from_user
    if user is None:
        return
    # /users lists everyone who ever started the bot, registered or not.
    await db.touch_user(user.id, user.username, user.full_name)
    is_admin, is_tutor = await get_roles(db, settings, user.id)
    if not (is_admin or is_tutor):
        # Two questionnaires now: the student picks which one they mean, and the picker shows which
        # of them is already filled in (tapping a finished one opens its card with the edit buttons).
        await show_survey_picker(bot, user.id, state, db)
        return
    await message.answer(
        texts.GREETING.format(name=hesc(user.full_name)),
        reply_markup=main_menu_kb(is_admin, is_tutor),
    )


async def cmd_help(message: Message, db: Database, settings: Settings) -> None:
    user = message.from_user
    if user is None:
        return
    is_admin, is_tutor = await get_roles(db, settings, user.id)
    await message.answer(texts.help_text(is_admin, is_tutor))


async def cmd_cancel(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    await state.clear()
    user = message.from_user
    if user is None:
        return
    is_admin, is_tutor = await get_roles(db, settings, user.id)
    if is_admin or is_tutor:
        await message.answer(texts.CANCELLED, reply_markup=main_menu_kb(is_admin, is_tutor))
    else:
        await message.answer(texts.CANCELLED_STUDENT, reply_markup=ReplyKeyboardRemove())


async def on_my_chat_member(event: ChatMemberUpdated, db: Database) -> None:
    """The user blocked the bot (``kicked``) or came back (``member``, e.g. via "Restart").

    In a private chat Telegram sends this update for exactly those two events, so the blocked list
    stays current without anyone having to write to the user first. Nothing is sent back: a blocked
    chat would refuse it, and the one coming back gets their /start answered as usual.
    """
    status = event.new_chat_member.status
    if status == ChatMemberStatus.KICKED:
        blocked = True
    elif status == ChatMemberStatus.MEMBER:
        blocked = False
    else:
        return
    changed = await db.set_blocked([event.chat.id], blocked)
    log.info("User %s %s the bot%s", event.chat.id, "blocked" if blocked else "unblocked", "" if changed else " (no change)")


# ------------------------------------------------------------- catch-alls


async def admin_command_refused(message: Message) -> None:
    await message.answer(texts.ADMIN_ONLY)


async def tutor_command_refused(message: Message) -> None:
    await message.answer(texts.TUTOR_ONLY)


async def unknown_message(message: Message) -> None:
    await message.answer(texts.UNKNOWN)


async def unexpected_in_state(message: Message) -> None:
    await message.answer(texts.USE_BUTTONS)


async def stale_callback(callback: CallbackQuery) -> None:
    await callback.answer(texts.STALE_BUTTON, show_alert=True)


# ------------------------------------------------------------- registration


def create_system_router() -> Router:
    """/start, /help, /cancel and the cancel button; include FIRST so they pre-empt any FSM state.

    Also the ``my_chat_member`` handler that records who blocked the bot. Registering it is what
    makes polling ask Telegram for those updates (``allowed_updates`` is derived from the handlers).
    """
    router = Router(name="system")
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_cancel, Command("cancel"))
    router.message.register(cmd_cancel, F.text == texts.BTN_CANCEL)
    router.my_chat_member.register(on_my_chat_member, F.chat.type == ChatType.PRIVATE)
    return router


def create_common_router() -> Router:
    """Catch-alls (refused role commands, unknown input, stale callbacks); include LAST."""
    router = Router(name="common")
    router.message.register(admin_command_refused, Command(*(c.command for c in ADMIN_COMMANDS)))
    router.message.register(tutor_command_refused, Command(*(c.command for c in TUTOR_COMMANDS)))
    router.message.register(unknown_message, StateFilter(None))
    router.message.register(unexpected_in_state)
    router.callback_query.register(stale_callback)
    return router
