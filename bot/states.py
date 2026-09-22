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


class Broadcast(StatesGroup):
    """A superadmin composing a message to every bot user (``bot.handlers.broadcast``).

    The parts collected so far live in the FSM data as ``parts`` (see ``bot.broadcast.Part``); the
    three media steps are optional and only guide the order, any supported content is accepted in each.
    """

    text = State()  # the mandatory opening text
    photo = State()
    video = State()
    voice = State()
    review = State()  # summary with ➕ / 👁 / 📤 buttons
    add = State()  # one more part requested from the review screen
    confirm = State()  # "send to N users?"


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


class FullSurvey(StatesGroup):
    """The full questionnaire (``bot.handlers.full``), used for filling it in and for editing it.

    One state per question plus the two pickers and the preview; which questions are asked, in what
    order, and where an answer goes is decided by the step table in ``bot.handlers.full``, not here.
    ``menu`` is the field picker a saved profile is edited from.
    """

    choose_tutor = State()
    choose_group = State()
    phone = State()
    full_name = State()
    direction = State()
    course = State()
    birth_date = State()
    passport = State()
    pinfl = State()
    citizenship = State()
    citizenship_other = State()
    region = State()
    district = State()
    mfy = State()
    mfy_contact = State()
    street = State()
    employed = State()
    work_place = State()
    work_position = State()
    work_address = State()
    work_phone = State()
    married = State()
    spouse_name = State()
    spouse_work = State()
    spouse_phone = State()
    social = State()
    father_name = State()
    father_phone = State()
    father_work = State()
    mother_name = State()
    mother_phone = State()
    mother_work = State()
    confirm = State()
    menu = State()


class TutorPhone(StatesGroup):
    """A tutor typing (or sharing) their own phone number for the full survey's report."""

    phone = State()


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
