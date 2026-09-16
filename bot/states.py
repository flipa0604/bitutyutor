"""FSM state groups."""

from aiogram.fsm.state import State, StatesGroup


class AdminTutorAdd(StatesGroup):
    name = State()
    telegram_id = State()
    confirm = State()


class AdminTutorEdit(StatesGroup):
    name = State()
    telegram_id = State()


class AdminTestUserAdd(StatesGroup):
    telegram_id = State()


class TutorGroupAdd(StatesGroup):
    name = State()


class TutorGroupEdit(StatesGroup):
    name = State()


class StudentManage(StatesGroup):
    """A tutor or superadmin messaging or deleting one student (``bot.handlers.manage``).

    ``farewell`` is the "send the deleted student a message?" question; the row is already gone by
    then, so the recipient's Telegram id and name travel in the FSM data rather than in callbacks.
    """

    message_text = State()
    farewell = State()
    farewell_text = State()


class Registration(StatesGroup):
    choose_tutor = State()
    choose_group = State()
    phone = State()
    full_name = State()
    direction = State()
    residence = State()
    address = State()
    father_name = State()
    father_phone = State()
    mother_name = State()
    mother_phone = State()
    confirm = State()


class StudentEdit(StatesGroup):
    """Editing an already saved registration, one field at a time.

    ``value`` is shared by every free-text field; which one is being edited lives in the FSM data
    under ``field`` (see ``EDIT_FIELDS`` in ``bot.handlers.student``). Residence and the tutor/group
    pair need their own keyboards, so they keep dedicated states.
    """

    menu = State()
    value = State()
    residence = State()
    address = State()
    choose_tutor = State()
    choose_group = State()
