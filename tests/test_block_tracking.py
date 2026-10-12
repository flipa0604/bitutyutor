"""Who has blocked the bot: recorded from Telegram's own updates, from broadcasts and from staff messages.

Runs through the real Dispatcher with the flow harness from ``tests/test_flows.py``.
User ids: SUPERADMIN=1001, TUTOR=2002, BOTH=3003 (superadmin AND tutor), STUDENT=4004, OTHER_TUTOR=5005.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    Chat,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberUpdated,
    Update,
    User,
)

import bot.broadcast as broadcast_module
from bot import texts
from tests.test_flows import (
    BOTH,
    STUDENT,
    SUPERADMIN,
    TUTOR,
    Harness,
    RegInput,
    _update_ids,
    assert_all_callbacks_answered,
    callback_update,
    h,
    make_user,
    register,
    text_update,
)

__all__ = ["h"]  # the flow harness fixture is re-exported so pytest finds it in this module too

VISITOR = 4007  # pressed /start, never registered
NEVER_STARTED = 4999  # opened the chat and blocked the bot without ever pressing /start

_BOT_USER = User(id=42, is_bot=True, first_name="bot")
_MEMBERS = {
    "kicked": lambda: ChatMemberBanned(user=_BOT_USER, until_date=0),
    "member": lambda: ChatMemberMember(user=_BOT_USER),
    "left": lambda: ChatMemberLeft(user=_BOT_USER),
}


def member_update(user_id: int, status: str, chat_type: str = "private") -> Update:
    """The bot's own membership in ``user_id``'s chat changed to ``status`` (kicked = blocked)."""
    old = "member" if status != "member" else "kicked"
    event = ChatMemberUpdated(
        chat=Chat(id=user_id, type=chat_type),
        from_user=make_user(user_id),
        date=datetime.now(),
        old_chat_member=_MEMBERS[old](),
        new_chat_member=_MEMBERS[status](),
    )
    return Update(update_id=next(_update_ids), my_chat_member=event)


async def blocked(h: Harness, user_id: int) -> bool:
    user = await h.db.get_user(user_id)
    assert user is not None, f"{user_id} is not in users"
    return user.is_blocked


async def seed(h: Harness) -> Any:
    """Tutor TUTOR with group DI-21 holding STUDENT; TUTOR, VISITOR, BOTH and SUPERADMIN pressed /start."""
    tutor = await h.db.add_tutor("Karimov Aziz", TUTOR)
    group = await h.db.add_group(tutor.id, "DI-21")
    await register(h, make_user(STUDENT, username="vali"), tutor.id, group.id, RegInput(full_name="Zokirov Vali"))
    for user_id in (TUTOR, VISITOR, BOTH, SUPERADMIN):
        await h.feed(text_update(make_user(user_id), "/start"))
    student = await h.db.get_student_by_telegram_id(STUDENT)
    assert student is not None
    h.clear()
    return student


# ================================================================== Telegram's my_chat_member


async def test_polling_asks_telegram_for_membership_updates(h: Harness) -> None:
    assert "my_chat_member" in h.dp.resolve_used_update_types()


async def test_blocking_and_restarting_the_bot_are_recorded(h: Harness) -> None:
    await seed(h)

    await h.feed(member_update(STUDENT, "kicked"))
    assert await blocked(h, STUDENT) and await h.db.count_blocked() == 1
    first_seen = (await h.db.get_user(STUDENT)).blocked_at  # type: ignore[union-attr]
    await h.feed(member_update(STUDENT, "kicked"))  # a repeat keeps the first moment
    assert (await h.db.get_user(STUDENT)).blocked_at == first_seen  # type: ignore[union-attr]

    await h.feed(member_update(STUDENT, "member"))  # "Restart"
    assert not await blocked(h, STUDENT) and await h.db.count_blocked() == 0

    # any other status is not about blocking: the mark is left as it was
    await h.feed(member_update(STUDENT, "kicked"), member_update(STUDENT, "left"))
    assert await blocked(h, STUDENT)

    # nothing is ever sent in reply
    assert h.messages(STUDENT) == []


async def test_membership_updates_outside_private_chats_and_of_strangers_are_ignored(h: Harness) -> None:
    await seed(h)

    # the same id in a group chat is not the user's private chat with the bot
    for chat_type in ("group", "supergroup"):
        await h.feed(member_update(VISITOR, "kicked", chat_type=chat_type))
    assert not await blocked(h, VISITOR)

    # someone who never pressed /start does not become a bot user by blocking it
    await h.feed(member_update(NEVER_STARTED, "kicked"))
    assert await h.db.get_user(NEVER_STARTED) is None
    assert await h.db.count_users() == (5, 1)
    assert await h.db.count_blocked() == 0


async def test_pressing_start_clears_a_mark(h: Harness) -> None:
    await seed(h)
    await h.feed(member_update(VISITOR, "kicked"))
    assert await blocked(h, VISITOR)
    await h.feed(text_update(make_user(VISITOR), "/start"))
    assert not await blocked(h, VISITOR)


# ================================================================== broadcast


async def test_broadcast_marks_the_blocked_and_clears_whoever_got_it(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(broadcast_module, "SEND_DELAY", 0)
    await seed(h)
    # BOTH was marked earlier but has come back since; VISITOR was marked too, and this time the copy
    # fails for an unrelated reason, which proves nothing either way
    await h.db.set_blocked([BOTH, VISITOR], True)
    original = type(h.session).make_request

    async def failing(self_session: Any, bot: Any, method: Any, timeout: Any = None) -> Any:
        if type(method).__name__ == "CopyMessage":
            chat_id = int(method.chat_id)
            if chat_id == STUDENT:
                raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
            if chat_id == VISITOR:
                raise TelegramBadRequest(method=method, message="Bad Request: chat not found")
        return await original(self_session, bot, method, timeout)

    monkeypatch.setattr(type(h.session), "make_request", failing)
    admin = make_user(SUPERADMIN)
    await h.feed(text_update(admin, "/broadcast"), text_update(admin, "Salom!"))
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    await h.feed(callback_update(admin, "bc:send:"), callback_update(admin, "bc:go:"))

    assert h.last_text(SUPERADMIN) == texts.BC_REPORT.format(total=4, sent=2, blocked=1, failed=1)
    assert {uid: await blocked(h, uid) for uid in (TUTOR, STUDENT, VISITOR, BOTH, SUPERADMIN)} == {
        TUTOR: False,
        STUDENT: True,  # refused: newly marked
        VISITOR: True,  # failed otherwise: the old mark stays
        BOTH: False,  # delivered: the old mark is cleared
        SUPERADMIN: False,  # the sender is not a recipient
    }
    assert_all_callbacks_answered(h)


async def test_broadcast_still_reaches_users_marked_as_blocked(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sending to everyone is what notices that someone has come back; the mark is not a filter."""
    monkeypatch.setattr(broadcast_module, "SEND_DELAY", 0)
    await seed(h)
    await h.db.set_blocked([STUDENT], True)
    admin = make_user(SUPERADMIN)
    await h.feed(text_update(admin, "/broadcast"), text_update(admin, "Salom!"))
    for _ in range(3):
        await h.feed(callback_update(admin, "bc:skip:"))
    await h.feed(callback_update(admin, "bc:send:"))
    assert h.last_shown(SUPERADMIN).text == texts.BC_CONFIRM.format(parts=1, n=4)
    await h.feed(callback_update(admin, "bc:go:"))
    assert STUDENT in [int(m.chat_id) for m in h.of("CopyMessage")]
    assert not await blocked(h, STUDENT)
    assert_all_callbacks_answered(h)


# ================================================================== staff messages to a student


async def test_messaging_a_blocked_student_marks_them_and_a_delivery_clears_it(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    student = await seed(h)
    tutor_user = make_user(TUTOR)
    admin = make_user(SUPERADMIN)
    original = type(h.session).make_request
    refuse = {"on": True}

    async def failing(self_session: Any, bot: Any, method: Any, timeout: Any = None) -> Any:
        if type(method).__name__ == "SendMessage" and int(method.chat_id) == STUDENT and refuse["on"]:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        return await original(self_session, bot, method, timeout)

    monkeypatch.setattr(type(h.session), "make_request", failing)

    # the tutor's message bounces: the student is marked
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t:basic"), text_update(tutor_user, "Salom"))
    assert h.messages(TUTOR)[-2].text == texts.STUDENT_MESSAGE_BLOCKED
    assert await blocked(h, STUDENT)

    # the student unblocked meanwhile (no update seen): the next delivery clears the mark
    refuse["on"] = False
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t:basic"), text_update(tutor_user, "Salom"))
    assert h.messages(TUTOR)[-2].text == texts.STUDENT_MESSAGE_SENT.format(name="Zokirov Vali")
    assert not await blocked(h, STUDENT)

    # a superadmin deletes the student and the farewell bounces: the users row is marked all the same
    refuse["on"] = True
    await h.feed(
        callback_update(admin, f"stu:del:{student.id}:a:basic"),
        callback_update(admin, f"stu:delok:{student.id}:a:basic"),
        callback_update(admin, f"stu:bye_y:{student.id}:a:basic"),
        text_update(admin, "Xayr"),
    )
    assert h.messages(SUPERADMIN)[-2].text == texts.STUDENT_DELETED_MESSAGE_BLOCKED.format(name="Zokirov Vali")
    gone = await h.db.get_user(STUDENT)
    assert gone is not None and gone.is_blocked and not gone.is_student
    assert_all_callbacks_answered(h)
