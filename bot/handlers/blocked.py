"""Superadmin tools about reaching people: who has blocked the bot, and finding one user.

``/blocked`` (🚫 Bloklaganlar) lists the users known to have blocked the bot. The bot learns it the
moment someone blocks it, whenever a message cannot be delivered, and from 🔄 Hammasini tekshirish,
which probes everyone once (``bot.reach``) -- the only way to find those who blocked it before any of
this existed. ``/find`` (🔍 Foydalanuvchi qidirish) looks users up by username, Telegram ID or name
and checks each one live, so "have they blocked the bot?" is answered as of now; the search stays
open for the next query until it is cancelled. Every handler is guarded by ``IsSuperAdmin``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from .. import reach, texts
from ..config import Settings
from ..db import Database
from ..filters import IsFreeText, IsSuperAdmin, get_roles
from ..keyboards import (
    ADM_FIND,
    BLK_CHECK,
    BLK_LIST,
    AdminCb,
    BlkCb,
    admin_blocked_kb,
    cancel_kb,
    main_menu_kb,
)
from ..models import BotUser
from ..states import AdminUserSearch
from ..utils import clean_user_query, edit_or_send, hesc
from .admin import telegram_id_from_message

log = logging.getLogger(__name__)

BLOCKED_PAGE_SIZE = 20
SEARCH_LIMIT = 10  # users shown (and checked live) per query
QUERY_MIN_LEN, QUERY_MAX_LEN = 2, 64
MESSAGE_BUDGET = 3500  # Telegram caps a message at 4096 characters; longer results are split


# ------------------------------------------------------------- blocked list


async def _blocked_page(db: Database, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Render one page of the blocked list, clamping ``page`` so a stale arrow cannot overshoot."""
    blocked = await db.count_blocked()
    total, _registered = await db.count_users()
    if blocked == 0:
        return texts.blocked_empty(total), admin_blocked_kb(0, 1)
    pages = (blocked + BLOCKED_PAGE_SIZE - 1) // BLOCKED_PAGE_SIZE
    page = min(max(page, 0), pages - 1)
    offset = page * BLOCKED_PAGE_SIZE
    users = await db.list_blocked(BLOCKED_PAGE_SIZE, offset)
    return texts.blocked_page(users, blocked, total, page, pages, offset), admin_blocked_kb(page, pages)


async def cmd_blocked(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, markup = await _blocked_page(db, 0)
    await message.answer(text, reply_markup=markup)


async def cb_blocked(callback: CallbackQuery, callback_data: BlkCb, state: FSMContext, db: Database, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    text, markup = await _blocked_page(db, callback_data.page)
    await edit_or_send(callback, bot, text, markup)


async def cb_check(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    """🔄 Hammasini tekshirish: probe every user once, then report and show the list afresh.

    Runs inside the bot process for a few minutes (like a broadcast); only one check at a time.
    """
    user_id = callback.from_user.id
    with reach.exclusive() as acquired:
        if not acquired:
            await callback.answer(texts.BLK_CHECK_RUNNING, show_alert=True)
            return
        user_ids = await db.list_user_ids()
        if not user_ids:
            await callback.answer(texts.USERS_EMPTY, show_alert=True)
            return
        await state.clear()
        await callback.answer()
        log.info("Superadmin %s checks %s users for blocks", user_id, len(user_ids))
        is_admin, is_tutor = await get_roles(db, settings, user_id)
        status = await bot.send_message(
            user_id,
            texts.BLK_CHECK_STARTED.format(done=0, total=len(user_ids)),
            reply_markup=main_menu_kb(is_admin, is_tutor),
        )

        async def progress(done: int, total: int) -> None:
            try:
                await bot.edit_message_text(
                    texts.BLK_CHECK_STARTED.format(done=done, total=total), chat_id=user_id, message_id=status.message_id
                )
            except TelegramAPIError as exc:  # progress is best-effort
                log.debug("Check progress update failed: %s", exc)

        report = await reach.check_users(bot, db, user_ids, progress)
    log.info(
        "Check by %s finished: %s reachable, %s blocked (%s new), %s unblocked, %s failed of %s",
        user_id, report.reachable, report.blocked, report.newly_blocked, report.unblocked, report.failed, report.total,
    )
    await bot.send_message(
        user_id,
        texts.BLK_CHECK_REPORT.format(
            total=report.total,
            reachable=report.reachable,
            blocked=report.blocked,
            newly_blocked=report.newly_blocked,
            unblocked=report.unblocked,
            failed=report.failed,
        ),
    )
    text, markup = await _blocked_page(db, 0)
    await bot.send_message(user_id, text, reply_markup=markup)


# ------------------------------------------------------------------- search


def _chunks(blocks: Sequence[str], budget: int = MESSAGE_BUDGET) -> list[str]:
    """Join ``blocks`` with blank lines into as few messages as fit under ``budget`` characters each;
    a block is never split."""
    chunks: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if current and len(candidate) > budget:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def _check_live(bot: Bot, db: Database, user: BotUser) -> tuple[BotUser, bool]:
    """Probe one found user now and store the answer; ``checked`` is ``False`` when Telegram gave none
    (the stored status is then shown as the last known one)."""
    outcome = await reach.probe(bot, user.telegram_id)
    if outcome == reach.FAILED:
        return user, False
    await db.set_blocked([user.telegram_id], outcome == reach.BLOCKED)
    return (await db.get_user(user.telegram_id)) or user, True


async def _search(message: Message, raw: str, db: Database, bot: Bot) -> None:
    query = clean_user_query(raw)
    if not QUERY_MIN_LEN <= len(query) <= QUERY_MAX_LEN:
        await message.answer(
            texts.SEARCH_QUERY_INVALID.format(min=QUERY_MIN_LEN, max=QUERY_MAX_LEN), reply_markup=cancel_kb()
        )
        return
    found = await db.search_users(query, SEARCH_LIMIT + 1)
    sender = message.from_user.id if message.from_user is not None else message.chat.id
    log.info("Superadmin %s searched users: %s found", sender, len(found))
    if not found:
        await message.answer(texts.SEARCH_NOT_FOUND.format(query=hesc(query)), reply_markup=cancel_kb())
        return
    more = len(found) > SEARCH_LIMIT
    if more:
        blocks = [texts.SEARCH_HEADER_MORE.format(query=hesc(query), limit=SEARCH_LIMIT)]
    else:
        blocks = [texts.SEARCH_HEADER.format(query=hesc(query), n=len(found))]
    for index, user in enumerate(found[:SEARCH_LIMIT], start=1):
        checked_user, checked = await _check_live(bot, db, user)
        blocks.append(texts.search_result(index, checked_user, checked))
    blocks.append(f"{texts.SEARCH_MORE_HINT}\n{texts.SEARCH_FOOTER}" if more else texts.SEARCH_FOOTER)
    for chunk in _chunks(blocks):
        await message.answer(chunk, reply_markup=cancel_kb())


async def _start_search(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AdminUserSearch.query)
    await bot.send_message(chat_id, texts.ASK_USER_SEARCH, reply_markup=cancel_kb())


async def cmd_find(message: Message, command: CommandObject, state: FSMContext, db: Database, bot: Bot) -> None:
    """``/find`` asks for a query; ``/find vali`` searches at once. Either way the search stays open."""
    if not (command.args or "").strip():
        await _start_search(bot, message.chat.id, state)
        return
    await state.clear()
    await state.set_state(AdminUserSearch.query)
    await _search(message, command.args or "", db, bot)


async def cb_find(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _start_search(bot, callback.from_user.id, state)


async def search_query(message: Message, db: Database, bot: Bot) -> None:
    """A query typed -- or a message forwarded, which searches by its sender -- while the search is open."""
    if message.forward_origin is not None or message.forward_from is not None:
        telegram_id, hidden = telegram_id_from_message(message)
        if hidden or telegram_id is None:
            await message.answer(texts.SEARCH_FORWARD_HIDDEN, reply_markup=cancel_kb())
            return
        await _search(message, str(telegram_id), db, bot)
        return
    if message.text is None:  # ``IsFreeText`` lets photos, stickers and voice notes through
        await message.answer(texts.SEARCH_TEXT_ONLY, reply_markup=cancel_kb())
        return
    await _search(message, message.text, db, bot)


# ------------------------------------------------------------- registration


def create_router() -> Router:
    """Build the blocked-list / search router. A fresh instance is returned on every call."""
    router = Router(name="blocked")
    router.message.filter(IsSuperAdmin())
    router.callback_query.filter(IsSuperAdmin())

    msg = router.message
    cb = router.callback_query

    msg.register(cmd_blocked, Command("blocked"))
    msg.register(cmd_find, Command("find"))
    cb.register(cb_blocked, BlkCb.filter(F.action == BLK_LIST))
    cb.register(cb_check, BlkCb.filter(F.action == BLK_CHECK))
    cb.register(cb_find, AdminCb.filter(F.action == ADM_FIND))

    # Free text only: slash commands and main-menu buttons keep falling through to their owners.
    msg.register(search_query, AdminUserSearch.query, IsFreeText())
    return router
