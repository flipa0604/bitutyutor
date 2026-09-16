"""Student management by tutors and superadmins: browse a group, message a student, delete a student.

Runs through the real Dispatcher with the flow harness from ``tests/test_flows.py``.
User ids: SUPERADMIN=1001, TUTOR=2002, BOTH=3003 (superadmin AND tutor), STUDENT=4004, OTHER_TUTOR=5005.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Chat, Message, PhotoSize, Update, User

from bot import texts
from bot.handlers.manage import MESSAGE_MAX_LEN
from bot.states import Registration, StudentManage
from tests.test_flows import (
    BOTH,
    OTHER_TUTOR,
    STUDENT,
    SUPERADMIN,
    TUTOR,
    Harness,
    RegInput,
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

SECOND_STUDENT = 4005
STRANGER = 4006  # neither tutor nor superadmin nor registered

TUTOR_MENU = [texts.BTN_TUTOR_PANEL, texts.BTN_REGISTER]
ADMIN_MENU = [texts.BTN_ADMIN_PANEL, texts.BTN_REGISTER]


def photo_update(user: User) -> Update:
    """A photo without a caption: ``message.text`` is ``None``."""
    message = Message(
        message_id=next(_message_ids),
        date=datetime.now(),
        chat=Chat(id=user.id, type="private"),
        from_user=user,
        photo=[PhotoSize(file_id="p", file_unique_id="pu", width=1, height=1)],
    )
    return Update(update_id=next(_update_ids), message=message)


def tutor_sender(name: str) -> str:
    return texts.MESSAGE_SENDER_TUTOR.format(name=name)


def student_message(sender: str, text: str, removed_from: str | None = None) -> str:
    note = texts.MESSAGE_REMOVED_LINE.format(group=removed_from) if removed_from else ""
    return texts.MESSAGE_TO_STUDENT.format(sender=sender, note=note, text=text)


async def seed(h: Harness) -> tuple[Any, Any, Any]:
    """Tutor TUTOR with group DI-21 holding one registered student (STUDENT); recorder cleared."""
    tutor = await h.db.add_tutor("Karimov Aziz", TUTOR)
    group = await h.db.add_group(tutor.id, "DI-21")
    await register(h, make_user(STUDENT, username="vali"), tutor.id, group.id, RegInput(full_name="Zokirov Vali"))
    student = await h.db.get_student_by_telegram_id(STUDENT)
    assert student is not None
    h.clear()
    return tutor, group, student


# ================================================================== navigation


async def test_tutor_reaches_students_from_panel_command_and_group_card(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)

    await h.feed(text_update(tutor_user, "/tutor"))
    panel = inline_buttons(h.last_message(TUTOR).reply_markup)
    assert panel["tut:students:0:"] == texts.BTN_GROUP_STUDENTS
    await h.feed(callback_update(tutor_user, "tut:students:0:"))
    picker = h.last_shown(TUTOR)
    assert picker.text == texts.STUDENT_PICK_GROUP
    assert inline_buttons(picker.reply_markup) == {
        f"stu:list:{group.id}:t": "DI-21 — 1 ta talaba",
        "tut:panel:0:": texts.BTN_BACK,
    }

    await h.feed(text_update(tutor_user, "/students"))
    assert h.last_message(TUTOR).text == texts.STUDENT_PICK_GROUP
    assert f"stu:list:{group.id}:t" in inline_buttons(h.last_message(TUTOR).reply_markup)

    await h.feed(callback_update(tutor_user, f"tut:view:{group.id}:"))
    card_kb = inline_buttons(h.last_shown(TUTOR).reply_markup)
    assert card_kb[f"stu:list:{group.id}:t"] == texts.BTN_GROUP_STUDENTS

    await h.feed(callback_update(tutor_user, f"stu:list:{group.id}:t"))
    listing = h.last_shown(TUTOR)
    assert listing.text == texts.STUDENT_LIST_TITLE.format(group="DI-21", n=1, tutor="")
    assert inline_buttons(listing.reply_markup) == {
        f"stu:view:{student.id}:t": "Zokirov Vali",
        f"tut:view:{group.id}:": texts.BTN_BACK,
    }

    await h.feed(callback_update(tutor_user, f"stu:view:{student.id}:t"))
    card = h.last_shown(TUTOR)
    assert card.text.startswith(texts.STUDENT_CARD_TITLE)
    assert "Zokirov Vali" in card.text and "+998901234567" in card.text and "DI-21" in card.text
    assert inline_buttons(card.reply_markup) == {
        f"stu:msg:{student.id}:t": texts.BTN_SEND_MESSAGE,
        f"stu:del:{student.id}:t": texts.BTN_DELETE,
        f"stu:list:{group.id}:t": texts.BTN_BACK,
    }

    # an empty group says so and still offers the way back
    empty = await h.db.add_group(tutor.id, "DI-22")
    await h.feed(callback_update(tutor_user, f"stu:list:{empty.id}:t"))
    shown = h.last_shown(TUTOR)
    assert shown.text == texts.STUDENT_LIST_EMPTY.format(group="DI-22", tutor="")
    assert inline_buttons(shown.reply_markup) == {f"tut:view:{empty.id}:": texts.BTN_BACK}

    assert "/students" in texts.help_text(is_admin=False, is_tutor=True)
    assert_all_callbacks_answered(h)


async def test_students_command_is_refused_for_non_tutors(h: Harness) -> None:
    await h.feed(text_update(make_user(STRANGER), "/students"))
    assert h.last_text(STRANGER) == texts.TUTOR_ONLY


# ================================================================== messaging


async def test_tutor_messages_a_student(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)

    await h.feed(callback_update(tutor_user, f"stu:view:{student.id}:t"))
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"))
    assert h.of("EditMessageReplyMarkup", TUTOR)  # the card's buttons are taken away
    prompt = h.last_message(TUTOR)
    assert prompt.text == texts.ASK_STUDENT_MESSAGE.format(name="Zokirov Vali")
    assert reply_button_texts(prompt.reply_markup) == [texts.BTN_CANCEL]
    assert await h.state_of(TUTOR) == StudentManage.message_text.state

    # validation: blank, too long, not text at all -- nothing leaves, the prompt stays open
    await h.feed(text_update(tutor_user, "   "))
    assert h.last_text(TUTOR) == texts.STUDENT_MESSAGE_INVALID.format(max=MESSAGE_MAX_LEN)
    await h.feed(text_update(tutor_user, "x" * (MESSAGE_MAX_LEN + 1)))
    assert h.last_text(TUTOR) == texts.STUDENT_MESSAGE_INVALID.format(max=MESSAGE_MAX_LEN)
    await h.feed(photo_update(tutor_user))
    assert h.last_text(TUTOR) == texts.STUDENT_MESSAGE_TEXT_ONLY
    assert h.messages(STUDENT) == []
    assert await h.state_of(TUTOR) == StudentManage.message_text.state

    await h.feed(text_update(tutor_user, "Salom!\nErtaga dars 9:00 da."))
    delivered = h.messages(STUDENT)
    assert len(delivered) == 1
    assert delivered[0].text == student_message(tutor_sender("Karimov Aziz"), "Salom!\nErtaga dars 9:00 da.")
    assert "o'chirildingiz" not in delivered[0].text

    sent = h.messages(TUTOR)
    assert sent[-2].text == texts.STUDENT_MESSAGE_SENT.format(name="Zokirov Vali")
    assert reply_button_texts(sent[-2].reply_markup) == TUTOR_MENU
    assert sent[-1].text.startswith(texts.STUDENT_CARD_TITLE)
    assert f"stu:msg:{student.id}:t" in inline_buttons(sent[-1].reply_markup)
    assert await h.state_of(TUTOR) is None
    assert await h.db.get_student_by_telegram_id(STUDENT) is not None
    assert_all_callbacks_answered(h)


async def test_message_and_names_are_html_escaped(h: Harness) -> None:
    # ``is_valid_name`` accepts ``<``, ``>`` and ``&`` in names, so every screen must escape them
    tutor = await h.db.add_tutor("T&T <i>Karimov", TUTOR)
    group = await h.db.add_group(tutor.id, "DI-21")
    student, _ = await h.db.upsert_student(
        telegram_id=STUDENT,
        username="vali",
        tutor_id=tutor.id,
        group_id=group.id,
        full_name="Ali <b>Valiyev",
        phone="+998901234567",
        direction="Dasturiy injiniring",
        residence="ttj",
        address="TTJ",
        father_name="Ota Otayev",
        father_phone="+998901111111",
        mother_name="Ona Onayeva",
        mother_phone="+998902222222",
    )
    tutor_user = make_user(TUTOR)

    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"))
    assert h.last_text(TUTOR) == texts.ASK_STUDENT_MESSAGE.format(name="Ali &lt;b&gt;Valiyev")
    await h.feed(text_update(tutor_user, "<script>1 & 2</script>"))
    delivered = h.messages(STUDENT)[0].text
    assert "&lt;script&gt;1 &amp; 2&lt;/script&gt;" in delivered
    assert "Kimdan: tyutor T&amp;T &lt;i&gt;Karimov" in delivered
    assert "<script>" not in delivered and "<i>Karimov" not in delivered
    assert h.messages(TUTOR)[-2].text == texts.STUDENT_MESSAGE_SENT.format(name="Ali &lt;b&gt;Valiyev")

    await h.feed(callback_update(tutor_user, f"stu:del:{student.id}:t"))
    assert h.last_shown(TUTOR).text == texts.STUDENT_DELETE_CONFIRM.format(name="Ali &lt;b&gt;Valiyev", group="DI-21")
    assert_all_callbacks_answered(h)


async def test_cancel_commands_and_menu_buttons_preempt_the_prompt(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)

    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"), text_update(tutor_user, "/cancel"))
    assert h.last_text(TUTOR) == texts.CANCELLED and await h.state_of(TUTOR) is None
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"), text_update(tutor_user, texts.BTN_CANCEL))
    assert h.last_text(TUTOR) == texts.CANCELLED and await h.state_of(TUTOR) is None
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"), text_update(tutor_user, "/tutor"))
    assert texts.TUTOR_PANEL.format(name="Karimov Aziz") == h.last_text(TUTOR) and await h.state_of(TUTOR) is None
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"), text_update(tutor_user, texts.BTN_REGISTER))
    assert await h.state_of(TUTOR) == Registration.choose_tutor.state  # the student router got it
    # a stray typed line after all that is not a message to anyone
    await h.feed(text_update(tutor_user, "/cancel"), text_update(tutor_user, "hello"))
    assert h.messages(STUDENT) == []
    assert_all_callbacks_answered(h)


async def test_student_moved_to_another_tutor_while_the_prompt_was_open(h: Harness) -> None:
    tutor, group, student = await seed(h)
    other = await h.db.add_tutor("Boshqa Tyutor", OTHER_TUTOR)
    other_group = await h.db.add_group(other.id, "IQ-11")
    tutor_user = make_user(TUTOR)

    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"))
    await h.db.update_student(STUDENT, tutor_id=other.id, group_id=other_group.id)
    await h.feed(text_update(tutor_user, "Salom"))
    refused = h.last_message(TUTOR)
    assert refused.text == texts.NO_PERMISSION and reply_button_texts(refused.reply_markup) == TUTOR_MENU
    assert await h.state_of(TUTOR) is None
    assert h.messages(STUDENT) == []

    # deleted meanwhile -> "not found", still nothing sent
    await h.db.update_student(STUDENT, tutor_id=tutor.id, group_id=group.id)
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"))
    assert await h.db.delete_student(student.id)
    await h.feed(text_update(tutor_user, "Salom"))
    assert h.last_text(TUTOR) == texts.STUDENT_NOT_FOUND and await h.state_of(TUTOR) is None
    assert h.messages(STUDENT) == []
    assert_all_callbacks_answered(h)


async def test_delivery_failures_are_reported_honestly(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)
    original = type(h.session).make_request
    failure: dict[str, Any] = {"exc": None}

    async def failing(self_session: Any, bot: Any, method: Any, timeout: Any = None) -> Any:
        if type(method).__name__ == "SendMessage" and int(method.chat_id) == STUDENT and failure["exc"]:
            raise failure["exc"](method=method, message=failure["message"])
        return await original(self_session, bot, method, timeout)

    monkeypatch.setattr(type(h.session), "make_request", failing)

    failure.update(exc=TelegramForbiddenError, message="Forbidden: bot was blocked by the user")
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"), text_update(tutor_user, "Salom"))
    assert h.messages(TUTOR)[-2].text == texts.STUDENT_MESSAGE_BLOCKED

    failure.update(exc=TelegramBadRequest, message="Bad Request: something else")
    await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"), text_update(tutor_user, "Salom"))
    assert h.messages(TUTOR)[-2].text == texts.STUDENT_MESSAGE_FAILED
    assert await h.state_of(TUTOR) is None

    # the deletion stands even when the farewell message cannot be delivered
    failure.update(exc=TelegramForbiddenError, message="Forbidden: bot was blocked by the user")
    await h.feed(
        callback_update(tutor_user, f"stu:del:{student.id}:t"),
        callback_update(tutor_user, f"stu:delok:{student.id}:t"),
        callback_update(tutor_user, f"stu:bye_y:{student.id}:t"),
        text_update(tutor_user, "Xayr"),
    )
    assert h.messages(TUTOR)[-2].text == texts.STUDENT_DELETED_MESSAGE_BLOCKED.format(name="Zokirov Vali")
    assert await h.db.get_student_by_telegram_id(STUDENT) is None
    assert await h.state_of(TUTOR) is None
    assert_all_callbacks_answered(h)


# ================================================================== deleting


async def test_delete_student_then_send_a_farewell_message(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)
    sid = student.id

    await h.feed(callback_update(tutor_user, f"stu:del:{sid}:t"))
    confirm = h.last_shown(TUTOR)
    assert confirm.text == texts.STUDENT_DELETE_CONFIRM.format(name="Zokirov Vali", group="DI-21")
    assert inline_buttons(confirm.reply_markup) == {
        f"stu:delok:{sid}:t": texts.BTN_YES_DELETE,
        f"stu:view:{sid}:t": texts.BTN_NO,
    }
    await h.feed(callback_update(tutor_user, f"stu:view:{sid}:t"))  # changed my mind
    assert h.last_shown(TUTOR).text.startswith(texts.STUDENT_CARD_TITLE)
    assert await h.db.get_student_by_telegram_id(STUDENT) is not None

    await h.feed(callback_update(tutor_user, f"stu:del:{sid}:t"), callback_update(tutor_user, f"stu:delok:{sid}:t"))
    assert await h.db.get_student_by_telegram_id(STUDENT) is None
    assert h.answers()[-1].text == texts.STUDENT_DELETED_TOAST
    question = h.last_shown(TUTOR)
    assert question.text == texts.STUDENT_DELETED_ASK_MESSAGE.format(name="Zokirov Vali")
    assert inline_buttons(question.reply_markup) == {
        f"stu:bye_y:{sid}:t": texts.BTN_YES_SEND_MESSAGE,
        f"stu:bye_n:{sid}:t": texts.BTN_NO,
    }
    assert await h.state_of(TUTOR) == StudentManage.farewell.state
    await h.feed(text_update(tutor_user, "nima?"))
    assert h.last_text(TUTOR) == texts.USE_BUTTONS

    await h.feed(callback_update(tutor_user, f"stu:bye_y:{sid}:t"))
    ask = texts.ASK_STUDENT_MESSAGE.format(name="Zokirov Vali")
    assert h.last_text(TUTOR) == ask
    assert await h.state_of(TUTOR) == StudentManage.farewell_text.state
    await h.feed(callback_update(tutor_user, f"stu:bye_y:{sid}:t"))  # ✉️ Ha tapped again: just a toast
    assert h.answers()[-1].text == texts.STUDENT_MESSAGE_PROMPT_TOAST
    assert h.texts_to(TUTOR).count(ask) == 1

    await h.feed(text_update(tutor_user, "Omad!"))
    delivered = h.messages(STUDENT)
    assert len(delivered) == 1
    assert delivered[0].text == student_message(tutor_sender("Karimov Aziz"), "Omad!", removed_from="DI-21")
    sent = h.messages(TUTOR)
    assert sent[-2].text == texts.STUDENT_DELETED_MESSAGE_SENT.format(name="Zokirov Vali")
    assert reply_button_texts(sent[-2].reply_markup) == TUTOR_MENU
    assert sent[-1].text == texts.STUDENT_LIST_EMPTY.format(group="DI-21", tutor="")
    assert await h.state_of(TUTOR) is None
    assert await h.db.list_students(group_id=group.id) == []  # hence gone from every Excel export

    # the old question cannot be answered any more, and says why
    await h.feed(callback_update(tutor_user, f"stu:bye_n:{sid}:t"))
    assert h.answers()[-1].text == texts.FAREWELL_STALE and h.answers()[-1].show_alert

    # the student is free to register again from scratch
    student_user = make_user(STUDENT, username="vali")
    await h.feed(text_update(student_user, "/mydata"))
    assert texts.STUDENT_NOT_REGISTERED in h.texts_to(STUDENT)
    assert await h.state_of(STUDENT) == Registration.choose_tutor.state
    assert_all_callbacks_answered(h)


async def test_delete_student_without_a_message(h: Harness) -> None:
    tutor, group, student = await seed(h)
    await register(h, make_user(SECOND_STUDENT), tutor.id, group.id, RegInput(full_name="Aliyev Olim"))
    h.clear()
    tutor_user = make_user(TUTOR)
    sid = student.id

    await h.feed(callback_update(tutor_user, f"stu:del:{sid}:t"), callback_update(tutor_user, f"stu:delok:{sid}:t"))
    await h.feed(callback_update(tutor_user, f"stu:bye_n:{sid}:t"))
    shown = h.last_shown(TUTOR)
    listing = texts.STUDENT_LIST_TITLE.format(group="DI-21", n=1, tutor="")
    assert shown.text == f"{texts.STUDENT_DELETED_NO_MESSAGE.format(name='Zokirov Vali')}\n\n{listing}"
    second = await h.db.get_student_by_telegram_id(SECOND_STUDENT)
    assert second is not None
    assert inline_buttons(shown.reply_markup) == {
        f"stu:view:{second.id}:t": "Aliyev Olim",
        f"tut:view:{group.id}:": texts.BTN_BACK,
    }
    assert h.messages(STUDENT) == []
    assert await h.db.get_student_by_telegram_id(STUDENT) is None
    assert await h.state_of(TUTOR) is None
    assert_all_callbacks_answered(h)


async def test_cancelling_at_the_farewell_question_keeps_the_deletion(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)
    sid = student.id

    await h.feed(callback_update(tutor_user, f"stu:delok:{sid}:t"), text_update(tutor_user, texts.BTN_CANCEL))
    assert h.last_text(TUTOR) == texts.CANCELLED and await h.state_of(TUTOR) is None
    assert await h.db.get_student_by_telegram_id(STUDENT) is None
    await h.feed(callback_update(tutor_user, f"stu:bye_y:{sid}:t"))
    assert h.answers()[-1].text == texts.FAREWELL_STALE
    assert h.messages(STUDENT) == []
    assert_all_callbacks_answered(h)


async def test_stale_farewell_button_from_an_earlier_deletion_is_refused(h: Harness) -> None:
    tutor, group, first = await seed(h)
    await register(h, make_user(SECOND_STUDENT), tutor.id, group.id, RegInput(full_name="Aliyev Olim"))
    second = await h.db.get_student_by_telegram_id(SECOND_STUDENT)
    assert second is not None
    h.clear()
    tutor_user = make_user(TUTOR)

    await h.feed(callback_update(tutor_user, f"stu:delok:{first.id}:t"))  # question #1, left unanswered
    await h.feed(
        callback_update(tutor_user, f"stu:list:{group.id}:t"),
        callback_update(tutor_user, f"stu:delok:{second.id}:t"),  # question #2
    )
    assert await h.state_of(TUTOR) == StudentManage.farewell.state

    await h.feed(callback_update(tutor_user, f"stu:bye_y:{first.id}:t"))  # the old ✉️ Ha
    assert h.answers()[-1].text == texts.FAREWELL_STALE and h.answers()[-1].show_alert
    assert await h.state_of(TUTOR) == StudentManage.farewell.state  # #2 is still open
    await h.feed(callback_update(tutor_user, f"stu:bye_y:{second.id}:t"), text_update(tutor_user, "Xayr"))
    assert h.messages(STUDENT) == []
    assert [m.text for m in h.messages(SECOND_STUDENT)] == [
        student_message(tutor_sender("Karimov Aziz"), "Xayr", removed_from="DI-21")
    ]
    assert_all_callbacks_answered(h)


async def test_concurrent_double_tap_deletes_once(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)
    sid = student.id

    await h.feed_concurrently(
        callback_update(tutor_user, f"stu:delok:{sid}:t"), callback_update(tutor_user, f"stu:delok:{sid}:t")
    )
    assert Counter(a.text for a in h.answers()) == Counter({texts.STUDENT_DELETED_TOAST: 1, texts.STUDENT_NOT_FOUND: 1})
    question = texts.STUDENT_DELETED_ASK_MESSAGE.format(name="Zokirov Vali")
    assert h.texts_to(TUTOR).count(question) == 1
    assert await h.state_of(TUTOR) == StudentManage.farewell.state
    assert_all_callbacks_answered(h)


async def test_group_gone_between_screens(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)

    await h.feed(callback_update(tutor_user, f"stu:list:{group.id}:t"))
    assert await h.db.delete_group(group.id)  # cascades to the student
    await h.feed(
        callback_update(tutor_user, f"stu:view:{student.id}:t"),
        callback_update(tutor_user, f"stu:delok:{student.id}:t"),
        callback_update(tutor_user, f"stu:list:{group.id}:t"),
    )
    assert [a.text for a in h.answers()][-3:] == [texts.STUDENT_NOT_FOUND, texts.STUDENT_NOT_FOUND, texts.GROUP_NOT_FOUND]
    assert_all_callbacks_answered(h)


# ================================================================== authorization


async def test_other_tutor_and_strangers_are_denied(h: Harness) -> None:
    tutor, group, student = await seed(h)
    await h.db.add_tutor("Boshqa Tyutor", OTHER_TUTOR)
    intruder = make_user(OTHER_TUTOR)
    sid = student.id

    for data in (
        f"stu:list:{group.id}:t",
        f"stu:view:{sid}:t",
        f"stu:msg:{sid}:t",
        f"stu:del:{sid}:t",
        f"stu:delok:{sid}:t",
        f"stu:msg:{sid}:a",  # forging the admin mode does not help
        f"stu:delok:{sid}:a",
    ):
        await h.feed(callback_update(intruder, data))
        answer = h.answers()[-1]
        assert answer.text == texts.NO_PERMISSION and answer.show_alert, data
    assert await h.db.get_student_by_telegram_id(STUDENT) is not None
    assert await h.state_of(OTHER_TUTOR) is None
    assert h.texts_to(OTHER_TUTOR) == []

    # someone who is neither tutor nor superadmin never reaches the router at all
    stranger = make_user(STRANGER)
    await h.feed(callback_update(stranger, f"stu:list:{group.id}:t"), callback_update(stranger, f"stu:delok:{sid}:a"))
    assert [a.text for a in h.answers()][-2:] == [texts.STALE_BUTTON, texts.STALE_BUTTON]
    assert await h.db.get_student_by_telegram_id(STUDENT) is not None
    assert_all_callbacks_answered(h)


# ================================================================== superadmin


async def test_superadmin_manages_any_students_through_the_tutor_card(h: Harness) -> None:
    tutor, group, student = await seed(h)
    idle = await h.db.add_tutor("Bo'sh Tyutor", OTHER_TUTOR)
    admin = make_user(SUPERADMIN)
    sid = student.id

    await h.feed(text_update(admin, "/admin"), callback_update(admin, "adm:list:0"), callback_update(admin, f"adm:view:{tutor.id}"))
    card_kb = inline_buttons(h.last_shown(SUPERADMIN).reply_markup)
    assert card_kb[f"adm:groups:{tutor.id}"] == texts.BTN_TUTOR_GROUP_LIST

    await h.feed(callback_update(admin, f"adm:groups:{tutor.id}"))
    groups = h.last_shown(SUPERADMIN)
    assert groups.text == texts.TUTOR_GROUP_LIST_TITLE.format(name="Karimov Aziz", n=1)
    assert inline_buttons(groups.reply_markup) == {
        f"stu:list:{group.id}:a": "DI-21 — 1 ta talaba",
        f"adm:view:{tutor.id}": texts.BTN_BACK,
    }
    await h.feed(callback_update(admin, f"adm:groups:{idle.id}"))
    assert h.last_shown(SUPERADMIN).text == texts.TUTOR_GROUP_LIST_EMPTY.format(name="Bo'sh Tyutor")
    assert inline_buttons(h.last_shown(SUPERADMIN).reply_markup) == {f"adm:view:{idle.id}": texts.BTN_BACK}

    await h.feed(callback_update(admin, f"stu:list:{group.id}:a"))
    listing = h.last_shown(SUPERADMIN)
    tutor_line = texts.STUDENT_LIST_TUTOR_LINE.format(tutor="Karimov Aziz")
    assert listing.text == texts.STUDENT_LIST_TITLE.format(group="DI-21", n=1, tutor=tutor_line)
    assert inline_buttons(listing.reply_markup) == {
        f"stu:view:{sid}:a": "Zokirov Vali",
        f"adm:groups:{tutor.id}": texts.BTN_BACK,
    }

    await h.feed(callback_update(admin, f"stu:view:{sid}:a"))
    assert inline_buttons(h.last_shown(SUPERADMIN).reply_markup) == {
        f"stu:msg:{sid}:a": texts.BTN_SEND_MESSAGE,
        f"stu:del:{sid}:a": texts.BTN_DELETE,
        f"stu:list:{group.id}:a": texts.BTN_BACK,
    }
    await h.feed(callback_update(admin, f"stu:msg:{sid}:a"), text_update(admin, "Diqqat!"))
    assert h.messages(STUDENT)[-1].text == student_message(texts.MESSAGE_SENDER_ADMIN, "Diqqat!")
    assert reply_button_texts(h.messages(SUPERADMIN)[-2].reply_markup) == ADMIN_MENU

    await h.feed(
        callback_update(admin, f"stu:del:{sid}:a"),
        callback_update(admin, f"stu:delok:{sid}:a"),
        callback_update(admin, f"stu:bye_y:{sid}:a"),
        text_update(admin, "Xayr"),
    )
    assert await h.db.get_student_by_telegram_id(STUDENT) is None
    assert h.messages(STUDENT)[-1].text == student_message(texts.MESSAGE_SENDER_ADMIN, "Xayr", removed_from="DI-21")
    sent = h.messages(SUPERADMIN)
    assert sent[-2].text == texts.STUDENT_DELETED_MESSAGE_SENT.format(name="Zokirov Vali")
    assert sent[-1].text == texts.STUDENT_LIST_EMPTY.format(group="DI-21", tutor=tutor_line)
    assert inline_buttons(sent[-1].reply_markup) == {f"adm:groups:{tutor.id}": texts.BTN_BACK}
    assert_all_callbacks_answered(h)


async def test_superadmin_who_is_a_tutor_signs_own_students_by_name(h: Harness) -> None:
    tutor, group, student = await seed(h)  # someone else's student
    both = await h.db.add_tutor("Ikkalasi Ham", BOTH)
    own_group = await h.db.add_group(both.id, "BT-01")
    await register(h, make_user(SECOND_STUDENT), both.id, own_group.id, RegInput(full_name="O'z Talabam"))
    own = await h.db.get_student_by_telegram_id(SECOND_STUDENT)
    assert own is not None
    h.clear()
    both_user = make_user(BOTH)

    # own student, reached through the admin panel: still signed as their tutor
    await h.feed(callback_update(both_user, f"stu:msg:{own.id}:a"), text_update(both_user, "Salom"))
    assert h.messages(SECOND_STUDENT)[-1].text == student_message(tutor_sender("Ikkalasi Ham"), "Salom")
    # another tutor's student, whichever panel: the administration
    await h.feed(callback_update(both_user, f"stu:msg:{student.id}:t"), text_update(both_user, "Salom"))
    assert h.messages(STUDENT)[-1].text == student_message(texts.MESSAGE_SENDER_ADMIN, "Salom")
    # ...and the forged tutor mode did not grant tutor-style navigation either: back leads to the admin list
    await h.feed(callback_update(both_user, f"stu:view:{student.id}:t"))
    assert f"stu:list:{group.id}:a" in inline_buttons(h.last_shown(BOTH).reply_markup)
    assert_all_callbacks_answered(h)


# ================================================================== guards pinned by tests


async def test_tutor_delete_is_scoped_to_their_own_students_even_in_a_race(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The student moves to another tutor between the permission check and the DELETE statement."""
    tutor, group, student = await seed(h)
    other = await h.db.add_tutor("Boshqa Tyutor", OTHER_TUTOR)
    other_group = await h.db.add_group(other.id, "IQ-11")
    tutor_user = make_user(TUTOR)
    original = h.db.get_student

    async def get_then_move(student_id: int) -> Any:
        found = await original(student_id)
        await h.db.update_student(STUDENT, tutor_id=other.id, group_id=other_group.id)
        return found

    monkeypatch.setattr(h.db, "get_student", get_then_move)
    await h.feed(callback_update(tutor_user, f"stu:delok:{student.id}:t"))
    assert h.answers()[-1].text == texts.STUDENT_NOT_FOUND
    assert await h.state_of(TUTOR) is None
    moved = await h.db.get_student_by_telegram_id(STUDENT)
    assert moved is not None and moved.tutor_id == other.id  # still there, now the other tutor's
    assert_all_callbacks_answered(h)


async def test_superadmin_tutor_deletes_another_tutors_student(h: Harness) -> None:
    """A superadmin who is also a tutor is not scoped to their own students."""
    tutor, group, student = await seed(h)
    await h.db.add_tutor("Ikkalasi Ham", BOTH)
    both_user = make_user(BOTH)

    await h.feed(callback_update(both_user, f"stu:delok:{student.id}:a"))
    assert h.answers()[-1].text == texts.STUDENT_DELETED_TOAST
    assert await h.db.get_student_by_telegram_id(STUDENT) is None
    assert_all_callbacks_answered(h)


async def test_farewell_text_is_validated_like_a_message(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)
    sid = student.id
    await h.feed(callback_update(tutor_user, f"stu:delok:{sid}:t"), callback_update(tutor_user, f"stu:bye_y:{sid}:t"))
    assert await h.state_of(TUTOR) == StudentManage.farewell_text.state

    await h.feed(text_update(tutor_user, "   "))
    assert h.last_text(TUTOR) == texts.STUDENT_MESSAGE_INVALID.format(max=MESSAGE_MAX_LEN)
    await h.feed(text_update(tutor_user, "x" * (MESSAGE_MAX_LEN + 1)))
    assert h.last_text(TUTOR) == texts.STUDENT_MESSAGE_INVALID.format(max=MESSAGE_MAX_LEN)
    await h.feed(photo_update(tutor_user))
    assert h.last_text(TUTOR) == texts.STUDENT_MESSAGE_TEXT_ONLY
    assert h.messages(STUDENT) == []
    assert await h.state_of(TUTOR) == StudentManage.farewell_text.state

    await h.feed(text_update(tutor_user, "x" * MESSAGE_MAX_LEN))  # exactly the limit goes through
    assert len(h.messages(STUDENT)) == 1
    assert await h.state_of(TUTOR) is None
    assert_all_callbacks_answered(h)


async def test_saying_no_after_yes_drops_the_open_prompt(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)
    sid = student.id
    await h.feed(callback_update(tutor_user, f"stu:delok:{sid}:t"), callback_update(tutor_user, f"stu:bye_y:{sid}:t"))
    assert await h.state_of(TUTOR) == StudentManage.farewell_text.state

    await h.feed(callback_update(tutor_user, f"stu:bye_n:{sid}:t"))  # the question was still on screen
    assert await h.state_of(TUTOR) is None
    cancelled = h.last_message(TUTOR)
    assert cancelled.text == texts.CANCELLED and reply_button_texts(cancelled.reply_markup) == TUTOR_MENU
    assert h.last_shown(TUTOR).text.startswith(texts.STUDENT_DELETED_NO_MESSAGE.format(name="Zokirov Vali"))
    await h.feed(text_update(tutor_user, "Xayr"))
    assert h.messages(STUDENT) == []  # nothing pending any more
    assert_all_callbacks_answered(h)


async def test_stale_farewell_tap_leaves_the_new_list_keyboard_alone(h: Harness) -> None:
    tutor, group, student = await seed(h)
    await register(h, make_user(SECOND_STUDENT), tutor.id, group.id, RegInput(full_name="Aliyev Olim"))
    h.clear()
    tutor_user = make_user(TUTOR)
    sid = student.id
    await h.feed(callback_update(tutor_user, f"stu:delok:{sid}:t"))
    await h.feed(callback_update(tutor_user, f"stu:bye_n:{sid}:t"), callback_update(tutor_user, f"stu:bye_n:{sid}:t"))
    assert h.answers()[-1].text == texts.FAREWELL_STALE
    assert h.of("EditMessageReplyMarkup", TUTOR) == []  # the freshly drawn student list keeps its buttons
    second = await h.db.get_student_by_telegram_id(SECOND_STUDENT)
    assert second is not None
    assert f"stu:view:{second.id}:t" in inline_buttons(h.last_shown(TUTOR).reply_markup)
    assert_all_callbacks_answered(h)


async def test_farewell_still_reaches_a_student_who_re_registered_meanwhile(h: Harness) -> None:
    """The permission was checked at deletion time; the farewell belongs to that deletion."""
    tutor, group, student = await seed(h)
    other = await h.db.add_tutor("Boshqa Tyutor", OTHER_TUTOR)
    other_group = await h.db.add_group(other.id, "IQ-11")
    tutor_user = make_user(TUTOR)
    sid = student.id
    await h.feed(callback_update(tutor_user, f"stu:delok:{sid}:t"), callback_update(tutor_user, f"stu:bye_y:{sid}:t"))
    await register(h, make_user(STUDENT, username="vali"), other.id, other_group.id)  # meanwhile
    h.clear()

    await h.feed(text_update(tutor_user, "Xayr"))
    assert [m.text for m in h.messages(STUDENT)] == [
        student_message(tutor_sender("Karimov Aziz"), "Xayr", removed_from="DI-21")
    ]
    assert h.messages(TUTOR)[-2].text == texts.STUDENT_DELETED_MESSAGE_SENT.format(name="Zokirov Vali")
    again = await h.db.get_student_by_telegram_id(STUDENT)
    assert again is not None and again.tutor_id == other.id  # the new registration is untouched
    assert_all_callbacks_answered(h)


async def test_inline_navigation_abandons_an_open_prompt(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)
    for data in (f"stu:list:{group.id}:t", f"stu:view:{student.id}:t", f"stu:del:{student.id}:t"):
        await h.feed(callback_update(tutor_user, f"stu:msg:{student.id}:t"), callback_update(tutor_user, data))
        assert await h.state_of(TUTOR) is None, data
        await h.feed(text_update(tutor_user, "hello"))
        assert h.messages(STUDENT) == [], data
    assert_all_callbacks_answered(h)


async def test_a_tutor_cannot_ask_for_admin_style_navigation(h: Harness) -> None:
    tutor, group, student = await seed(h)
    tutor_user = make_user(TUTOR)
    await h.feed(callback_update(tutor_user, f"stu:view:{student.id}:a"))
    assert f"stu:list:{group.id}:t" in inline_buttons(h.last_shown(TUTOR).reply_markup)
    await h.feed(callback_update(tutor_user, f"stu:list:{group.id}:a"))
    assert f"tut:view:{group.id}:" in inline_buttons(h.last_shown(TUTOR).reply_markup)
    assert h.last_shown(TUTOR).text == texts.STUDENT_LIST_TITLE.format(group="DI-21", n=1, tutor="")
    assert_all_callbacks_answered(h)


async def test_every_screen_escapes_group_and_tutor_names(h: Harness) -> None:
    tutor = await h.db.add_tutor("T&T <i>Karimov", TUTOR)
    group = await h.db.add_group(tutor.id, "DI&<21>")
    student, _ = await h.db.upsert_student(
        telegram_id=STUDENT,
        username=None,
        tutor_id=tutor.id,
        group_id=group.id,
        full_name="Ali <b>Valiyev",
        phone="+998901234567",
        direction="Dasturiy injiniring",
        residence="ttj",
        address="TTJ",
        father_name="Ota Otayev",
        father_phone="+998901111111",
        mother_name="Ona Onayeva",
        mother_phone="+998902222222",
    )
    tutor_user, admin = make_user(TUTOR), make_user(SUPERADMIN)
    esc_group, esc_tutor, esc_name = "DI&amp;&lt;21&gt;", "T&amp;T &lt;i&gt;Karimov", "Ali &lt;b&gt;Valiyev"

    await h.feed(callback_update(tutor_user, f"stu:list:{group.id}:t"))
    assert h.last_shown(TUTOR).text == texts.STUDENT_LIST_TITLE.format(group=esc_group, n=1, tutor="")
    await h.feed(callback_update(admin, f"adm:groups:{tutor.id}"))
    assert h.last_shown(SUPERADMIN).text == texts.TUTOR_GROUP_LIST_TITLE.format(name=esc_tutor, n=1)
    await h.feed(callback_update(admin, f"stu:list:{group.id}:a"))
    tutor_line = texts.STUDENT_LIST_TUTOR_LINE.format(tutor=esc_tutor)
    assert h.last_shown(SUPERADMIN).text == texts.STUDENT_LIST_TITLE.format(group=esc_group, n=1, tutor=tutor_line)

    await h.feed(callback_update(tutor_user, f"stu:delok:{student.id}:t"))
    assert h.last_shown(TUTOR).text == texts.STUDENT_DELETED_ASK_MESSAGE.format(name=esc_name)
    await h.feed(callback_update(tutor_user, f"stu:bye_y:{student.id}:t"))
    assert h.last_text(TUTOR) == texts.ASK_STUDENT_MESSAGE.format(name=esc_name)
    await h.feed(text_update(tutor_user, "Xayr <3"))
    delivered = h.messages(STUDENT)[0].text
    assert delivered == student_message(tutor_sender(esc_tutor), "Xayr &lt;3", removed_from=esc_group)
    assert h.messages(TUTOR)[-2].text == texts.STUDENT_DELETED_MESSAGE_SENT.format(name=esc_name)
    assert h.messages(TUTOR)[-1].text == texts.STUDENT_LIST_EMPTY.format(group=esc_group, tutor="")
    assert_all_callbacks_answered(h)
