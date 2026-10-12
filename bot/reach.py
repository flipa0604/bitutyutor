"""Finding out who can still be reached: a superadmin's check of every bot user, and the live check
behind a user search.

Telegram never tells a bot who blocked it in the past -- it only refuses the next request. The
cheapest request refused the same way is ``sendChatAction``: it puts nothing in the chat (the user
sees a "typing..." indicator for a few seconds at most), yet answers 403 Forbidden for anyone who
blocked the bot or deleted their account.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from .db import Database

log = logging.getLogger(__name__)

CHECK_DELAY = 0.05
"""Pause between users (seconds): ~20 requests a second, under Telegram's bot-wide ceiling of 30."""
PROGRESS_EVERY = 100  # users between two progress updates

# outcome of one probe
REACHABLE = "reachable"
BLOCKED = "blocked"  # the user blocked the bot or deleted their account
FAILED = "failed"  # any other Telegram error, or still throttled after one wait

_running = False
"""Whether a check of everyone is under way. A plain flag rather than an ``asyncio.Lock``: it is
taken without an await in between (see :func:`exclusive`), so it needs no event loop of its own."""


@dataclass(slots=True)
class CheckReport:
    total: int
    reachable: int = 0
    blocked: int = 0
    failed: int = 0
    newly_blocked: int = 0  # blocked now, not marked before the check
    unblocked: int = 0  # marked blocked before the check, reachable now


@contextmanager
def exclusive() -> Iterator[bool]:
    """Hold the single check slot for the ``with`` block; yields ``False`` (holding nothing) while
    another superadmin's check has it. Taking it involves no await, so two taps handled
    concurrently cannot both get it, and it is given back however the block ends."""
    global _running
    if _running:
        yield False
        return
    _running = True
    try:
        yield True
    finally:
        _running = False


async def probe(bot: Bot, chat_id: int) -> str:
    """Whether ``chat_id`` can be reached right now: ``REACHABLE``, ``BLOCKED`` or ``FAILED``. Never raises."""
    for _attempt in range(2):
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            return REACHABLE
        except TelegramRetryAfter as exc:  # flood control: wait as told, then try once more
            log.info("Flood control while probing %s: waiting %ss", chat_id, exc.retry_after)
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            return BLOCKED
        except TelegramAPIError as exc:
            log.warning("Probe of %s failed: %s", chat_id, exc)
            return FAILED
    return FAILED


async def check_users(
    bot: Bot,
    db: Database,
    user_ids: Sequence[int],
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> CheckReport:
    """Probe every user in turn, pausing between them, then record who blocked the bot and who can be
    reached again. Users whose probe failed keep whatever was known about them."""
    report = CheckReport(total=len(user_ids))
    blocked: list[int] = []
    reachable: list[int] = []
    for done, chat_id in enumerate(user_ids, start=1):
        outcome = await probe(bot, chat_id)
        if outcome == REACHABLE:
            reachable.append(chat_id)
        elif outcome == BLOCKED:
            blocked.append(chat_id)
        else:
            report.failed += 1
        if on_progress is not None and done % PROGRESS_EVERY == 0 and done < len(user_ids):
            await on_progress(done, len(user_ids))
        if CHECK_DELAY and done < len(user_ids):
            await asyncio.sleep(CHECK_DELAY)
    report.reachable, report.blocked = len(reachable), len(blocked)
    report.newly_blocked = await db.set_blocked(blocked, True)
    report.unblocked = await db.set_blocked(reachable, False)
    return report
