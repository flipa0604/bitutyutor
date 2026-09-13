"""Test helpers: a recording fake Telegram session and Update factories."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from itertools import count
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import (
    CallbackQuery,
    Chat,
    Contact,
    Document,
    InputFile,
    Message,
    Update,
    User,
)

_update_ids = count(1)
_message_ids = count(1)
_callback_ids = count(1)


class FakeSession(BaseSession):
    """Records every Telegram method call and returns plausible results without touching the network."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self._message_ids = count(10_000)

    async def close(self) -> None:  # pragma: no cover - nothing to close
        return None

    async def stream_content(  # pragma: no cover - never used in tests
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b""

    async def make_request(
        self, bot: Bot, method: TelegramMethod[TelegramType], timeout: int | None = None
    ) -> TelegramType:
        self.calls.append(method)
        name = type(method).__name__
        chat_id = getattr(method, "chat_id", 0)
        if name == "SendMessage":
            return Message(  # type: ignore[return-value]
                message_id=next(self._message_ids),
                date=datetime.now(),
                chat=Chat(id=int(chat_id), type="private"),
                text=getattr(method, "text", None),
            )
        if name == "SendDocument":
            document = getattr(method, "document", None)
            filename = document.filename if isinstance(document, InputFile) else str(document)
            return Message(  # type: ignore[return-value]
                message_id=next(self._message_ids),
                date=datetime.now(),
                chat=Chat(id=int(chat_id), type="private"),
                document=Document(file_id="doc", file_unique_id="doc-u", file_name=filename),
            )
        if name in {"EditMessageText", "EditMessageReplyMarkup"}:
            return Message(  # type: ignore[return-value]
                message_id=int(getattr(method, "message_id", 0) or 0),
                date=datetime.now(),
                chat=Chat(id=int(chat_id), type="private"),
                text=getattr(method, "text", None),
            )
        if name == "GetMe":
            return User(id=42, is_bot=True, first_name="TestBot", username="test_bot")  # type: ignore[return-value]
        return True  # type: ignore[return-value]

    # ---------------------------------------------------------------- queries

    def of(self, method_name: str) -> list[TelegramMethod[Any]]:
        return [m for m in self.calls if type(m).__name__ == method_name]

    def sent_texts(self, chat_id: int | None = None) -> list[str]:
        result: list[str] = []
        for m in self.calls:
            if type(m).__name__ not in {"SendMessage", "EditMessageText"}:
                continue
            if chat_id is None or int(getattr(m, "chat_id", 0)) == chat_id:
                result.append(str(getattr(m, "text", "")))
        return result

    def last_text(self, chat_id: int | None = None) -> str:
        texts = self.sent_texts(chat_id)
        return texts[-1] if texts else ""

    def clear(self) -> None:
        self.calls.clear()


def make_user(user_id: int, username: str | None = None, first_name: str = "Test") -> User:
    return User(id=user_id, is_bot=False, first_name=first_name, username=username)


def text_update(user: User, text: str) -> Update:
    message = Message(
        message_id=next(_message_ids),
        date=datetime.now(),
        chat=Chat(id=user.id, type="private"),
        from_user=user,
        text=text,
    )
    return Update(update_id=next(_update_ids), message=message)


def contact_update(user: User, phone_number: str, contact_user_id: int | None) -> Update:
    message = Message(
        message_id=next(_message_ids),
        date=datetime.now(),
        chat=Chat(id=user.id, type="private"),
        from_user=user,
        contact=Contact(phone_number=phone_number, first_name="C", user_id=contact_user_id),
    )
    return Update(update_id=next(_update_ids), message=message)


def callback_update(user: User, data: str, message_text: str = "menu") -> Update:
    message = Message(
        message_id=next(_message_ids),
        date=datetime.now(),
        chat=Chat(id=user.id, type="private"),
        text=message_text,
    )
    callback = CallbackQuery(
        id=str(next(_callback_ids)),
        from_user=user,
        chat_instance="ci",
        message=message,
        data=data,
    )
    return Update(update_id=next(_update_ids), callback_query=callback)
