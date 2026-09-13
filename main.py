"""Entry point: builds the Bot/Dispatcher and starts long polling.

Importing this module has no side effects; polling starts only under ``python main.py``.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.commands import setup_bot_commands
from bot.config import ConfigError, Settings, load_settings
from bot.db import Database
from bot.handlers import create_routers

log = logging.getLogger(__name__)


def create_dispatcher(db: Database, settings: Settings) -> Dispatcher:
    """Dispatcher with MemoryStorage, all routers and workflow data (``db``, ``settings``)."""
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["settings"] = settings
    dp.include_routers(*create_routers())
    return dp


def create_bot(settings: Settings) -> Bot:
    return Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(1)

    bot = create_bot(settings)
    db = Database(settings.db_path)
    # Everything after the DB is opened runs inside try/finally: aiosqlite's worker thread is not a
    # daemon, so an unclosed connection would keep the process alive after a startup failure.
    try:
        await db.init()
        dp = create_dispatcher(db, settings)
        await setup_bot_commands(bot, db, settings)
        log.info("Bot started; superadmins: %s; db: %s", sorted(settings.superadmin_ids), settings.db_path)
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped")
