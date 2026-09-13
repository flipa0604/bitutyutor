"""FSM state groups."""

from aiogram.fsm.state import State, StatesGroup


class AdminTutorAdd(StatesGroup):
    name = State()
    telegram_id = State()
    confirm = State()


class AdminTutorEdit(StatesGroup):
    name = State()
    telegram_id = State()


class TutorGroupAdd(StatesGroup):
    name = State()


class TutorGroupEdit(StatesGroup):
    name = State()


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
