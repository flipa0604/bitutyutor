"""Reply / inline keyboards and CallbackData factories."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import texts
from .models import (
    COURSE_MAX,
    COURSE_MIN,
    REGION_VALUES,
    SURVEY_BASIC,
    SURVEY_FULL,
    Group,
    TestUser,
    Tutor,
)

# ------------------------------------------------------------ callback data


class AdminCb(CallbackData, prefix="adm"):
    """Superadmin panel callbacks. ``tutor_id`` is 0 when not applicable."""

    action: str
    tutor_id: int = 0


class TutorCb(CallbackData, prefix="tut"):
    """Tutor panel callbacks. ``group_id`` is 0 when not applicable; ``value`` carries a residence code."""

    action: str
    group_id: int = 0
    value: str = ""


class TestCb(CallbackData, prefix="tst"):
    """Test-user list callbacks, packed as ``tst:{action}:{user_id}``."""

    action: str
    user_id: int = 0


class UsersCb(CallbackData, prefix="usr"):
    """Paging of the /users list, packed as ``usr:{page}`` (0-based).

    Separate from :class:`AdminCb` on purpose: adding a field to ``AdminCb`` would change the
    packed length of every existing admin button.
    """

    page: int = 0


class RegCb(CallbackData, prefix="reg"):
    """Student registration callbacks, packed as ``reg:{action}:{id}`` (e.g. ``reg:tutor:5``)."""

    action: str
    id: int = 0


class EditCb(CallbackData, prefix="edt"):
    """Student self-service callbacks, packed as ``edt:{action}:{field}``.

    ``field`` names a student column for :data:`EDT_FIELD` and is empty for every other action.
    """

    action: str
    field: str = ""


VIA_TUTOR = "t"
VIA_ADMIN = "a"


class BcCb(CallbackData, prefix="bc"):
    """Broadcast composer callbacks, packed as ``bc:{action}:{value}``."""

    action: str
    value: str = ""


class SurveyCb(CallbackData, prefix="sv"):
    """Which questionnaire the student picked, packed as ``sv:{action}:{code}``."""

    action: str
    code: str


class FullCb(CallbackData, prefix="fl"):
    """Full-survey callbacks, packed as ``fl:{action}:{value}`` (``value`` = a field or status code)."""

    action: str
    value: str = ""


class StuCb(CallbackData, prefix="stu"):
    """Student management by a tutor or superadmin, packed as ``stu:{action}:{id}:{via}``.

    ``id`` is a group id for :data:`STU_LIST` and a student id otherwise -- for the farewell buttons
    the id of the row just deleted, which AUTOINCREMENT never hands out again.
    ``via`` records which panel the screen was reached from -- ``t`` (tutor) or ``a`` (admin) -- and
    only decides where "back" leads; neither permission nor how a message is signed depends on it
    (``bot.handlers.manage.Actor`` derives both from the sender's real roles).
    """

    action: str
    id: int = 0
    via: str = VIA_TUTOR
    s: str = SURVEY_BASIC
    """Which questionnaire the screen is about; the two are listed and deleted separately."""


# admin actions
ADM_PANEL = "panel"
ADM_LIST = "list"
ADM_ADD = "add"
ADM_VIEW = "view"
ADM_GROUPS = "groups"  # a tutor's group list, the superadmin's way into student management
ADM_EDIT_PICK = "edit_pick"
ADM_EDIT_NAME = "edit_name"
ADM_EDIT_TG = "edit_tg"
ADM_DELETE = "delete"
ADM_CONFIRM_DELETE = "confirm_delete"
ADM_SAVE = "save"
ADM_CANCEL = "cancel"
ADM_EXCEL_ALL = "excel_all"
ADM_EXCEL_PICK = "excel_pick"
ADM_EXCEL_TUTOR = "excel_tutor"
ADM_BROADCAST = "broadcast"
ADM_EXCEL_ALL_FULL = "excel_all_f"  # full survey, every tutor
ADM_EXCEL_TUTOR_FULL = "excel_tut_f"  # full survey, one tutor

# tutor actions
TUT_PANEL = "panel"
TUT_GROUPS = "groups"
TUT_ADD = "add"
TUT_VIEW = "view"
TUT_RENAME = "rename"
TUT_DELETE = "delete"
TUT_CONFIRM_DELETE = "confirm_delete"
TUT_EXCEL_MENU = "excel_menu"
TUT_EXCEL_PICK_GROUP = "excel_pick_group"
TUT_EXCEL_GROUP = "excel_group"
TUT_EXCEL_RES = "excel_res"
TUT_EXCEL_RES_PICK = "excel_res_pick"
TUT_EXCEL_ALL = "excel_all"
TUT_STUDENTS = "students"  # pick a group whose students to manage
TUT_EXCEL_FULL_PICK = "exf_pick"  # full survey: pick a group
TUT_EXCEL_FULL_GROUP = "exf_group"
TUT_EXCEL_FULL_ALL = "exf_all"
TUT_PHONE = "phone"  # the tutor's own number, a column of the full survey

# registration actions
REG_TUTOR = "tutor"
REG_GROUP = "group"
REG_BACK = "back"
REG_CONFIRM = "confirm"
REG_RESTART = "restart"
REG_CANCEL = "cancel"

# test-user list actions
TST_LIST = "list"
TST_ADD = "add"
TST_DELETE = "delete"

# student self-service actions
EDT_OPEN = "open"  # show the field picker
EDT_FIELD = "field"  # edit one free-text column, named by ``EditCb.field``
EDT_RESIDENCE = "res"
EDT_TUTOR_GROUP = "tg"
EDT_DONE = "done"
EDT_REREGISTER = "again"

# survey picker actions
SV_FILL = "fill"  # not filled in yet: start the questionnaire
SV_OPEN = "open"  # already filled in: show the card

# full survey actions
FL_OPEN = "open"  # show the field picker
FL_FIELD = "field"  # edit one field, named by ``FullCb.value``
FL_SOCIAL = "soc"  # toggle one social-status code
FL_SOCIAL_NONE = "soc_no"
FL_SOCIAL_DONE = "soc_ok"
FL_CONFIRM = "confirm"
FL_RESTART = "restart"
FL_CANCEL = "cancel"
FL_DONE = "done"
FL_REFILL = "again"  # test users only: fill the whole questionnaire again

# broadcast actions
BC_SKIP = "skip"  # optional media step: nothing to add here, go on
BC_ADD = "add"  # ``value`` = part kind to ask for next (text / photo / video / voice)
BC_REMOVE = "rm"  # drop the last part
BC_PREVIEW = "preview"  # copy every part to the admin themselves
BC_REVIEW = "review"  # back to the summary
BC_SEND = "send"  # summary -> "send to N users?"
BC_CONFIRM = "go"  # really send
BC_CANCEL = "cancel"

# student management actions (tutor / superadmin)
STU_SURVEYS = "svs"  # a group's two student lists to choose from (id = group id)
STU_LIST = "list"  # students of a group in one survey (id = group id)
STU_VIEW = "view"  # one student's card
STU_MESSAGE = "msg"  # write to the student
STU_DELETE = "del"  # ask for confirmation
STU_CONFIRM_DELETE = "delok"
STU_BYE_YES = "bye_y"  # after deletion: message the former student (id = the deleted row's id)
STU_BYE_NO = "bye_n"


# ---------------------------------------------------------- reply keyboards


def main_menu_kb(is_admin: bool, is_tutor: bool) -> ReplyKeyboardMarkup:
    """Role-additive main menu: both panel buttons appear when the user holds both roles."""
    rows: list[list[KeyboardButton]] = []
    role_row = [KeyboardButton(text=texts.BTN_ADMIN_PANEL)] if is_admin else []
    if is_tutor:
        role_row.append(KeyboardButton(text=texts.BTN_TUTOR_PANEL))
    if role_row:
        rows.append(role_row)
    rows.append([KeyboardButton(text=texts.BTN_REGISTER)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=texts.BTN_CANCEL)]], resize_keyboard=True)


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_SEND_CONTACT, request_contact=True)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def residence_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_RES_TTJ), KeyboardButton(text=texts.BTN_RES_KVARTIRA)],
            [KeyboardButton(text=texts.BTN_RES_UY), KeyboardButton(text=texts.BTN_RES_QARINDOSH)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


# --------------------------------------------------------- inline: helpers


def _back_button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


# ----------------------------------------------------------- inline: admin


def admin_panel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_ADMIN_TUTORS, callback_data=AdminCb(action=ADM_LIST))
    b.button(text=texts.BTN_ADMIN_ADD_TUTOR, callback_data=AdminCb(action=ADM_ADD))
    b.button(text=texts.BTN_ADMIN_USERS, callback_data=UsersCb(page=0))
    b.button(text=texts.BTN_ADMIN_TEST_USERS, callback_data=TestCb(action=TST_LIST))
    b.button(text=texts.BTN_ADMIN_EXCEL_ALL, callback_data=AdminCb(action=ADM_EXCEL_ALL))
    b.button(text=texts.BTN_ADMIN_EXCEL_PICK, callback_data=AdminCb(action=ADM_EXCEL_PICK))
    b.button(text=texts.BTN_ADMIN_EXCEL_FULL, callback_data=AdminCb(action=ADM_EXCEL_ALL_FULL))
    b.button(text=texts.BTN_ADMIN_BROADCAST, callback_data=AdminCb(action=ADM_BROADCAST))
    b.adjust(2, 2, 1, 1, 1, 1)
    return b.as_markup()


def admin_test_users_kb(users: Sequence[TestUser]) -> InlineKeyboardMarkup:
    """One button per tester (tapping it removes them) plus ➕ add and ⬅️ back."""
    b = InlineKeyboardBuilder()
    for user in users:
        b.button(text=texts.test_user_button_label(user), callback_data=TestCb(action=TST_DELETE, user_id=user.telegram_id))
    b.adjust(1)
    b.row(InlineKeyboardButton(text=texts.BTN_ADD_TEST_USER, callback_data=TestCb(action=TST_ADD).pack()))
    b.row(_back_button(texts.BTN_BACK, AdminCb(action=ADM_PANEL).pack()))
    return b.as_markup()


def admin_users_kb(page: int, pages: int) -> InlineKeyboardMarkup:
    """Prev/next paging for /users; an arrow appears only when there is a page on that side."""
    b = InlineKeyboardBuilder()
    arrows = []
    if page > 0:
        arrows.append(InlineKeyboardButton(text=texts.BTN_PREV, callback_data=UsersCb(page=page - 1).pack()))
    if page + 1 < pages:
        arrows.append(InlineKeyboardButton(text=texts.BTN_NEXT, callback_data=UsersCb(page=page + 1).pack()))
    if arrows:
        b.row(*arrows)
    b.row(_back_button(texts.BTN_BACK, AdminCb(action=ADM_PANEL).pack()))
    return b.as_markup()


def admin_tutor_list_kb(tutors: Sequence[Tutor], action: str = ADM_VIEW) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for tutor in tutors:
        b.button(text=texts.tutor_button_label(tutor), callback_data=AdminCb(action=action, tutor_id=tutor.id))
    b.adjust(1)
    b.row(_back_button(texts.BTN_BACK, AdminCb(action=ADM_PANEL).pack()))
    return b.as_markup()


def admin_tutor_card_kb(tutor_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_EDIT_NAME, callback_data=AdminCb(action=ADM_EDIT_NAME, tutor_id=tutor_id))
    b.button(text=texts.BTN_EDIT_TG, callback_data=AdminCb(action=ADM_EDIT_TG, tutor_id=tutor_id))
    b.button(text=texts.BTN_TUTOR_GROUP_LIST, callback_data=AdminCb(action=ADM_GROUPS, tutor_id=tutor_id))
    b.button(text=texts.BTN_EXCEL, callback_data=AdminCb(action=ADM_EXCEL_TUTOR, tutor_id=tutor_id))
    b.button(text=texts.BTN_EXCEL_FULL, callback_data=AdminCb(action=ADM_EXCEL_TUTOR_FULL, tutor_id=tutor_id))
    b.button(text=texts.BTN_DELETE, callback_data=AdminCb(action=ADM_DELETE, tutor_id=tutor_id))
    b.button(text=texts.BTN_BACK, callback_data=AdminCb(action=ADM_LIST))
    b.adjust(1, 1, 1, 2, 1, 1)
    return b.as_markup()


def admin_group_list_kb(groups: Sequence[Group], tutor_id: int) -> InlineKeyboardMarkup:
    """A tutor's groups as seen by a superadmin; each opens that group's students in admin mode."""
    b = InlineKeyboardBuilder()
    for group in groups:
        b.button(
            text=texts.group_button_label(group.name, group.student_count, group.profile_count),
            callback_data=StuCb(action=STU_SURVEYS, id=group.id, via=VIA_ADMIN),
        )
    b.adjust(1)
    b.row(_back_button(texts.BTN_BACK, AdminCb(action=ADM_VIEW, tutor_id=tutor_id).pack()))
    return b.as_markup()


def admin_edit_field_kb(tutor_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_EDIT_NAME, callback_data=AdminCb(action=ADM_EDIT_NAME, tutor_id=tutor_id))
    b.button(text=texts.BTN_EDIT_TG, callback_data=AdminCb(action=ADM_EDIT_TG, tutor_id=tutor_id))
    b.button(text=texts.BTN_BACK, callback_data=AdminCb(action=ADM_VIEW, tutor_id=tutor_id))
    b.adjust(1)
    return b.as_markup()


def admin_confirm_delete_kb(tutor_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_YES_DELETE, callback_data=AdminCb(action=ADM_CONFIRM_DELETE, tutor_id=tutor_id))
    b.button(text=texts.BTN_NO, callback_data=AdminCb(action=ADM_VIEW, tutor_id=tutor_id))
    b.adjust(2)
    return b.as_markup()


def admin_save_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SAVE, callback_data=AdminCb(action=ADM_SAVE))
    b.button(text=texts.BTN_CANCEL, callback_data=AdminCb(action=ADM_CANCEL))
    b.adjust(2)
    return b.as_markup()


def admin_back_kb(action: str = ADM_PANEL, tutor_id: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_back_button(texts.BTN_BACK, AdminCb(action=action, tutor_id=tutor_id).pack())]]
    )


# ----------------------------------------------------------- inline: tutor


def tutor_panel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_TUTOR_GROUPS, callback_data=TutorCb(action=TUT_GROUPS))
    b.button(text=texts.BTN_TUTOR_ADD_GROUP, callback_data=TutorCb(action=TUT_ADD))
    b.button(text=texts.BTN_GROUP_STUDENTS, callback_data=TutorCb(action=TUT_STUDENTS))
    b.button(text=texts.BTN_TUTOR_EXCEL, callback_data=TutorCb(action=TUT_EXCEL_MENU))
    b.button(text=texts.BTN_TUTOR_PHONE, callback_data=TutorCb(action=TUT_PHONE))
    b.adjust(2, 1, 1, 1)
    return b.as_markup()


def tutor_group_list_kb(
    groups: Sequence[Group], action: str = TUT_VIEW, back_action: str = TUT_PANEL
) -> InlineKeyboardMarkup:
    """The tutor's groups. ``action=TUT_STUDENTS`` makes each button open the group's student list."""
    b = InlineKeyboardBuilder()
    for group in groups:
        if action == TUT_STUDENTS:
            data = StuCb(action=STU_SURVEYS, id=group.id, via=VIA_TUTOR).pack()
        else:
            data = TutorCb(action=action, group_id=group.id).pack()
        b.button(text=texts.group_button_label(group.name, group.student_count, group.profile_count), callback_data=data)
    b.adjust(1)
    if not groups:
        b.row(InlineKeyboardButton(text=texts.BTN_TUTOR_ADD_GROUP, callback_data=TutorCb(action=TUT_ADD).pack()))
    b.row(_back_button(texts.BTN_BACK, TutorCb(action=back_action).pack()))
    return b.as_markup()


def tutor_group_card_kb(group_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_GROUP_STUDENTS, callback_data=StuCb(action=STU_SURVEYS, id=group_id, via=VIA_TUTOR))
    b.button(text=texts.BTN_RENAME_GROUP, callback_data=TutorCb(action=TUT_RENAME, group_id=group_id))
    b.button(text=texts.BTN_DELETE, callback_data=TutorCb(action=TUT_DELETE, group_id=group_id))
    b.button(text=texts.BTN_EXCEL, callback_data=TutorCb(action=TUT_EXCEL_GROUP, group_id=group_id))
    b.button(text=texts.BTN_BACK, callback_data=TutorCb(action=TUT_GROUPS))
    b.adjust(1, 2, 1, 1)
    return b.as_markup()


def tutor_confirm_delete_kb(group_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_YES_DELETE, callback_data=TutorCb(action=TUT_CONFIRM_DELETE, group_id=group_id))
    b.button(text=texts.BTN_NO, callback_data=TutorCb(action=TUT_VIEW, group_id=group_id))
    b.adjust(2)
    return b.as_markup()


def tutor_excel_menu_kb() -> InlineKeyboardMarkup:
    """Both questionnaires on one screen: the basic one first, the full one under it."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_EXCEL_BY_GROUP, callback_data=TutorCb(action=TUT_EXCEL_PICK_GROUP))
    b.button(text=texts.BTN_EXCEL_BY_RESIDENCE, callback_data=TutorCb(action=TUT_EXCEL_RES))
    b.button(text=texts.BTN_EXCEL_ALL_GROUPS, callback_data=TutorCb(action=TUT_EXCEL_ALL))
    b.button(text=texts.BTN_EXCEL_FULL_GROUP, callback_data=TutorCb(action=TUT_EXCEL_FULL_PICK))
    b.button(text=texts.BTN_EXCEL_FULL_ALL, callback_data=TutorCb(action=TUT_EXCEL_FULL_ALL))
    b.button(text=texts.BTN_BACK, callback_data=TutorCb(action=TUT_PANEL))
    b.adjust(1)
    return b.as_markup()


def tutor_residence_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_RES_TTJ, callback_data=TutorCb(action=TUT_EXCEL_RES_PICK, value="ttj"))
    b.button(text=texts.BTN_RES_KVARTIRA, callback_data=TutorCb(action=TUT_EXCEL_RES_PICK, value="kvartira"))
    b.button(text=texts.BTN_EXCEL_RES_UY, callback_data=TutorCb(action=TUT_EXCEL_RES_PICK, value="uy"))
    b.button(text=texts.BTN_RES_QARINDOSH, callback_data=TutorCb(action=TUT_EXCEL_RES_PICK, value="qarindosh"))
    b.button(text=texts.BTN_BACK, callback_data=TutorCb(action=TUT_EXCEL_MENU))
    b.adjust(2, 2, 1)
    return b.as_markup()


# ---------------------------------------------------- inline: registration


def reg_tutor_list_kb(tutors: Sequence[Tutor]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for tutor in tutors:
        b.button(text=tutor.name, callback_data=RegCb(action=REG_TUTOR, id=tutor.id))
    b.adjust(1)
    b.row(InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data=RegCb(action=REG_CANCEL).pack()))
    return b.as_markup()


def reg_group_list_kb(groups: Sequence[Group]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for group in groups:
        b.button(text=group.name, callback_data=RegCb(action=REG_GROUP, id=group.id))
    b.adjust(1)
    b.row(
        InlineKeyboardButton(text=texts.BTN_BACK, callback_data=RegCb(action=REG_BACK).pack()),
        InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data=RegCb(action=REG_CANCEL).pack()),
    )
    return b.as_markup()


def reg_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_CONFIRM, callback_data=RegCb(action=REG_CONFIRM))
    b.button(text=texts.BTN_RESTART, callback_data=RegCb(action=REG_RESTART))
    b.button(text=texts.BTN_CANCEL, callback_data=RegCb(action=REG_CANCEL))
    b.adjust(1)
    return b.as_markup()


# ------------------------------------------------- inline: student's own data


def student_home_kb(can_reregister: bool = False) -> InlineKeyboardMarkup:
    """Shown under a registered student's own card.

    Editing is always offered; registering from scratch a second time only to test users, so a real
    student cannot accidentally replace their record.
    """
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_EDIT_MY_DATA, callback_data=EditCb(action=EDT_OPEN))
    if can_reregister:
        b.button(text=texts.BTN_REREGISTER, callback_data=EditCb(action=EDT_REREGISTER))
    b.adjust(1)
    return b.as_markup()


def student_edit_field_kb(residence: str) -> InlineKeyboardMarkup:
    """Field picker. ``Manzil`` is hidden for TTJ residents: their address is always ``TTJ``,
    and it is set automatically when they pick a residence."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_EDIT_TUTOR_GROUP, callback_data=EditCb(action=EDT_TUTOR_GROUP))
    b.button(text=texts.BTN_EDIT_FULL_NAME, callback_data=EditCb(action=EDT_FIELD, field="full_name"))
    b.button(text=texts.BTN_EDIT_PHONE, callback_data=EditCb(action=EDT_FIELD, field="phone"))
    b.button(text=texts.BTN_EDIT_DIRECTION, callback_data=EditCb(action=EDT_FIELD, field="direction"))
    b.button(text=texts.BTN_EDIT_RESIDENCE, callback_data=EditCb(action=EDT_RESIDENCE))
    rows = [1, 2, 2]
    if residence != "ttj":
        b.button(text=texts.BTN_EDIT_ADDRESS, callback_data=EditCb(action=EDT_FIELD, field="address"))
        rows.append(1)
    b.button(text=texts.BTN_EDIT_FATHER_NAME, callback_data=EditCb(action=EDT_FIELD, field="father_name"))
    b.button(text=texts.BTN_EDIT_FATHER_PHONE, callback_data=EditCb(action=EDT_FIELD, field="father_phone"))
    b.button(text=texts.BTN_EDIT_MOTHER_NAME, callback_data=EditCb(action=EDT_FIELD, field="mother_name"))
    b.button(text=texts.BTN_EDIT_MOTHER_PHONE, callback_data=EditCb(action=EDT_FIELD, field="mother_phone"))
    b.button(text=texts.BTN_EDIT_DONE, callback_data=EditCb(action=EDT_DONE))
    b.adjust(*rows, 2, 2, 1)
    return b.as_markup()


# ------------------------------------- inline: student management (tutor / superadmin)


def _students_back_button(group: Group, via: str) -> InlineKeyboardButton:
    """Back from a group's student list: the tutor's group card, or the superadmin's group list."""
    if via == VIA_ADMIN:
        data = AdminCb(action=ADM_GROUPS, tutor_id=group.tutor_id).pack()
    else:
        data = TutorCb(action=TUT_VIEW, group_id=group.id).pack()
    return _back_button(texts.BTN_BACK, data)


def group_surveys_kb(group: Group, via: str, basic_n: int, full_n: int) -> InlineKeyboardMarkup:
    """Which questionnaire's students of this group to work with."""
    b = InlineKeyboardBuilder()
    b.button(
        text=f"{texts.BTN_SURVEY_BASIC} — {basic_n} ta",
        callback_data=StuCb(action=STU_LIST, id=group.id, via=via, s=SURVEY_BASIC),
    )
    b.button(
        text=f"{texts.BTN_SURVEY_FULL} — {full_n} ta",
        callback_data=StuCb(action=STU_LIST, id=group.id, via=via, s=SURVEY_FULL),
    )
    b.adjust(1)
    b.row(_students_back_button(group, via))
    return b.as_markup()


def student_list_kb(rows: Sequence[Any], group: Group, via: str, survey: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for row in rows:
        b.button(text=row.full_name, callback_data=StuCb(action=STU_VIEW, id=row.id, via=via, s=survey))
    b.adjust(1)
    b.row(
        InlineKeyboardButton(
            text=texts.BTN_BACK, callback_data=StuCb(action=STU_SURVEYS, id=group.id, via=via).pack()
        )
    )
    return b.as_markup()


def student_manage_kb(row: Any, via: str, survey: str) -> InlineKeyboardMarkup:
    """Under a student's card: write to them, delete them, or back to their group's list."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_SEND_MESSAGE, callback_data=StuCb(action=STU_MESSAGE, id=row.id, via=via, s=survey))
    b.button(text=texts.BTN_DELETE, callback_data=StuCb(action=STU_DELETE, id=row.id, via=via, s=survey))
    b.button(
        text=texts.BTN_BACK, callback_data=StuCb(action=STU_LIST, id=row.group_id, via=via, s=survey)
    )
    b.adjust(2, 1)
    return b.as_markup()


def student_confirm_delete_kb(row: Any, via: str, survey: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text=texts.BTN_YES_DELETE,
        callback_data=StuCb(action=STU_CONFIRM_DELETE, id=row.id, via=via, s=survey),
    )
    b.button(text=texts.BTN_NO, callback_data=StuCb(action=STU_VIEW, id=row.id, via=via, s=survey))
    b.adjust(2)
    return b.as_markup()


def student_farewell_kb(row_id: int, via: str, survey: str) -> InlineKeyboardMarkup:
    """"Message the deleted student?" -- carries the deleted row's id so a button left over from an
    earlier deletion can be told apart from the current question."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_YES_SEND_MESSAGE, callback_data=StuCb(action=STU_BYE_YES, id=row_id, via=via, s=survey))
    b.button(text=texts.BTN_NO, callback_data=StuCb(action=STU_BYE_NO, id=row_id, via=via, s=survey))
    b.adjust(2)
    return b.as_markup()


# ----------------------------------------------------- inline: broadcast (superadmin)

PART_KINDS: tuple[str, ...] = ("text", "photo", "video", "voice")


def broadcast_skip_kb() -> InlineKeyboardMarkup:
    """Under an optional media step: nothing to add, go to the next step."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_BC_SKIP, callback_data=BcCb(action=BC_SKIP))
    return b.as_markup()


def broadcast_continue_kb() -> InlineKeyboardMarkup:
    """After something was added in a media step: more of the same is welcome, or move on."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_BC_CONTINUE, callback_data=BcCb(action=BC_SKIP))
    return b.as_markup()


def broadcast_review_kb(can_remove: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_BC_ADD_TEXT, callback_data=BcCb(action=BC_ADD, value="text"))
    b.button(text=texts.BTN_BC_ADD_PHOTO, callback_data=BcCb(action=BC_ADD, value="photo"))
    b.button(text=texts.BTN_BC_ADD_VIDEO, callback_data=BcCb(action=BC_ADD, value="video"))
    b.button(text=texts.BTN_BC_ADD_VOICE, callback_data=BcCb(action=BC_ADD, value="voice"))
    rows = [2, 2]
    if can_remove:
        b.button(text=texts.BTN_BC_REMOVE_LAST, callback_data=BcCb(action=BC_REMOVE))
        rows.append(1)
    b.button(text=texts.BTN_BC_PREVIEW, callback_data=BcCb(action=BC_PREVIEW))
    b.button(text=texts.BTN_BC_SEND, callback_data=BcCb(action=BC_SEND))
    b.button(text=texts.BTN_CANCEL, callback_data=BcCb(action=BC_CANCEL))
    b.adjust(*rows, 1, 1, 1)
    return b.as_markup()


def broadcast_back_kb() -> InlineKeyboardMarkup:
    """Under an ➕ prompt: changed my mind, back to the summary."""
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_BACK, callback_data=BcCb(action=BC_REVIEW))
    return b.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_BC_CONFIRM, callback_data=BcCb(action=BC_CONFIRM))
    b.button(text=texts.BTN_BACK, callback_data=BcCb(action=BC_REVIEW))
    b.adjust(1)
    return b.as_markup()

# --------------------------------------------- survey picker (student's entry)


def survey_pick_kb(filled: dict[str, str | None]) -> InlineKeyboardMarkup:
    """One button per questionnaire: fill it in, or open the card that is already saved."""
    b = InlineKeyboardBuilder()
    for code, label in texts.SURVEY_LABELS.items():
        done = bool(filled.get(code))
        action = SV_OPEN if done else SV_FILL
        prefix = "✅ " if done else "🕗 "
        b.button(text=f"{prefix}{label}", callback_data=SurveyCb(action=action, code=code))
    b.adjust(1)
    return b.as_markup()


# --------------------------------------- full survey: bottom (reply) keyboards


def _nav_row(with_back: bool = True) -> list[KeyboardButton]:
    row = [KeyboardButton(text=texts.BTN_CANCEL)]
    if with_back:
        row.insert(0, KeyboardButton(text=texts.BTN_BACK))
    return row


def full_nav_kb(*rows: Sequence[str], with_back: bool = True) -> ReplyKeyboardMarkup:
    """Choice buttons (if any) above the ⬅️ Orqaga / ❌ Bekor qilish row, always at the bottom."""
    keyboard = [[KeyboardButton(text=label) for label in row] for row in rows]
    keyboard.append(_nav_row(with_back))
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def full_phone_kb(with_back: bool = True) -> ReplyKeyboardMarkup:
    """The contact button is the only way to answer the phone step of the full survey."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=texts.BTN_SEND_CONTACT, request_contact=True)], _nav_row(with_back)],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def full_course_kb() -> ReplyKeyboardMarkup:
    labels = [texts.course_label(c) for c in range(COURSE_MIN, COURSE_MAX + 1)]
    return full_nav_kb(labels[:3], labels[3:])


def full_citizenship_kb() -> ReplyKeyboardMarkup:
    return full_nav_kb([texts.BTN_CITIZEN_UZ, texts.BTN_CITIZEN_OTHER])


def full_region_kb() -> ReplyKeyboardMarkup:
    rows = [REGION_VALUES[i : i + 2] for i in range(0, len(REGION_VALUES), 2)]
    return full_nav_kb(*rows)


def full_employed_kb() -> ReplyKeyboardMarkup:
    return full_nav_kb([texts.BTN_EMPLOYED_YES, texts.BTN_EMPLOYED_NO])


def full_married_kb() -> ReplyKeyboardMarkup:
    return full_nav_kb([texts.BTN_MARRIED_YES, texts.BTN_MARRIED_NO])


def full_parent_kb() -> ReplyKeyboardMarkup:
    """Text step that may legitimately have no answer (an orphan's parent fields)."""
    return full_nav_kb([texts.BTN_FULL_SKIP_PARENT])


# ------------------------------------------- full survey: inline keyboards


def full_social_kb(selected: Sequence[str]) -> InlineKeyboardMarkup:
    """Multi-select: every status toggles, 🚫 clears them all, ✅ finishes the step."""
    b = InlineKeyboardBuilder()
    for code, label in texts.SOCIAL_LABELS.items():
        mark = "✅" if code in selected else "▫️"
        b.button(text=f"{mark} {label}", callback_data=FullCb(action=FL_SOCIAL, value=code))
    b.adjust(1)
    b.row(InlineKeyboardButton(text=texts.BTN_SOCIAL_NONE, callback_data=FullCb(action=FL_SOCIAL_NONE).pack()))
    b.row(InlineKeyboardButton(text=texts.BTN_SOCIAL_DONE, callback_data=FullCb(action=FL_SOCIAL_DONE).pack()))
    return b.as_markup()


def full_home_kb(can_refill: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_EDIT_FULL_DATA, callback_data=FullCb(action=FL_OPEN))
    if can_refill:
        b.button(text=texts.BTN_REREGISTER, callback_data=FullCb(action=FL_REFILL))
    b.adjust(1)
    return b.as_markup()


FULL_EDIT_FIELDS: tuple[tuple[str, str], ...] = (
    ("tg", "👨‍🏫 Tyutor / guruh"),
    ("full_name", "👤 F.I.SH"),
    ("phone", "📞 Telefon"),
    ("direction", "🎓 Yo'nalish"),
    ("course", "📚 Kurs"),
    ("birth_date", "🎂 Tug'ilgan sana"),
    ("passport", "🪪 Pasport"),
    ("pinfl", "🔢 JShShR"),
    ("citizenship", "🌐 Fuqarolik"),
    ("region", "📍 Viloyat"),
    ("district", "🏙 Shahar/tuman"),
    ("mfy", "🏘 MFY"),
    ("mfy_contact", "📞 MFY raqami"),
    ("street", "🏠 Ko'cha, uy"),
    ("employed", "💼 Ish bilan bandlik"),
    ("married", "💍 Oila"),
    ("social", "🧾 Ijtimoiy holat"),
    ("father_name", "👨 Otasi"),
    ("father_phone", "📞 Otasining tel"),
    ("father_work", "🏢 Otasining ishi"),
    ("mother_name", "👩 Onasi"),
    ("mother_phone", "📞 Onasining tel"),
    ("mother_work", "🏢 Onasining ishi"),
)
"""Everything a student may change in their full survey, as ``(field, button label)``."""


def full_edit_field_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for field, label in FULL_EDIT_FIELDS:
        b.button(text=label, callback_data=FullCb(action=FL_FIELD, value=field))
    b.adjust(1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2)
    b.row(InlineKeyboardButton(text=texts.BTN_EDIT_DONE, callback_data=FullCb(action=FL_DONE).pack()))
    return b.as_markup()


def full_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_CONFIRM, callback_data=FullCb(action=FL_CONFIRM))
    b.button(text=texts.BTN_RESTART, callback_data=FullCb(action=FL_RESTART))
    b.button(text=texts.BTN_CANCEL, callback_data=FullCb(action=FL_CANCEL))
    b.adjust(1)
    return b.as_markup()
