"""Superadmin broadcast: compose a message out of several parts and copy it to every bot user.

The composer walks through four steps -- the mandatory text, then optional photo, video and voice
steps (any supported content is accepted in each, ⏭ moves on) -- and ends on a review screen where
more parts can be added with ➕, the last one dropped, the whole thing previewed (copied to the admin
themselves) and finally sent after one confirmation. Every handler is guarded by ``IsSuperAdmin``.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..broadcast import MAX_PARTS, Part, part_from_message, run_broadcast
from ..config import Settings
from ..db import Database
from ..filters import IsFreeText, IsSuperAdmin, get_roles
from ..keyboards import (
    ADM_BROADCAST,
    BC_ADD,
    BC_CANCEL,
    BC_CONFIRM,
    BC_PREVIEW,
    BC_REMOVE,
    BC_REVIEW,
    BC_SEND,
    BC_SKIP,
    PART_KINDS,
    AdminCb,
    BcCb,
    broadcast_back_kb,
    broadcast_confirm_kb,
    broadcast_continue_kb,
    broadcast_review_kb,
    broadcast_skip_kb,
    cancel_kb,
    main_menu_kb,
)
from ..states import Broadcast
from ..utils import edit_or_send, remove_inline_keyboard

log = logging.getLogger(__name__)

# the optional media steps in order, each with its prompt
_STEPS: tuple[tuple[Any, str], ...] = (
    (Broadcast.photo, texts.BC_ASK_PHOTO),
    (Broadcast.video, texts.BC_ASK_VIDEO),
    (Broadcast.voice, texts.BC_ASK_VOICE),
)
_STEP_STATES = {Broadcast.photo.state, Broadcast.video.state, Broadcast.voice.state}
# content is accepted in the media steps, after ➕, and straight from the review screen
_ACCEPTING = StateFilter(Broadcast.photo, Broadcast.video, Broadcast.voice, Broadcast.add, Broadcast.review)


# ------------------------------------------------------------------ helpers


def _parts(data: dict[str, Any]) -> list[Part]:
    return [Part.from_data(d) for d in data.get("parts") or []]


async def _store_parts(state: FSMContext, parts: list[Part]) -> None:
    await state.update_data(parts=[p.to_data() for p in parts])


async def _menu(db: Database, settings: Settings, user_id: int) -> Any:
    is_admin, is_tutor = await get_roles(db, settings, user_id)
    return main_menu_kb(is_admin, is_tutor)


async def _recipients(db: Database, sender_id: int) -> list[int]:
    """Everyone who ever started the bot, except the admin who is sending."""
    return [user_id for user_id in await db.list_user_ids() if user_id != sender_id]


def _review_text(parts: list[Part], recipients: int) -> str:
    lines = [texts.broadcast_part_line(i, p.kind, p.summary) for i, p in enumerate(parts, start=1)]
    return f"{texts.BC_REVIEW_TITLE}\n" + "\n".join(lines) + "\n\n" + texts.BC_REVIEW_FOOTER.format(n=recipients)


async def _show_review(
    bot: Bot, chat_id: int, state: FSMContext, db: Database, callback: CallbackQuery | None = None
) -> None:
    """The summary screen; edits the callback's message when there is one, else sends a new message."""
    parts = _parts(await state.get_data())
    await state.set_state(Broadcast.review)
    text = _review_text(parts, len(await _recipients(db, chat_id)))
    markup = broadcast_review_kb(can_remove=len(parts) > 1)
    if callback is not None:
        await edit_or_send(callback, bot, text, markup)
    else:
        await bot.send_message(chat_id, text, reply_markup=markup)


async def _start(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Broadcast.text)
    await state.set_data({"parts": []})
    await bot.send_message(chat_id, texts.BC_ASK_TEXT, reply_markup=cancel_kb())


# ------------------------------------------------------------------- entry


async def cmd_broadcast(message: Message, state: FSMContext, bot: Bot) -> None:
    await _start(bot, message.chat.id, state)


async def cb_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await _start(bot, callback.from_user.id, state)


# ------------------------------------------------------------- step 1: text


async def bc_text(message: Message, state: FSMContext) -> None:
    part = part_from_message(message)
    assert part is not None and part.kind == "text"  # guaranteed by the ``F.text`` filter
    await _store_parts(state, [part])
    await state.set_state(Broadcast.photo)
    await message.answer(texts.BC_ASK_PHOTO, reply_markup=broadcast_skip_kb())


async def bc_text_required(message: Message) -> None:
    await message.answer(texts.BC_TEXT_REQUIRED)


# -------------------------------------------------- steps 2-4 and ➕ from review


async def bc_add_part(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    """Any supported content in a media step, after ➕ or on the review screen becomes the next part."""
    part = part_from_message(message)
    if part is None:
        await message.answer(texts.BC_UNSUPPORTED)
        return
    parts = _parts(await state.get_data())
    if len(parts) >= MAX_PARTS:
        await message.answer(texts.BC_TOO_MANY_PARTS.format(max=MAX_PARTS))
        return
    parts.append(part)
    await _store_parts(state, parts)
    if await state.get_state() not in _STEP_STATES:  # ➕ or a direct send on the review: back to the summary
        await _show_review(bot, message.chat.id, state, db)
        return
    label = texts.BC_PART_LABELS[part.kind]
    await message.answer(texts.BC_PART_ADDED.format(label=label, n=len(parts)), reply_markup=broadcast_continue_kb())


async def bc_unsupported(message: Message) -> None:
    await message.answer(texts.BC_UNSUPPORTED)


async def cb_skip(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    """⏭ / ➡️ in a media step: on to the next step, or to the review after the last one."""
    current = await state.get_state()
    await callback.answer()
    await remove_inline_keyboard(callback)
    for index, (step, _prompt) in enumerate(_STEPS):
        if current == step.state:
            if index + 1 < len(_STEPS):
                next_step, next_prompt = _STEPS[index + 1]
                await state.set_state(next_step)
                await bot.send_message(callback.from_user.id, next_prompt, reply_markup=broadcast_skip_kb())
            else:
                await _show_review(bot, callback.from_user.id, state, db)
            return
    await _show_review(bot, callback.from_user.id, state, db)  # ⏭ tapped from an unexpected state


# ------------------------------------------------------------------ review


async def cb_add(callback: CallbackQuery, callback_data: BcCb, state: FSMContext, bot: Bot) -> None:
    kind = callback_data.value
    if kind not in PART_KINDS:
        await callback.answer(texts.STALE_BUTTON, show_alert=True)
        return
    if len(_parts(await state.get_data())) >= MAX_PARTS:
        await callback.answer(texts.BC_TOO_MANY_PARTS.format(max=MAX_PARTS), show_alert=True)
        return
    await state.set_state(Broadcast.add)
    await callback.answer()
    await edit_or_send(callback, bot, texts.BC_ASK_MORE.format(label=texts.BC_PART_LABELS[kind]), broadcast_back_kb())


async def cb_review(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    await callback.answer()
    await _show_review(bot, callback.from_user.id, state, db, callback)


async def cb_remove(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    parts = _parts(await state.get_data())
    if len(parts) <= 1:  # the opening text stays
        await callback.answer(texts.BC_NOTHING_TO_REMOVE, show_alert=True)
        return
    parts.pop()
    await _store_parts(state, parts)
    await callback.answer()
    await _show_review(bot, callback.from_user.id, state, db, callback)


async def cb_preview(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    """Copy the parts to the admin, one by one, so they see exactly what everyone else will."""
    parts = _parts(await state.get_data())
    await callback.answer()
    await remove_inline_keyboard(callback)
    user_id = callback.from_user.id
    for part in parts:
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=user_id, message_id=part.message_id)
        except TelegramAPIError as exc:  # the admin deleted the original message in the meantime
            log.warning("Broadcast preview of %s failed for %s: %s", part.kind, user_id, exc)
            await bot.send_message(user_id, texts.BC_PREVIEW_FAILED.format(label=texts.BC_PART_LABELS[part.kind]))
    await bot.send_message(user_id, texts.BC_PREVIEW_DONE)
    await _show_review(bot, user_id, state, db)


async def cb_send(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    recipients = await _recipients(db, callback.from_user.id)
    if not recipients:
        await callback.answer(texts.BC_NO_RECIPIENTS, show_alert=True)
        return
    parts = _parts(await state.get_data())
    await state.set_state(Broadcast.confirm)
    await callback.answer()
    await edit_or_send(
        callback, bot, texts.BC_CONFIRM.format(parts=len(parts), n=len(recipients)), broadcast_confirm_kb()
    )


async def cb_confirm(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    # Single-shot guard (see ``student.reg_confirm``): a double tap must not send everything twice.
    if await state.get_state() != Broadcast.confirm.state:
        await callback.answer(texts.BC_STALE, show_alert=True)
        return
    data = await state.get_data()
    await state.clear()
    parts = _parts(data)
    user_id = callback.from_user.id
    recipients = await _recipients(db, user_id)
    await callback.answer()
    await remove_inline_keyboard(callback)
    log.info("Superadmin %s broadcasts %s parts to %s users", user_id, len(parts), len(recipients))
    status = await bot.send_message(
        user_id, texts.BC_STARTED.format(done=0, total=len(recipients)), reply_markup=await _menu(db, settings, user_id)
    )

    async def progress(done: int, total: int) -> None:
        try:
            await bot.edit_message_text(
                texts.BC_STARTED.format(done=done, total=total), chat_id=user_id, message_id=status.message_id
            )
        except TelegramAPIError as exc:  # progress is best-effort
            log.debug("Broadcast progress update failed: %s", exc)

    report = await run_broadcast(bot, user_id, recipients, parts, progress)
    log.info(
        "Broadcast by %s finished: %s sent, %s blocked, %s failed of %s",
        user_id, report.sent, report.blocked, report.failed, report.total,
    )
    await bot.send_message(
        user_id,
        texts.BC_REPORT.format(total=report.total, sent=report.sent, blocked=report.blocked, failed=report.failed),
    )


async def cb_cancel(callback: CallbackQuery, state: FSMContext, db: Database, settings: Settings, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    await remove_inline_keyboard(callback)
    await bot.send_message(callback.from_user.id, texts.BC_CANCELLED, reply_markup=await _menu(db, settings, callback.from_user.id))


async def cb_stale(callback: CallbackQuery) -> None:
    """A composer button pressed after the composer was finished, cancelled or lost to a restart."""
    await callback.answer(texts.BC_STALE, show_alert=True)


# ------------------------------------------------------------- registration


def create_router() -> Router:
    """Build the broadcast router. A fresh instance is returned on every call (routers cannot be shared)."""
    router = Router(name="broadcast")
    router.message.filter(IsSuperAdmin())
    router.callback_query.filter(IsSuperAdmin())

    msg = router.message
    cb = router.callback_query
    free_text = IsFreeText()
    composing = StateFilter(Broadcast)

    msg.register(cmd_broadcast, Command("broadcast"))
    cb.register(cb_broadcast, AdminCb.filter(F.action == ADM_BROADCAST))

    # Step 1 takes text only; anything else (but commands and menu buttons, which fall through) is refused.
    msg.register(bc_text, Broadcast.text, F.text, free_text)
    msg.register(bc_text_required, Broadcast.text, ~F.text)

    # Steps 2-4, ➕ and the review screen: media, or free text as one more text part; other content is refused.
    msg.register(bc_add_part, _ACCEPTING, F.photo | F.video | F.voice)
    msg.register(bc_add_part, _ACCEPTING, F.text, free_text)
    msg.register(bc_unsupported, _ACCEPTING, ~F.text)

    cb.register(cb_cancel, composing, BcCb.filter(F.action == BC_CANCEL))
    cb.register(cb_skip, StateFilter(Broadcast.photo, Broadcast.video, Broadcast.voice), BcCb.filter(F.action == BC_SKIP))
    cb.register(cb_add, Broadcast.review, BcCb.filter(F.action == BC_ADD))
    cb.register(cb_remove, Broadcast.review, BcCb.filter(F.action == BC_REMOVE))
    cb.register(cb_preview, Broadcast.review, BcCb.filter(F.action == BC_PREVIEW))
    cb.register(cb_send, Broadcast.review, BcCb.filter(F.action == BC_SEND))
    cb.register(cb_review, StateFilter(Broadcast.add, Broadcast.confirm, Broadcast.review), BcCb.filter(F.action == BC_REVIEW))
    cb.register(cb_confirm, Broadcast.confirm, BcCb.filter(F.action == BC_CONFIRM))
    cb.register(cb_stale, BcCb.filter())
    return router
