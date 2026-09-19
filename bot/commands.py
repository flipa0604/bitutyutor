"""Bot command menus (``setMyCommands``) per scope; refreshed when roles change."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from .config import Settings
from .db import Database
from .filters import get_roles

log = logging.getLogger(__name__)

DEFAULT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Boshlash / ro'yxatdan o'tish"),
    BotCommand(command="mydata", description="Ma'lumotlarim (ko'rish va tahrirlash)"),
    BotCommand(command="help", description="Yordam"),
    BotCommand(command="cancel", description="Bekor qilish"),
)
ADMIN_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="admin", description="Admin panel"),
    BotCommand(command="tutors", description="Tyutorlar ro'yxati"),
    BotCommand(command="users", description="Bot foydalanuvchilari"),
    BotCommand(command="test_users", description="Test userlar (qayta ro'yxatdan o'tishi mumkin)"),
    BotCommand(command="add_tutor", description="Tyutor qo'shish"),
    BotCommand(command="edit_tutor", description="Tyutorni tahrirlash"),
    BotCommand(command="delete_tutor", description="Tyutorni o'chirish"),
    BotCommand(command="broadcast", description="Hammaga xabar yuborish"),
)
TUTOR_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="tutor", description="Tyutor panel"),
    BotCommand(command="groups", description="Guruhlarim"),
    BotCommand(command="students", description="Talabalar (xabar yuborish, o'chirish)"),
    BotCommand(command="add_group", description="Guruh qo'shish"),
    BotCommand(command="edit_group", description="Guruh nomini o'zgartirish"),
    BotCommand(command="delete_group", description="Guruhni o'chirish"),
    BotCommand(command="excel", description="Excel yuklab olish"),
)


def commands_for(is_admin: bool, is_tutor: bool) -> list[BotCommand]:
    """Role-additive command list for a private chat."""
    commands = list(DEFAULT_COMMANDS)
    if is_admin:
        commands.extend(ADMIN_COMMANDS)
    if is_tutor:
        commands.extend(TUTOR_COMMANDS)
    return commands


async def set_chat_commands(bot: Bot, chat_id: int, is_admin: bool, is_tutor: bool) -> None:
    """Best-effort: set (or reset) the command menu of one private chat.

    Telegram rejects chat scopes for users the bot has never talked to; that is logged and ignored.
    """
    scope = BotCommandScopeChat(chat_id=chat_id)
    try:
        if is_admin or is_tutor:
            await bot.set_my_commands(commands_for(is_admin, is_tutor), scope=scope)
        else:
            await bot.delete_my_commands(scope=scope)
    except TelegramAPIError as exc:
        log.warning("Could not update command menu for chat %s: %s", chat_id, exc)


async def refresh_user_commands(bot: Bot, db: Database, settings: Settings, user_id: int) -> None:
    """Recompute a user's roles and update their command menu (best-effort)."""
    is_admin, is_tutor = await get_roles(db, settings, user_id)
    await set_chat_commands(bot, user_id, is_admin, is_tutor)


async def setup_bot_commands(bot: Bot, db: Database, settings: Settings) -> None:
    """Default scope gets the basic commands; every superadmin/tutor chat gets its role-specific menu."""
    await bot.set_my_commands(list(DEFAULT_COMMANDS), scope=BotCommandScopeDefault())
    user_ids = set(settings.superadmin_ids)
    user_ids.update(t.telegram_id for t in await db.list_tutors())
    for user_id in sorted(user_ids):
        await refresh_user_commands(bot, db, settings, user_id)
