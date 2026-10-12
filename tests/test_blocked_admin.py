"""Superadmin tools about reaching people: the blocked list, the 🔄 check of everyone and user search.

Runs through the real Dispatcher with the flow harness from ``tests/test_flows.py``; whether someone
blocked the bot is simulated by refusing ``SendChatAction`` for their chat.
User ids: SUPERADMIN=1001, TUTOR=2002, BOTH=3003 (superadmin AND tutor), STUDENT=4004, OTHER_TUTOR=5005.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import MessageOriginHiddenUser, MessageOriginUser, PhotoSize, Update

from bot import reach, texts
from bot.handlers import blocked as blocked_handlers
from bot.models import Group, Tutor
from bot.states import AdminUserSearch
from tests.test_db import student_kwargs
from tests.test_flows import (
    BOTH,
    STUDENT,
    SUPERADMIN,
    TUTOR,
    Harness,
    _message,
    _update_ids,
    assert_all_callbacks_answered,
    callback_update,
    h,
    inline_buttons,
    make_user,
    reply_button_texts,
    text_update,
)

__all__ = ["h"]  # the flow harness fixture is re-exported so pytest finds it in this module too

VISITOR = 4007  # pressed /start, never registered

ADMIN_MENU = [texts.BTN_ADMIN_PANEL, texts.BTN_REGISTER]
LIST_KB = {"blk:check:0": texts.BTN_BLK_CHECK, "adm:panel:0": texts.BTN_BACK}


@pytest.fixture(autouse=True)
def no_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reach, "CHECK_DELAY", 0)


@dataclass
class Refusals:
    """Chats whose ``SendChatAction`` fails: blocked (403), failed (400), throttled once (429)."""

    blocked: set[int] = field(default_factory=set)
    failed: set[int] = field(default_factory=set)
    throttled_once: set[int] = field(default_factory=set)
    attempts: Counter[int] = field(default_factory=Counter)  # refused attempts included


@pytest.fixture
def refusals(h: Harness, monkeypatch: pytest.MonkeyPatch) -> Refusals:
    refused = Refusals()
    original = type(h.session).make_request

    async def failing(self_session: Any, bot: Any, method: Any, timeout: Any = None) -> Any:
        if type(method).__name__ == "SendChatAction":
            chat_id = int(method.chat_id)
            refused.attempts[chat_id] += 1
            if chat_id in refused.blocked:
                raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
            if chat_id in refused.failed:
                raise TelegramBadRequest(method=method, message="Bad Request: chat not found")
            if chat_id in refused.throttled_once and refused.attempts[chat_id] == 1:
                raise TelegramRetryAfter(method=method, message="Too Many Requests", retry_after=1)
        return await original(self_session, bot, method, timeout)

    monkeypatch.setattr(type(h.session), "make_request", failing)
    return refused


async def seed(h: Harness) -> tuple[Tutor, Group]:
    """Four people who pressed /start: Vali (registered in DI-21), a visitor, the tutor and the admin."""
    tutor = await h.db.add_tutor("Karimov Aziz", TUTOR)
    group = await h.db.add_group(tutor.id, "DI-21")
    await h.db.touch_user(STUDENT, "vali", "Vali 🌟")
    await h.db.upsert_student(
        **student_kwargs(STUDENT, tutor.id, group.id, username="vali", full_name="Aliyev Vali G'aniyevich")
    )
    await h.db.touch_user(VISITOR, "mehmon", "Mehmon")
    await h.db.touch_user(TUTOR, "aziz_tutor", "Aziz")
    await h.db.touch_user(SUPERADMIN, "boss", "Admin")
    h.clear()
    return tutor, group


def chat_actions(h: Harness) -> list[int]:
    """Chats a ``SendChatAction`` went through to (refused ones are not recorded)."""
    return [int(m.chat_id) for m in h.of("SendChatAction")]


async def is_blocked(h: Harness, telegram_id: int) -> bool:
    user = await h.db.get_user(telegram_id)
    assert user is not None
    return user.is_blocked


# ================================================================== the list


async def test_panel_buttons_and_the_empty_list(h: Harness) -> None:
    await seed(h)
    admin = make_user(SUPERADMIN)

    await h.feed(text_update(admin, "/admin"))
    panel = inline_buttons(h.last_message(SUPERADMIN).reply_markup)
    assert panel["adm:find:0"] == texts.BTN_ADMIN_FIND and panel["blk:list:0"] == texts.BTN_ADMIN_BLOCKED

    await h.feed(callback_update(admin, "blk:list:0"))
    shown = h.last_shown(SUPERADMIN)
    assert shown.text == texts.blocked_empty(4)
    assert inline_buttons(shown.reply_markup) == LIST_KB
    await h.feed(text_update(admin, "/blocked"))
    assert h.last_message(SUPERADMIN).text == texts.blocked_empty(4)
    assert chat_actions(h) == []  # looking at the list checks nobody
    assert_all_callbacks_answered(h)


async def test_blocked_list_pages(h: Harness) -> None:
    ids = list(range(9000, 9025))
    for user_id in ids:
        await h.db.touch_user(user_id, f"user{user_id}", f"Foydalanuvchi {user_id}")
    await h.db.set_blocked(ids, True)
    admin = make_user(SUPERADMIN)

    await h.feed(text_update(admin, "/blocked"))
    first = h.last_message(SUPERADMIN)
    assert first.text.startswith(texts.BLOCKED_TITLE.format(n=25, total=25, page=1, pages=2))
    assert first.text.count("<code>") == 20 and first.text.endswith(texts.BLOCKED_NOTE)
    assert inline_buttons(first.reply_markup) == {"blk:list:1": texts.BTN_NEXT, **LIST_KB}

    await h.feed(callback_update(admin, "blk:list:1"))
    second = h.last_shown(SUPERADMIN)
    assert second.text.startswith(texts.BLOCKED_TITLE.format(n=25, total=25, page=2, pages=2))
    assert second.text.count("<code>") == 5 and "\n21. " in second.text and "\n25. " in second.text
    assert inline_buttons(second.reply_markup) == {"blk:list:0": texts.BTN_PREV, **LIST_KB}

    await h.feed(callback_update(admin, "blk:list:9"))  # a stale arrow lands on the last page
    assert "2/2-sahifa" in h.last_shown(SUPERADMIN).text
    assert_all_callbacks_answered(h)


async def test_users_list_counts_and_marks_the_blocked(h: Harness) -> None:
    await seed(h)
    await h.db.set_blocked([VISITOR], True)
    await h.feed(text_update(make_user(SUPERADMIN), "/users"))
    text = h.last_text(SUPERADMIN)
    assert "🚫 bloklagan: <b>1</b> ta" in text and "Jami: <b>4</b> ta" in text
    assert f"🕗🚫 Mehmon @mehmon — <code>{VISITOR}</code>" in text
    assert f"✅ Vali 🌟 @vali — <code>{STUDENT}</code>" in text


# ================================================================== 🔄 check everyone


async def test_check_finds_who_blocked_and_reports(
    h: Harness, refusals: Refusals, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed(h)
    await h.db.touch_user(BOTH, None, "Ikkalasi")
    await h.db.set_blocked([BOTH, VISITOR], True)  # both were marked earlier
    await h.db.conn.execute(f"UPDATE users SET blocked_at = '2000-01-01 00:00:00' WHERE telegram_id = {VISITOR}")
    await h.db.conn.commit()
    refusals.blocked.add(STUDENT)
    refusals.failed.add(VISITOR)
    refusals.throttled_once.add(TUTOR)
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(reach.asyncio, "sleep", fake_sleep)
    admin = make_user(SUPERADMIN)

    await h.feed(callback_update(admin, "blk:check:0"))
    status, report, listing = h.messages(SUPERADMIN)
    assert status.text == texts.BLK_CHECK_STARTED.format(done=0, total=5)
    assert reply_button_texts(status.reply_markup) == ADMIN_MENU
    assert report.text == texts.BLK_CHECK_REPORT.format(
        total=5, reachable=3, blocked=1, newly_blocked=1, unblocked=1, failed=1
    )
    assert refusals.attempts == Counter({STUDENT: 1, VISITOR: 1, TUTOR: 2, BOTH: 1, SUPERADMIN: 1})
    assert slept == [1]  # exactly the wait Telegram asked for (CHECK_DELAY is 0 in tests)

    # Vali is new on the list; the visitor could not be checked, so their old mark stays; BOTH is off it
    assert [await is_blocked(h, u) for u in (STUDENT, VISITOR, TUTOR, BOTH, SUPERADMIN)] == [True, True, False, False, False]
    assert listing.text.startswith(texts.BLOCKED_TITLE.format(n=2, total=5, page=1, pages=1))
    assert f"\n1. Aliyev Vali G'aniyevich @vali — <code>{STUDENT}</code> · 👥 DI-21 · 🕒 20" in listing.text
    assert f"\n2. Mehmon @mehmon — <code>{VISITOR}</code> · 🕒 2000-01-01 00:00\n" in listing.text
    assert inline_buttons(listing.reply_markup) == LIST_KB
    assert_all_callbacks_answered(h)


async def test_check_progress_and_one_check_at_a_time(h: Harness) -> None:
    for index in range(250):
        await h.db.touch_user(9000 + index, None, f"User {index}")
    admin = make_user(SUPERADMIN)

    # another superadmin's check holds the slot: refused, nobody probed
    with reach.exclusive() as held:
        assert held
        await h.feed(callback_update(admin, "blk:check:0"))
    assert h.answers()[-1].text == texts.BLK_CHECK_RUNNING and h.answers()[-1].show_alert
    assert chat_actions(h) == []

    # a double tap: one check runs, the other tap is refused
    h.clear()
    await h.feed_concurrently(callback_update(admin, "blk:check:0"), callback_update(admin, "blk:check:0"))
    assert Counter(a.text for a in h.answers()) == Counter({None: 1, texts.BLK_CHECK_RUNNING: 1})
    assert sorted(chat_actions(h)) == list(range(9000, 9250))  # everyone exactly once
    progress = [m.text for m in h.of("EditMessageText", SUPERADMIN)]
    assert progress == [texts.BLK_CHECK_STARTED.format(done=n, total=250) for n in (100, 200)]
    assert texts.BLK_CHECK_REPORT.format(
        total=250, reachable=250, blocked=0, newly_blocked=0, unblocked=0, failed=0
    ) in h.texts_to(SUPERADMIN)
    with reach.exclusive() as free:  # given back at the end
        assert free
    assert_all_callbacks_answered(h)


async def test_check_with_nobody_to_check(h: Harness) -> None:
    await h.feed(callback_update(make_user(SUPERADMIN), "blk:check:0"))
    assert h.answers()[-1].text == texts.USERS_EMPTY and h.answers()[-1].show_alert
    assert chat_actions(h) == []
    with reach.exclusive() as free:
        assert free
    assert_all_callbacks_answered(h)


# ================================================================== search


async def test_search_from_the_panel_checks_live_and_stays_open(h: Harness, refusals: Refusals) -> None:
    await seed(h)
    refusals.blocked.add(STUDENT)
    admin = make_user(SUPERADMIN)

    await h.feed(callback_update(admin, "adm:find:0"))
    prompt = h.last_message(SUPERADMIN)
    assert prompt.text == texts.ASK_USER_SEARCH and reply_button_texts(prompt.reply_markup) == [texts.BTN_CANCEL]
    assert await h.state_of(SUPERADMIN) == AdminUserSearch.query.state

    await h.feed(text_update(admin, "@vali"))
    result = h.last_message(SUPERADMIN)
    stored = await h.db.get_user(STUDENT)
    assert stored is not None and stored.is_blocked  # the live answer is recorded
    assert result.text == "\n\n".join(
        [texts.SEARCH_HEADER.format(query="vali", n=1), texts.search_result(1, stored, True), texts.SEARCH_FOOTER]
    )
    for piece in (
        "1. 👤 <b>Aliyev Vali G'aniyevich</b> @vali",
        texts.SEARCH_TELEGRAM_NAME.format(name="Vali 🌟"),
        f"<code>{STUDENT}</code>",
        texts.SEARCH_SURVEYS.format(surveys=texts.BTN_SURVEY_BASIC),
        texts.SEARCH_GROUP.format(group="DI-21", tutor="Karimov Aziz"),
        texts.SEARCH_STATUS_BLOCKED.format(since=texts.short_time(stored.blocked_at)),
    ):
        assert piece in result.text, piece
    assert reply_button_texts(result.reply_markup) == [texts.BTN_CANCEL]
    assert chat_actions(h) == [] and refusals.attempts == Counter({STUDENT: 1})
    assert await h.state_of(SUPERADMIN) == AdminUserSearch.query.state  # ready for the next query

    # Vali unblocks the bot: the next query (by ID this time) says so and the mark goes
    refusals.blocked.clear()
    await h.feed(text_update(admin, str(STUDENT)))
    assert h.last_text(SUPERADMIN).startswith(texts.SEARCH_HEADER.format(query=str(STUDENT), n=1))
    assert texts.SEARCH_STATUS_REACHABLE in h.last_text(SUPERADMIN)
    assert not await is_blocked(h, STUDENT)

    # someone who never registered
    await h.feed(text_update(admin, "mehmon"))
    shown = h.last_text(SUPERADMIN)
    assert texts.SEARCH_NOT_REGISTERED in shown and texts.SEARCH_STATUS_REACHABLE in shown
    assert texts.SEARCH_TELEGRAM_NAME.split("{")[0] not in shown  # one name only

    await h.feed(text_update(admin, texts.BTN_CANCEL))
    cancelled = h.last_message(SUPERADMIN)
    assert cancelled.text == texts.CANCELLED and reply_button_texts(cancelled.reply_markup) == ADMIN_MENU
    assert await h.state_of(SUPERADMIN) is None
    assert_all_callbacks_answered(h)


async def test_find_command_links_names_and_forwards(h: Harness, refusals: Refusals) -> None:
    await seed(h)
    admin = make_user(SUPERADMIN)

    await h.feed(text_update(admin, "/find vali"))  # searches at once and stays open
    assert h.last_text(SUPERADMIN).startswith(texts.SEARCH_HEADER.format(query="vali", n=1))
    assert await h.state_of(SUPERADMIN) == AdminUserSearch.query.state
    await h.feed(text_update(admin, "/find"))
    assert h.last_text(SUPERADMIN) == texts.ASK_USER_SEARCH

    for typed, query in (
        ("https://t.me/vali", "vali"),
        ("aliyev", "aliyev"),  # the questionnaire's F.I.SH
        ("  ALIYEV   vali ", "ALIYEV vali"),
        ("Vali 🌟", "Vali 🌟"),  # the Telegram profile's name
    ):
        await h.feed(text_update(admin, typed))
        shown = h.last_text(SUPERADMIN)
        assert shown.startswith(texts.SEARCH_HEADER.format(query=query, n=1)), typed
        assert f"<code>{STUDENT}</code>" in shown, typed

    # a forwarded message searches by its sender; a hidden sender is explained
    origin = MessageOriginUser(type="user", date=datetime.now(), sender_user=make_user(VISITOR))
    await h.feed(Update(update_id=next(_update_ids), message=_message(admin, text="salom", forward_origin=origin)))
    assert h.last_text(SUPERADMIN).startswith(texts.SEARCH_HEADER.format(query=str(VISITOR), n=1))
    hidden = MessageOriginHiddenUser(type="hidden_user", date=datetime.now(), sender_user_name="X")
    await h.feed(Update(update_id=next(_update_ids), message=_message(admin, text="salom", forward_origin=hidden)))
    assert h.last_text(SUPERADMIN) == texts.SEARCH_FORWARD_HIDDEN

    # what cannot be searched; the search stays open through all of it
    for typed in ("@a", "t.me/", "x" * 65):
        await h.feed(text_update(admin, typed))
        assert h.last_text(SUPERADMIN) == texts.SEARCH_QUERY_INVALID.format(min=2, max=64), typed
    photo = [PhotoSize(file_id="p", file_unique_id="pu", width=1, height=1)]
    await h.feed(Update(update_id=next(_update_ids), message=_message(admin, photo=photo)))
    assert h.last_text(SUPERADMIN) == texts.SEARCH_TEXT_ONLY
    await h.feed(text_update(admin, "hech_kim"))
    assert h.last_text(SUPERADMIN) == texts.SEARCH_NOT_FOUND.format(query="hech_kim")
    assert await h.state_of(SUPERADMIN) == AdminUserSearch.query.state

    # commands and menu buttons are not queries: they do their own thing and end the search
    await h.feed(text_update(admin, "/admin"))
    assert h.last_text(SUPERADMIN) == texts.ADMIN_PANEL and await h.state_of(SUPERADMIN) is None
    assert sorted(refusals.attempts) == [STUDENT, VISITOR]  # only found users were checked


async def test_search_falls_back_to_what_is_stored_when_telegram_does_not_answer(
    h: Harness, refusals: Refusals
) -> None:
    await seed(h)
    await h.db.set_blocked([STUDENT], True)
    before = await h.db.get_user(STUDENT)
    assert before is not None and before.blocked_at
    refusals.failed.update({STUDENT, VISITOR})
    admin = make_user(SUPERADMIN)

    await h.feed(text_update(admin, "/find vali"))
    assert texts.SEARCH_STATUS_UNKNOWN_BLOCKED.format(since=texts.short_time(before.blocked_at)) in h.last_text(SUPERADMIN)
    after = await h.db.get_user(STUDENT)
    assert after is not None and after.blocked_at == before.blocked_at  # nothing changed
    await h.feed(text_update(admin, "mehmon"))
    assert texts.SEARCH_STATUS_UNKNOWN in h.last_text(SUPERADMIN)
    assert not await is_blocked(h, VISITOR)


async def test_search_shows_ten_and_says_there_are_more(h: Harness) -> None:
    for index in range(1, 13):
        await h.db.touch_user(9000 + index, f"talaba{index:02d}", f"Talaba {index}")
    admin = make_user(SUPERADMIN)

    await h.feed(text_update(admin, "/find talaba"))
    shown = h.last_text(SUPERADMIN)
    assert shown.startswith(texts.SEARCH_HEADER_MORE.format(query="talaba", limit=10))
    assert "\n10. 👤" in shown and "\n11. 👤" not in shown
    assert shown.endswith(f"{texts.SEARCH_MORE_HINT}\n{texts.SEARCH_FOOTER}")
    assert len(chat_actions(h)) == 10  # only the users shown are checked


def test_long_results_are_split_between_messages() -> None:
    chunks = blocked_handlers._chunks(["a" * 2000, "b" * 1400, "c" * 200, "d"], budget=3500)
    assert chunks == ["a" * 2000 + "\n\n" + "b" * 1400, "c" * 200 + "\n\nd"]
    assert blocked_handlers._chunks(["x" * 5000]) == ["x" * 5000]  # a block is never cut
    assert blocked_handlers._chunks([]) == []


# ================================================================== access


async def test_only_superadmins(h: Harness) -> None:
    await seed(h)
    tutor_user = make_user(TUTOR)
    for command in ("/blocked", "/find", "/find vali"):
        await h.feed(text_update(tutor_user, command))
        assert h.last_text(TUTOR) == texts.ADMIN_ONLY, command
    await h.feed(
        callback_update(tutor_user, "blk:list:0"),
        callback_update(tutor_user, "blk:check:0"),
        callback_update(tutor_user, "adm:find:0"),
    )
    assert [a.text for a in h.answers()][-3:] == [texts.STALE_BUTTON] * 3
    assert chat_actions(h) == [] and await h.state_of(TUTOR) is None

    help_text = texts.help_text(is_admin=True, is_tutor=False)
    assert "/blocked" in help_text and "/find" in help_text
    assert "/blocked" not in texts.help_text(is_admin=False, is_tutor=True)
    assert_all_callbacks_answered(h)
