"""Plain dataclasses mirroring database rows."""

from __future__ import annotations

from dataclasses import dataclass

RESIDENCE_VALUES: tuple[str, ...] = ("ttj", "kvartira", "uy", "qarindosh")
"""Residence codes stored in ``students.residence``; every code but ``ttj`` comes with a street
address. Appending a code here is enough for the database (``bot.db`` rebuilds its CHECK constraint
on the next start); the keyboards and the Excel filter still need a button and a label."""


SURVEY_BASIC = "basic"
SURVEY_FULL = "full"
SURVEY_VALUES: tuple[str, ...] = (SURVEY_BASIC, SURVEY_FULL)
"""The two questionnaires a student can fill in. They share the tutor and group lists but keep their
answers in separate tables (``students`` and ``full_profiles``), so one can be filled, edited or
deleted without touching the other."""


@dataclass(frozen=True, slots=True)
class Tutor:
    id: int
    name: str
    telegram_id: int
    created_at: str
    phone: str = ""
    """The tutor's own number, asked of the tutor (never of a student); a column of the full survey."""


@dataclass(frozen=True, slots=True)
class BotUser:
    """Someone who has pressed /start, whether or not they finished registering."""

    telegram_id: int
    username: str | None
    full_name: str
    started_at: str
    last_start_at: str
    is_student: bool = False


@dataclass(frozen=True, slots=True)
class TestUser:
    """A Telegram ID allowed to run the registration flow again after it already has a row.

    ``name`` and ``username`` are looked up from the ``users`` table when that person has ever
    pressed /start, so the admin list stays readable without asking for a label.
    """

    telegram_id: int
    name: str
    created_at: str
    username: str | None = None


@dataclass(frozen=True, slots=True)
class Group:
    id: int
    tutor_id: int
    name: str
    created_at: str
    student_count: int = 0
    """How many filled the basic questionnaire in this group."""
    profile_count: int = 0
    """How many filled the full one -- a different set of people, counted on its own."""


@dataclass(frozen=True, slots=True)
class Student:
    id: int
    telegram_id: int
    username: str | None
    tutor_id: int
    group_id: int
    full_name: str
    phone: str
    direction: str
    residence: str
    address: str
    father_name: str
    father_phone: str
    mother_name: str
    mother_phone: str
    created_at: str
    updated_at: str
    edited_at: str | None = None
    """When the data was last changed after registration; ``None`` while it never was."""
    tutor_name: str = ""
    group_name: str = ""


SOCIAL_VALUES: tuple[str, ...] = (
    "yoshlar_daftari",
    "ijtimoiy_reestr",
    "kam_taminlangan",
    "nogiron",
    "yetim",
    "chin_yetim",
)
"""Codes of ``FullProfile.social_status`` (stored comma-separated; empty string = none of them)."""

REGION_VALUES: tuple[str, ...] = (
    "Qoraqalpog'iston Respublikasi",
    "Andijon",
    "Buxoro",
    "Farg'ona",
    "Jizzax",
    "Namangan",
    "Navoiy",
    "Qashqadaryo",
    "Samarqand",
    "Sirdaryo",
    "Surxondaryo",
    "Toshkent viloyati",
    "Toshkent shahri",
    "Xorazm",
)

COURSE_MIN, COURSE_MAX = 1, 6


@dataclass(frozen=True, slots=True)
class FullProfile:
    """One row of the full survey (``full_profiles``). Every column the tutors' report asks for.

    ``tutor_phone`` comes from the tutor's own record, not from the student; the work and spouse
    blocks stay empty unless ``employed`` / ``married`` says otherwise.
    """

    id: int
    telegram_id: int
    username: str | None
    tutor_id: int
    group_id: int
    full_name: str
    phone: str
    direction: str
    course: int
    passport: str
    pinfl: str
    birth_date: str  # as entered: DD.MM.YYYY
    citizenship: str
    region: str
    district: str
    mfy: str
    mfy_contact: str
    street: str
    employed: bool
    work_place: str
    work_position: str
    work_address: str
    work_phone: str
    married: bool
    spouse_name: str
    spouse_work: str
    spouse_phone: str
    social_status: str  # comma-separated ``SOCIAL_VALUES`` codes
    father_name: str
    father_phone: str
    father_work: str
    mother_name: str
    mother_phone: str
    mother_work: str
    created_at: str
    updated_at: str
    edited_at: str | None = None
    tutor_name: str = ""
    tutor_phone: str = ""
    group_name: str = ""

    @property
    def social_codes(self) -> list[str]:
        return [code for code in self.social_status.split(",") if code]
