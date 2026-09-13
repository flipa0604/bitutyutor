"""openpyxl workbook builders. All builders are synchronous and return the ``.xlsx`` bytes."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .models import Group, Student, Tutor
from .texts import residence_label

StudentRow = Student
"""A student row: :class:`Student` already carries ``tutor_name`` and ``group_name``."""

ALL_SHEET_NAME = "Barchasi"
MAX_SHEET_NAME_LEN = 31
RESERVED_SHEET_NAME = "History"  # Excel keeps this name for its own change-history sheet

HEADERS: tuple[str, ...] = (
    "№",
    "F.I.SH",
    "Telefon",
    "Yo'nalish",
    "Tyutor",
    "Guruh",
    "Turar joy",
    "Manzil",
    "Otasining F.I.SH",
    "Otasining tel",
    "Onasining F.I.SH",
    "Onasining tel",
    "Telegram username",
    "Telegram ID",
    "Ro'yxatdan o'tgan vaqt",
    "Oxirgi tahrir",
)
COLUMN_WIDTHS: tuple[int, ...] = (5, 32, 16, 24, 26, 16, 12, 36, 32, 16, 32, 16, 20, 14, 20, 20)
_TEXT_COLUMNS = {3, 10, 12}  # 1-based indexes of phone columns; forced to text format

_INVALID_SHEET_CHARS_RE = re.compile(r"[\[\]:*?/\\]")
_SHEET_EDGE_RE = re.compile(r"^[\s']+|[\s']+$")  # Excel forbids a leading/trailing apostrophe
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill(fill_type="solid", fgColor="D9E1F2")
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def sanitize_sheet_name(name: str) -> str:
    """Make ``name`` a valid Excel sheet title: no ``[]:*?/\\``, no edge apostrophes, at most 31 chars."""
    cleaned = _SHEET_EDGE_RE.sub("", _INVALID_SHEET_CHARS_RE.sub("", name))
    # Truncation can expose a new trailing apostrophe (e.g. "... o'g'li" cut at "o'"), so strip again.
    cleaned = _SHEET_EDGE_RE.sub("", cleaned[:MAX_SHEET_NAME_LEN])
    if cleaned.lower() == RESERVED_SHEET_NAME.lower():
        cleaned += "_"
    return cleaned or "Sheet"


def unique_sheet_names(names: Iterable[str]) -> list[str]:
    """Sanitise names and make them unique (case-insensitively) by appending `` (2)``, `` (3)``, ..."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in names:
        base = sanitize_sheet_name(raw)
        candidate = base
        counter = 2
        while candidate.lower() in seen:
            suffix = f" ({counter})"
            candidate = _SHEET_EDGE_RE.sub("", base[: MAX_SHEET_NAME_LEN - len(suffix)]) + suffix
            counter += 1
        seen.add(candidate.lower())
        result.append(candidate)
    return result


def _fill_sheet(ws: Worksheet, students: Sequence[StudentRow]) -> None:
    ws.append(list(HEADERS))
    for cell in ws[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN
        cell.border = _BORDER

    for index, s in enumerate(students, start=1):
        ws.append(
            [
                index,
                s.full_name,
                str(s.phone),
                s.direction,
                s.tutor_name,
                s.group_name,
                residence_label(s.residence),
                s.address,
                s.father_name,
                str(s.father_phone),
                s.mother_name,
                str(s.mother_phone),
                f"@{s.username}" if s.username else None,
                s.telegram_id,
                s.created_at,
                # NULL until the data is changed for the first time, so a filled cell means
                # "edited since registration" at a glance.
                s.edited_at,
            ]
        )
        row = ws[index + 1]
        for col_index, cell in enumerate(row, start=1):
            cell.border = _BORDER
            if col_index in _TEXT_COLUMNS:
                cell.number_format = "@"

    for col_index, width in enumerate(COLUMN_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(col_index)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{max(ws.max_row, 1)}"


def build_students_workbook(sheets: Sequence[tuple[str, Sequence[StudentRow]]]) -> bytes:
    """Build a workbook with one sheet per ``(name, students)`` pair and return its bytes."""
    wb = Workbook()
    default = wb.active
    if default is not None:
        wb.remove(default)
    if not sheets:
        sheets = [(ALL_SHEET_NAME, [])]
    names = unique_sheet_names(name for name, _ in sheets)
    for title, (_, students) in zip(names, sheets, strict=True):
        ws = wb.create_sheet(title=title)
        _fill_sheet(ws, students)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_group_workbook(group: Group, students: Sequence[StudentRow]) -> bytes:
    """Single sheet named after the group."""
    return build_students_workbook([(group.name, students)])


def build_residence_workbook(residence: str, students: Sequence[StudentRow]) -> bytes:
    """Single sheet named after the residence label (rows keep their ``Guruh`` column)."""
    return build_students_workbook([(residence_label(residence), students)])


def build_tutor_workbook(groups: Sequence[Group], students: Sequence[StudentRow]) -> bytes:
    """Sheet ``Barchasi`` with all of the tutor's students + one sheet per group."""
    sheets: list[tuple[str, Sequence[StudentRow]]] = [(ALL_SHEET_NAME, students)]
    for group in groups:
        sheets.append((group.name, [s for s in students if s.group_id == group.id]))
    return build_students_workbook(sheets)


def build_all_tutors_workbook(tutors: Sequence[Tutor], students: Sequence[StudentRow]) -> bytes:
    """Sheet ``Barchasi`` with every student + one sheet per tutor."""
    sheets: list[tuple[str, Sequence[StudentRow]]] = [(ALL_SHEET_NAME, students)]
    for tutor in tutors:
        sheets.append((tutor.name, [s for s in students if s.tutor_id == tutor.id]))
    return build_students_workbook(sheets)
