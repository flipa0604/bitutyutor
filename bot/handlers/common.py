"""System commands (/start, /help, /cancel), the cancel button and catch-all fallbacks.

The system router must be included *before* the role routers so that ``/start``, ``/cancel`` and
the cancel button pre-empt any FSM state; the common router must be included *last* (catch-alls).
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from .. import texts
from ..commands import ADMIN_COMMANDS, TUTOR_COMMANDS
from ..config import Settings
from ..db import Database
from ..filters import get_roles
from ..keyboards import main_menu_kb
from ..utils import hesc
from .student import show_student_home, start_registration


async def cmd_start(message: Message, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    await state.clear()
    user = message.from_user
    if user is None:
        return
    # /users lists everyone who ever started the bot, registered or not.
    await db.touch_user(user.id, user.username, user.full_name)
    is_admin, is_tutor = await get_roles(db, settings, user.id)
    if not (is_admin or is_tutor):
        # Someone already registered lands on their own card with the edit buttons; only a user with
        # nothing saved is pushed straight into the registration flow.
        if not await show_student_home(bot, user.id, state, db):
            await start_registration(bot, message.chat.id, state, db)
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
    """/start, /help, /cancel and the cancel button; include FIRST so they pre-empt any FSM state."""
    router = Router(name="system")
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_cancel, Command("cancel"))
    router.message.register(cmd_cancel, F.text == texts.BTN_CANCEL)
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
