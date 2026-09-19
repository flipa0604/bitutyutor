"""Delivering a superadmin's broadcast: the collected parts are copied, in order, to every recipient.

A part is one of the admin's own messages (the opening text, a photo, a video, a voice note ...).
Telegram's ``copyMessage`` re-sends it to another chat exactly as it was -- formatting, caption and
media included, without a "forwarded from" header -- so nothing has to be stored but the message id.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import Message

log = logging.getLogger(__name__)

MAX_PARTS = 10
SEND_DELAY = 0.05
"""Pause between recipients (seconds): ~20 copies a second, under Telegram's bot-wide ceiling of 30."""
PROGRESS_EVERY = 20  # recipients between two progress updates

# outcome of one recipient
SENT = "sent"
BLOCKED = "blocked"  # the user blocked or deleted the bot
FAILED = "failed"  # any other Telegram error (source message deleted, chat gone, still throttled)

_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Part:
    kind: str  # text / photo / video / voice
    message_id: int  # the admin's original message, copied to each recipient
    summary: str  # first words of the text or caption, for the review screen

    def to_data(self) -> dict[str, Any]:
        return {"kind": self.kind, "message_id": self.message_id, "summary": self.summary}

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> Part:
        return cls(kind=str(data["kind"]), message_id=int(data["message_id"]), summary=str(data.get("summary") or ""))


def summarize(text: str | None, limit: int = 60) -> str:
    value = _WS_RE.sub(" ", (text or "").strip())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def part_from_message(message: Message) -> Part | None:
    """Turn what the admin just sent into a part, or ``None`` for content a broadcast does not carry."""
    if message.text is not None:
        return Part("text", message.message_id, summarize(message.text))
    if message.photo:
        return Part("photo", message.message_id, summarize(message.caption))
    if message.video is not None:
        return Part("video", message.message_id, summarize(message.caption))
    if message.voice is not None:
        return Part("voice", message.message_id, summarize(message.caption))
    return None


@dataclass(slots=True)
class Report:
    total: int
    sent: int = 0
    blocked: int = 0
    failed: int = 0

    def count(self, outcome: str) -> None:
        if outcome == SENT:
            self.sent += 1
        elif outcome == BLOCKED:
            self.blocked += 1
        else:
            self.failed += 1


async def copy_parts(bot: Bot, from_chat_id: int, to_chat_id: int, parts: Sequence[Part]) -> str:
    """Copy every part to one chat, in order. Stops at the first failure and reports why."""
    for part in parts:
        for attempt in range(2):
            try:
                await bot.copy_message(chat_id=to_chat_id, from_chat_id=from_chat_id, message_id=part.message_id)
                break
            except TelegramRetryAfter as exc:  # flood control: wait as told, then try once more
                log.info("Flood control while broadcasting to %s: waiting %ss", to_chat_id, exc.retry_after)
                await asyncio.sleep(exc.retry_after)
            except TelegramForbiddenError:
                return BLOCKED
            except TelegramAPIError as exc:
                log.warning("Broadcast part %s to %s failed: %s", part.kind, to_chat_id, exc)
                return FAILED
        else:  # two attempts, still throttled
            return FAILED
    return SENT


async def run_broadcast(
    bot: Bot,
    from_chat_id: int,
    recipients: Sequence[int],
    parts: Sequence[Part],
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> Report:
    """Deliver ``parts`` to every recipient, pausing between them, reporting progress now and then."""
    report = Report(total=len(recipients))
    for done, chat_id in enumerate(recipients, start=1):
        report.count(await copy_parts(bot, from_chat_id, chat_id, parts))
        if on_progress is not None and done % PROGRESS_EVERY == 0 and done < len(recipients):
            await on_progress(done, len(recipients))
        if SEND_DELAY and done < len(recipients):
            await asyncio.sleep(SEND_DELAY)
    return report
