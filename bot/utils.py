"""Validation, normalisation and small Telegram helpers shared by handlers."""

from __future__ import annotations

import html
import logging
import re
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

log = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^\+998\d{9}$")
NAME_MIN_LEN = 3
NAME_MAX_LEN = 150
_TELEGRAM_ID_RE = re.compile(r"[0-9]{1,19}")  # ASCII digits only: str.isdigit() also accepts '²' or '٣'
MAX_TELEGRAM_ID = 2**63 - 1  # largest SQLite INTEGER; real Telegram IDs are far below it
_WS_RE = re.compile(r"\s+")
_UNSAFE_FILENAME_RE = re.compile(r"[^\w\-]+", re.UNICODE)


def hesc(value: object) -> str:
    """Escape a user-supplied value for use inside an HTML-formatted Telegram message."""
    return html.escape(str(value), quote=False)


def clean_text(text: str | None) -> str:
    """Strip and collapse internal whitespace."""
    return _WS_RE.sub(" ", (text or "").strip())


def is_valid_phone(text: str | None) -> bool:
    """Strict check: ``+998`` followed by exactly nine digits (after strip)."""
    return bool(text) and PHONE_RE.fullmatch(text.strip()) is not None


def normalize_phone(raw: str | None) -> str | None:
    """Normalise a contact phone number (may lack ``+``, may contain spaces/dashes) to ``+998XXXXXXXXX``.

    Returns ``None`` when the number is not an Uzbek mobile number.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    if len(digits) == 9:
        return "+998" + digits
    return None


def is_valid_name(text: str | None) -> bool:
    """Full name: 3..150 chars after cleaning, at least two words, no digits."""
    value = clean_text(text)
    if not NAME_MIN_LEN <= len(value) <= NAME_MAX_LEN:
        return False
    if any(ch.isdigit() for ch in value):
        return False
    return len(value.split()) >= 2


def is_valid_length(text: str | None, min_len: int, max_len: int) -> bool:
    """Check that the cleaned text length lies within ``[min_len, max_len]``."""
    return min_len <= len(clean_text(text)) <= max_len


def parse_telegram_id(text: str | None) -> int | None:
    """Parse a positive integer Telegram user ID from text; ``None`` when invalid or not storable."""
    value = (text or "").strip()
    if _TELEGRAM_ID_RE.fullmatch(value) is None:
        return None
    number = int(value)
    return number if 0 < number <= MAX_TELEGRAM_ID else None


_PASSPORT_RE = re.compile(r"^[A-Z]{2}\d{7}$")
_CYRILLIC_LOOKALIKES = str.maketrans("АВСЕКМНОРТХУІ", "ABCEKMHOPTXYI")
"""Uzbek passport series are printed in Latin, but phone keyboards happily produce the Cyrillic
letters that look the same; they mean the same series, so they are folded before checking."""

PINFL_LEN = 14
_BIRTH_DATE_RE = re.compile(r"^(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{4})$")
STUDENT_MIN_AGE, STUDENT_MAX_AGE = 15, 70


def normalize_passport(text: str | None) -> str | None:
    """``AA1234567`` from what the student typed (spaces, lowercase, Cyrillic lookalikes), else ``None``."""
    value = re.sub(r"[\s\-]", "", (text or "")).upper().translate(_CYRILLIC_LOOKALIKES)
    return value if _PASSPORT_RE.fullmatch(value) else None


def parse_birth_date(text: str | None) -> date | None:
    """Parse ``DD.MM.YYYY`` (also ``/``, ``-`` or a space) and accept only a plausible student age."""
    match = _BIRTH_DATE_RE.fullmatch(clean_text(text))
    if match is None:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        value = date(year, month, day)
    except ValueError:  # 31.02.2004 and friends
        return None
    today = date.today()
    if value > today:
        return None
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    return value if STUDENT_MIN_AGE <= age <= STUDENT_MAX_AGE else None


def normalize_pinfl(text: str | None, birth: date) -> str | None:
    """Check a JShShR (PNFL) against the birth date the student already gave; ``None`` when it lies.

    The first digit encodes century and sex (3/4 = 1900s male/female, 5/6 = 2000s), digits 2..7 are
    the birth date as ``DDMMYY``. A number invented on the spot practically never lines up with both,
    which is what makes this worth checking.
    """
    value = re.sub(r"\s", "", text or "")
    if not value.isdigit() or len(value) != PINFL_LEN:
        return None
    century = {"3": 19, "4": 19, "5": 20, "6": 20}.get(value[0])
    if century is None or century != birth.year // 100:
        return None
    return value if value[1:7] == birth.strftime("%d%m%y") else None


def safe_filename_part(name: str, max_len: int = 40) -> str:
    """Reduce an arbitrary string to filename-safe characters (unicode letters, digits, ``_``, ``-``)."""
    cleaned = _UNSAFE_FILENAME_RE.sub("_", name).strip("_")
    cleaned = re.sub(r"_+", "_", cleaned)
    return (cleaned or "fayl")[:max_len].strip("_") or "fayl"


def today_str() -> str:
    return date.today().isoformat()


async def edit_or_send(
    callback: CallbackQuery,
    bot: Bot,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the message a callback originated from; fall back to a new message when editing is impossible."""
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc):
                return
            log.debug("edit_text failed (%s); sending a new message instead", exc)
    await bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)


async def remove_inline_keyboard(callback: CallbackQuery) -> None:
    """Best-effort removal of the inline keyboard from the message that triggered ``callback``."""
    message = callback.message
    if not isinstance(message, Message):
        return
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as exc:
        log.debug("edit_reply_markup failed: %s", exc)
