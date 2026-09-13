"""Shared fixtures: temporary database, settings, fake-session bot and a fully wired dispatcher."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import Settings
from bot.db import Database
from main import create_dispatcher
from tests.helpers import FakeSession

SUPERADMIN_ID = 1001
SECOND_SUPERADMIN_ID = 1002


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_token="42:TEST",
        superadmin_ids=frozenset({SUPERADMIN_ID, SECOND_SUPERADMIN_ID}),
        db_path=tmp_path / "test.db",
    )


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest_asyncio.fixture
async def bot(session: FakeSession) -> AsyncIterator[Bot]:
    test_bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    yield test_bot
    await test_bot.session.close()


@pytest.fixture
def dp(db: Database, settings: Settings) -> Dispatcher:
    return create_dispatcher(db, settings)
