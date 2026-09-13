"""Role filters (roles are additive: a user may be superadmin and tutor at the same time) and the
free-text guard shared by every FSM step that stores what the user typed."""

from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import Message, TelegramObject, User

from . import texts
from .config import Settings
from .db import Database


def _event_user(event: TelegramObject) -> User | None:
    return getattr(event, "from_user", None)


class IsSuperAdmin(BaseFilter):
    """Passes when the sender's Telegram ID is listed in ``SUPERADMIN_IDS``."""

    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = _event_user(event)
        return user is not None and settings.is_superadmin(user.id)


class IsTutor(BaseFilter):
    """Passes when the sender is a tutor (live DB lookup); injects ``tutor`` into handler kwargs."""

    async def __call__(self, event: TelegramObject, db: Database) -> bool | dict[str, Any]:
        user = _event_user(event)
        if user is None:
            return False
        tutor = await db.get_tutor_by_telegram_id(user.id)
        if tutor is None:
            return False
        return {"tutor": tutor}


class IsFreeText(BaseFilter):
    """Passes for input a free-text FSM step may store as data.

    A typed slash command or a main-menu button label is *not* data: it falls through to the handler
    that owns it (any role router or the catch-alls), so ``/excel`` typed at a name prompt opens the
    Excel menu instead of becoming a group called ``/excel``. Forwarded messages always pass because
    the Telegram-ID prompts read the original sender from them, whatever their text.
    """

    async def __call__(self, message: Message) -> bool:
        if message.forward_origin is not None or message.forward_from is not None:
            return True
        text = message.text or ""
        return not text.startswith("/") and text not in texts.MAIN_MENU_BUTTONS


async def get_roles(db: Database, settings: Settings, user_id: int) -> tuple[bool, bool]:
    """Return ``(is_admin, is_tutor)`` for a user, evaluated live."""
    is_admin = settings.is_superadmin(user_id)
    is_tutor = await db.get_tutor_by_telegram_id(user_id) is not None
    return is_admin, is_tutor
