"""Reply / inline keyboards and CallbackData factories."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import texts
from .models import Group, TestUser, Tutor

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


# admin actions
ADM_PANEL = "panel"
ADM_LIST = "list"
ADM_ADD = "add"
ADM_VIEW = "view"
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
            [KeyboardButton(text=texts.BTN_RES_UY)],
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
    b.adjust(2, 2, 1, 1)
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
    b.button(text=texts.BTN_EXCEL, callback_data=AdminCb(action=ADM_EXCEL_TUTOR, tutor_id=tutor_id))
    b.button(text=texts.BTN_DELETE, callback_data=AdminCb(action=ADM_DELETE, tutor_id=tutor_id))
    b.button(text=texts.BTN_BACK, callback_data=AdminCb(action=ADM_LIST))
    b.adjust(1, 1, 2, 1)
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
    b.button(text=texts.BTN_TUTOR_EXCEL, callback_data=TutorCb(action=TUT_EXCEL_MENU))
    b.adjust(2, 1)
    return b.as_markup()


def tutor_group_list_kb(
    groups: Sequence[Group], action: str = TUT_VIEW, back_action: str = TUT_PANEL
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for group in groups:
        b.button(
            text=texts.group_button_label(group.name, group.student_count),
            callback_data=TutorCb(action=action, group_id=group.id),
        )
    b.adjust(1)
    if not groups:
        b.row(InlineKeyboardButton(text=texts.BTN_TUTOR_ADD_GROUP, callback_data=TutorCb(action=TUT_ADD).pack()))
    b.row(_back_button(texts.BTN_BACK, TutorCb(action=back_action).pack()))
    return b.as_markup()


def tutor_group_card_kb(group_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_RENAME_GROUP, callback_data=TutorCb(action=TUT_RENAME, group_id=group_id))
    b.button(text=texts.BTN_DELETE, callback_data=TutorCb(action=TUT_DELETE, group_id=group_id))
    b.button(text=texts.BTN_EXCEL, callback_data=TutorCb(action=TUT_EXCEL_GROUP, group_id=group_id))
    b.button(text=texts.BTN_BACK, callback_data=TutorCb(action=TUT_GROUPS))
    b.adjust(2, 1, 1)
    return b.as_markup()


def tutor_confirm_delete_kb(group_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_YES_DELETE, callback_data=TutorCb(action=TUT_CONFIRM_DELETE, group_id=group_id))
    b.button(text=texts.BTN_NO, callback_data=TutorCb(action=TUT_VIEW, group_id=group_id))
    b.adjust(2)
    return b.as_markup()


def tutor_excel_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_EXCEL_BY_GROUP, callback_data=TutorCb(action=TUT_EXCEL_PICK_GROUP))
    b.button(text=texts.BTN_EXCEL_BY_RESIDENCE, callback_data=TutorCb(action=TUT_EXCEL_RES))
    b.button(text=texts.BTN_EXCEL_ALL_GROUPS, callback_data=TutorCb(action=TUT_EXCEL_ALL))
    b.button(text=texts.BTN_BACK, callback_data=TutorCb(action=TUT_PANEL))
    b.adjust(1)
    return b.as_markup()


def tutor_residence_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=texts.BTN_RES_TTJ, callback_data=TutorCb(action=TUT_EXCEL_RES_PICK, value="ttj"))
    b.button(text=texts.BTN_RES_KVARTIRA, callback_data=TutorCb(action=TUT_EXCEL_RES_PICK, value="kvartira"))
    b.button(text=texts.BTN_EXCEL_RES_UY, callback_data=TutorCb(action=TUT_EXCEL_RES_PICK, value="uy"))
    b.button(text=texts.BTN_BACK, callback_data=TutorCb(action=TUT_EXCEL_MENU))
    b.adjust(3, 1)
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
