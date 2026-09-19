"""Superadmin broadcast: composing parts step by step, reviewing, previewing and copying to everyone.

Runs through the real Dispatcher with the flow harness from ``tests/test_flows.py``.
User ids: SUPERADMIN=1001, TUTOR=2002, BOTH=3003 (superadmin AND tutor), STUDENT=4004, OTHER_TUTOR=5005.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import Chat, Document, Message, PhotoSize, Update, User, Video, Voice

import bot.broadcast as broadcast_module
from bot import texts
from bot.broadcast import MAX_PARTS, Part, part_from_message, summarize
from bot.states import Broadcast
from tests.test_flows import (
    BOTH,
    STUDENT,
    SUPERADMIN,
    TUTOR,
    Harness,
    _message_ids,
    _update_ids,
    assert_all_callbacks_answered,
    callback_update,
    h,
    inline_buttons,
    make_user,
    register,
    reply_button_texts,
    text_update,
)

__all__ = ["h"]  # the flow harness fixture is re-exported so pytest finds it in this module too

VISITOR = 4007  # pressed /start, never registered

ADMIN_MENU = [texts.BTN_ADMIN_PANEL, texts.BTN_REGISTER]


def _media_update(user: User, **fields: Any) -> Update:
    message = Message(
        message_id=next(_message_ids),
        date=datetime.now(),
        chat=Chat(id=user.id, type="private"),
        from_user=user,
        **fields,
    )
    return Update(update_id=next(_update_ids), message=message)


def photo_update(user: User, caption: str | None = None) -> Update:
    return _media_update(user, photo=[PhotoSize(file_id="p", file_unique_id="pu", width=1, height=1)], caption=caption)


def video_update(user: User) -> Update:
    return _media_update(user, video=Video(file_id="v", file_unique_id="vu", width=1, height=1, duration=1))


def voice_update(user: User) -> Update:
    return _media_update(user, voice=Voice(file_id="a", file_unique_id="au", duration=1))


def document_update(user: User) -> Update:
    return _media_update(user, document=Document(file_id="d", file_unique_id="du"))


async def seed_audience(h: Harness) -> list[int]:
    """Everyone who ever started the bot: a tutor, a registered student, a visitor, a second superadmin
    who is also a tutor, and the sending superadmin (who is not a recipient)."""
    tutor = await h.db.add_tutor("Karimov Aziz", TUTOR)
    group = await h.db.add_group(tutor.id, "DI-21")
    await h.db.add_tutor("Ikkalasi Ham", BOTH)
    await register(h, make_user(STUDENT), tutor.id, group.id)
    for user_id in (TUTOR, VISITOR, BOTH, SUPERADMIN):
        await h.feed(text_update(make_user(user_id), "/start"))
    h.clear()
    return sorted({TUTOR, STUDENT, VISITOR, BOTH})


@pytest.fixture(autouse=True)
def no_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(broadcast_module, "SEND_DELAY", 0)


def copies(h: Harness) -> list[tuple[int, int, int]]:
    """``(to, from, message_id)`` of every CopyMessage so far."""
    return [(int(m.chat_id), int(m.from_chat_id), int(m.message_id)) for m in h.of("CopyMessage")]


# ================================================================== units


def test_part_from_message_and_summary() -> None:
    admin = make_user(SUPERADMIN)
    opening = text_update(admin, "  Salom   hammaga!\nErtaga  dars.").message
    assert part_from_message(opening) == Part("text", opening.message_id, "Salom hammaga! Ertaga dars.")
    photo = part_from_message(photo_update(admin, caption="Rasm izohi").message)
    assert photo is not None and photo.kind == "photo" and photo.summary == "Rasm izohi"
    assert part_from_message(video_update(admin).message).kind == "video"  # type: ignore[union-attr]
    assert part_from_message(voice_update(admin).message).kind == "voice"  # type: ignore[union-attr]
    assert part_from_message(document_update(admin).message) is None
    assert summarize("x" * 100) == "x" * 59 + "…"
    assert summarize(None) == ""
    assert Part.from_data(Part("text", 5, "s").to_data()) == Part("text", 5, "s")


# ================================================================== the full flow


async def test_compose_review_preview_and_send_to_everyone(h: Harness) -> None:
    recipients = await seed_audience(h)
    admin = make_user(SUPERADMIN)

    await h.feed(text_update(admin, "/admin"))
    panel = inline_buttons(h.last_message(SUPERADMIN).reply_markup)
    assert panel["adm:broadcast:0"] == texts.BTN_ADMIN_BROADCAST
    await h.feed(callback_update(admin, "adm:broadcast:0"))
    prompt = h.last_message(SUPERADMIN)
    assert prompt.text == texts.BC_ASK_TEXT and reply_button_texts(prompt.reply_markup) == [texts.BTN_CANCEL]
    assert await h.state_of(SUPERADMIN) == Broadcast.text.state

    # step 1: text is mandatory
    await h.feed(photo_update(admin))
    assert h.last_text(SUPERADMIN) == texts.BC_TEXT_REQUIRED
    assert await h.state_of(SUPERADMIN) == Broadcast.text.state
    opening = text_update(admin, "<b>Diqqat!</b> Ertaga dars 9:00 da boshlanadi.")
    await h.feed(opening)
    assert h.last_text(SUPERADMIN) == texts.BC_ASK_PHOTO
    assert inline_buttons(h.last_message(SUPERADMIN).reply_markup) == {"bc:skip:": texts.BTN_BC_SKIP}
    assert await h.state_of(SUPERADMIN) == Broadcast.photo.state

    # step 2: two photos, then on
    first_photo = photo_update(admin, caption="Jadval")
    second_photo = photo_update(admin)
    await h.feed(first_photo)
    assert h.last_text(SUPERADMIN) == texts.BC_PART_ADDED.format(label="🖼 Rasm", n=2)
    assert inline_buttons(h.last_message(SUPERADMIN).reply_markup) == {"bc:skip:": texts.BTN_BC_CONTINUE}
    await h.feed(second_photo)
    assert h.last_text(SUPERADMIN) == texts.BC_PART_ADDED.format(label="🖼 Rasm", n=3)
    await h.feed(callback_update(admin, "bc:skip:"))
    assert h.last_text(SUPERADMIN) == texts.BC_ASK_VIDEO and await h.state_of(SUPERADMIN) == Broadcast.video.state

    # step 3: unsupported content is refused, the step is skipped
    await h.feed(document_update(admin))
    assert h.last_text(SUPERADMIN) == texts.BC_UNSUPPORTED
    await h.feed(callback_update(admin, "bc:skip:"))
    assert h.last_text(SUPERADMIN) == texts.BC_ASK_VOICE and await h.state_of(SUPERADMIN) == Broadcast.voice.state

    # step 4: a voice note, then the review
    voice = voice_update(admin)
    await h.feed(voice, callback_update(admin, "bc:skip:"))
    review = h.last_message(SUPERADMIN)
    assert await h.state_of(SUPERADMIN) == Broadcast.review.state
    assert review.text.startswith(texts.BC_REVIEW_TITLE)
    assert "1. 📝 Matn — «&lt;b&gt;Diqqat!&lt;/b&gt; Ertaga dars 9:00 da boshlanadi.»" in review.text
    assert "2. 🖼 Rasm — «Jadval»" in review.text and "3. 🖼 Rasm\n" in review.text and "4. 🎤 Ovozli xabar" in review.text
    assert texts.BC_REVIEW_FOOTER.format(n=len(recipients)) in review.text
    kb = inline_buttons(review.reply_markup)
    assert kb == {
        "bc:add:text": texts.BTN_BC_ADD_TEXT,
        "bc:add:photo": texts.BTN_BC_ADD_PHOTO,
        "bc:add:video": texts.BTN_BC_ADD_VIDEO,
        "bc:add:voice": texts.BTN_BC_ADD_VOICE,
        "bc:rm:": texts.BTN_BC_REMOVE_LAST,
        "bc:preview:": texts.BTN_BC_PREVIEW,
        "bc:send:": texts.BTN_BC_SEND,
        "bc:cancel:": texts.BTN_CANCEL,
    }

    # ➕ another text, then a video via ➕ (whatever is sent is taken), then drop the video again
    await h.feed(callback_update(admin, "bc:add:text"))
    assert h.last_shown(SUPERADMIN).text == texts.BC_ASK_MORE.format(label="📝 Matn")
    assert inline_buttons(h.last_shown(SUPERADMIN).reply_markup) == {"bc:review:": texts.BTN_BACK}
    assert await h.state_of(SUPERADMIN) == Broadcast.add.state
    extra_text = text_update(admin, "Savollar bo'lsa tyutoringizga yozing.")
    await h.feed(extra_text)
    assert "5. 📝 Matn — «Savollar bo'lsa tyutoringizga yozing.»" in h.last_message(SUPERADMIN).text
    assert await h.state_of(SUPERADMIN) == Broadcast.review.state
    await h.feed(callback_update(admin, "bc:add:photo"), video_update(admin))
    assert "6. 🎬 Video" in h.last_message(SUPERADMIN).text
    await h.feed(callback_update(admin, "bc:rm:"))
    assert "6. 🎬 Video" not in h.last_shown(SUPERADMIN).text and "5. 📝 Matn" in h.last_shown(SUPERADMIN).text
    await h.feed(voice_update(admin))  # sent straight from the review, without ➕: taken all the same
    assert "6. 🎤 Ovozli xabar" in h.last_message(SUPERADMIN).text
    await h.feed(callback_update(admin, "bc:rm:"))
    assert "6. 🎤" not in h.last_shown(SUPERADMIN).text

    # 👁 preview: every part is copied to the admin, in order
    h.clear()
    await h.feed(callback_update(admin, "bc:preview:"))
    expected_ids = [
        opening.message.message_id,
        first_photo.message.message_id,
        second_photo.message.message_id,
        voice.message.message_id,
        extra_text.message.message_id,
    ]
    assert copies(h) == [(SUPERADMIN, SUPERADMIN, mid) for mid in expected_ids]
    assert texts.BC_PREVIEW_DONE in h.texts_to(SUPERADMIN)
    assert h.last_message(SUPERADMIN).text.startswith(texts.BC_REVIEW_TITLE)

    # 📤 → confirmation → sent to everyone but the sender, parts in order, then a report
    h.clear()
    await h.feed(callback_update(admin, "bc:send:"))
    assert h.last_shown(SUPERADMIN).text == texts.BC_CONFIRM.format(parts=5, n=len(recipients))
    assert inline_buttons(h.last_shown(SUPERADMIN).reply_markup) == {
        "bc:go:": texts.BTN_BC_CONFIRM,
        "bc:review:": texts.BTN_BACK,
    }
    assert await h.state_of(SUPERADMIN) == Broadcast.confirm.state
    await h.feed(callback_update(admin, "bc:go:"))
    assert copies(h) == [(user_id, SUPERADMIN, mid) for user_id in recipients for mid in expected_ids]
    sent = h.messages(SUPERADMIN)
    assert sent[0].text == texts.BC_STARTED.format(done=0, total=len(recipients))
    assert reply_button_texts(sent[0].reply_markup) == ADMIN_MENU
    assert sent[-1].text == texts.BC_REPORT.format(total=len(recipients), sent=len(recipients), blocked=0, failed=0)
    assert await h.state_of(SUPERADMIN) is None

    # the composer is gone: its buttons say so, and a second ✅ cannot send everything again
    await h.feed(callback_update(admin, "bc:go:"), callback_update(admin, "bc:add:text"))
    assert [a.text for a in h.answers()][-2:] == [texts.BC_STALE, texts.BC_STALE]
    assert len(copies(h)) == len(recipients) * len(expected_ids)
    assert_all_callbacks_answered(h)


async def test_broadcast_command_and_minimal_message(h: Harness) -> None:
    recipients = await seed_audience(h)
    admin = make_user(SUPERADMIN)

    opening = text_update(admin, "Salom!")
    await h.feed(text_update(admin, "/broadcast"), opening)
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    assert await h.state_of(SUPERADMIN) == Broadcast.review.state
    assert "bc:rm:" not in inline_buttons(h.last_message(SUPERADMIN).reply_markup)  # the text alone cannot go
    await h.feed(callback_update(admin, "bc:rm:"))
    assert h.answers()[-1].text == texts.BC_NOTHING_TO_REMOVE and h.answers()[-1].show_alert

    h.clear()
    await h.feed(callback_update(admin, "bc:send:"), callback_update(admin, "bc:go:"))
    assert copies(h) == [(user_id, SUPERADMIN, opening.message.message_id) for user_id in recipients]
    assert h.last_text(SUPERADMIN) == texts.BC_REPORT.format(total=len(recipients), sent=len(recipients), blocked=0, failed=0)
    assert "/broadcast" in texts.help_text(is_admin=True, is_tutor=False)
    assert_all_callbacks_answered(h)


async def test_concurrent_double_tap_sends_once(h: Harness) -> None:
    recipients = await seed_audience(h)
    admin = make_user(SUPERADMIN)
    await h.feed(text_update(admin, "/broadcast"), text_update(admin, "Salom!"))
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    await h.feed(callback_update(admin, "bc:send:"))
    h.clear()

    await h.feed_concurrently(callback_update(admin, "bc:go:"), callback_update(admin, "bc:go:"))
    assert Counter(a.text for a in h.answers()) == Counter({None: 1, texts.BC_STALE: 1})
    assert len(copies(h)) == len(recipients)
    assert_all_callbacks_answered(h)


# ================================================================== delivery outcomes


async def test_report_counts_blocked_and_failed_recipients(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    recipients = await seed_audience(h)
    admin = make_user(SUPERADMIN)
    original = type(h.session).make_request
    attempts: Counter[int] = Counter()  # CopyMessage attempts per chat, the refused ones included

    async def failing(self_session: Any, bot: Any, method: Any, timeout: Any = None) -> Any:
        if type(method).__name__ == "CopyMessage":
            chat_id = int(method.chat_id)
            attempts[chat_id] += 1
            if chat_id == STUDENT:
                raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
            if chat_id == VISITOR:
                raise TelegramBadRequest(method=method, message="Bad Request: chat not found")
            if chat_id == TUTOR and attempts[TUTOR] == 1:  # throttled once, then fine
                raise TelegramRetryAfter(method=method, message="Too Many Requests", retry_after=1)
        return await original(self_session, bot, method, timeout)

    monkeypatch.setattr(type(h.session), "make_request", failing)
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(broadcast_module.asyncio, "sleep", fake_sleep)

    opening = text_update(admin, "Salom!")
    photo = photo_update(admin)
    await h.feed(text_update(admin, "/broadcast"), opening, photo)
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    h.clear()
    await h.feed(callback_update(admin, "bc:send:"), callback_update(admin, "bc:go:"))

    assert attempts[STUDENT] == 1  # blocked on the first part: the second is not even attempted
    assert attempts[VISITOR] == 1
    assert attempts[TUTOR] == 3  # one throttled attempt + both parts
    assert attempts[BOTH] == 2
    assert Counter(to for to, _, _ in copies(h)) == Counter({TUTOR: 2, BOTH: 2})  # what actually went through
    assert slept == [1]  # exactly the wait Telegram asked for (SEND_DELAY is 0 in tests)
    assert h.last_text(SUPERADMIN) == texts.BC_REPORT.format(total=len(recipients), sent=2, blocked=1, failed=1)
    assert_all_callbacks_answered(h)


async def test_preview_reports_a_deleted_source_message(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    await seed_audience(h)
    admin = make_user(SUPERADMIN)
    original = type(h.session).make_request

    async def failing(self_session: Any, bot: Any, method: Any, timeout: Any = None) -> Any:
        if type(method).__name__ == "CopyMessage":
            raise TelegramBadRequest(method=method, message="Bad Request: message to copy not found")
        return await original(self_session, bot, method, timeout)

    monkeypatch.setattr(type(h.session), "make_request", failing)
    await h.feed(text_update(admin, "/broadcast"), text_update(admin, "Salom!"))
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    await h.feed(callback_update(admin, "bc:preview:"))
    shown = h.texts_to(SUPERADMIN)
    assert texts.BC_PREVIEW_FAILED.format(label="📝 Matn") in shown and texts.BC_PREVIEW_DONE in shown
    assert await h.state_of(SUPERADMIN) == Broadcast.review.state
    assert_all_callbacks_answered(h)


async def test_no_recipients(h: Harness) -> None:
    admin = make_user(SUPERADMIN)
    await h.feed(text_update(admin, "/start"))  # only the sender has ever started the bot
    await h.feed(text_update(admin, "/broadcast"), text_update(admin, "Salom!"))
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    assert texts.BC_REVIEW_FOOTER.format(n=0) in h.last_message(SUPERADMIN).text
    await h.feed(callback_update(admin, "bc:send:"))
    assert h.answers()[-1].text == texts.BC_NO_RECIPIENTS and h.answers()[-1].show_alert
    assert await h.state_of(SUPERADMIN) == Broadcast.review.state
    assert copies(h) == []
    assert_all_callbacks_answered(h)


# ================================================================== limits, cancel, access


async def test_part_limit(h: Harness) -> None:
    await seed_audience(h)
    admin = make_user(SUPERADMIN)
    await h.feed(text_update(admin, "/broadcast"), text_update(admin, "Salom!"))
    for _ in range(MAX_PARTS - 1):
        await h.feed(photo_update(admin))
    assert h.last_text(SUPERADMIN) == texts.BC_PART_ADDED.format(label="🖼 Rasm", n=MAX_PARTS)
    await h.feed(photo_update(admin))
    assert h.last_text(SUPERADMIN) == texts.BC_TOO_MANY_PARTS.format(max=MAX_PARTS)
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    await h.feed(callback_update(admin, "bc:add:video"))
    assert h.answers()[-1].text == texts.BC_TOO_MANY_PARTS.format(max=MAX_PARTS) and h.answers()[-1].show_alert
    assert await h.state_of(SUPERADMIN) == Broadcast.review.state
    assert_all_callbacks_answered(h)


async def test_cancel_paths_send_nothing(h: Harness) -> None:
    await seed_audience(h)
    admin = make_user(SUPERADMIN)

    await h.feed(text_update(admin, "/broadcast"), text_update(admin, texts.BTN_CANCEL))
    assert h.last_text(SUPERADMIN) == texts.CANCELLED and await h.state_of(SUPERADMIN) is None

    await h.feed(text_update(admin, "/broadcast"), text_update(admin, "Salom!"), text_update(admin, "/admin"))
    assert h.last_text(SUPERADMIN) == texts.ADMIN_PANEL and await h.state_of(SUPERADMIN) is None

    await h.feed(text_update(admin, "/broadcast"), text_update(admin, "Salom!"))
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    await h.feed(callback_update(admin, "bc:send:"), callback_update(admin, "bc:review:"))
    assert await h.state_of(SUPERADMIN) == Broadcast.review.state  # back from the confirmation
    await h.feed(callback_update(admin, "bc:cancel:"))
    cancelled = h.last_message(SUPERADMIN)
    assert cancelled.text == texts.BC_CANCELLED and reply_button_texts(cancelled.reply_markup) == ADMIN_MENU
    assert await h.state_of(SUPERADMIN) is None
    assert copies(h) == []
    assert_all_callbacks_answered(h)


async def test_only_superadmins_can_broadcast(h: Harness) -> None:
    await seed_audience(h)
    tutor_user = make_user(TUTOR)
    await h.feed(text_update(tutor_user, "/broadcast"))
    assert h.last_text(TUTOR) == texts.ADMIN_ONLY
    await h.feed(callback_update(tutor_user, "adm:broadcast:0"), callback_update(tutor_user, "bc:go:"))
    assert [a.text for a in h.answers()][-2:] == [texts.STALE_BUTTON, texts.STALE_BUTTON]
    assert copies(h) == [] and await h.state_of(TUTOR) is None
    assert_all_callbacks_answered(h)
