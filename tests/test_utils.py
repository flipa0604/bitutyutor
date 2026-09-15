"""Phone normalisation/validation matrix, name validation and small helpers."""

from __future__ import annotations

import pytest

from bot.texts import parse_residence, residence_label
from bot.utils import (
    clean_text,
    hesc,
    is_valid_length,
    is_valid_name,
    is_valid_phone,
    normalize_phone,
    parse_telegram_id,
    safe_filename_part,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+998901234567", "+998901234567"),
        ("998901234567", "+998901234567"),
        ("+998 90 123-45-67", "+998901234567"),
        ("(998) 90 123 45 67", "+998901234567"),
        ("901234567", "+998901234567"),
        ("90 123 45 67", "+998901234567"),
        ("+79161234567", None),
        ("+99890123456", None),
        ("+9989012345678", None),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_normalize_phone(raw: str | None, expected: str | None) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("+998901234567", True),
        ("  +998901234567  ", True),
        ("998901234567", False),
        ("+998 90 123 45 67", False),
        ("+99890123456", False),
        ("+9989012345678", False),
        ("+998abcdefghi", False),
        ("+79161234567", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_phone(text: str | None, expected: bool) -> None:
    assert is_valid_phone(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Aliyev Vali G'aniyevich", True),
        ("Aliyev Vali", True),
        ("  Aliyev   Vali  ", True),
        ("Aliyev", False),
        ("Aliyev Vali 2", False),
        ("Al", False),
        ("A B", True),
        ("x" * 151 + " y", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_name(text: str | None, expected: bool) -> None:
    assert is_valid_name(text) is expected


def test_clean_text_collapses_whitespace() -> None:
    assert clean_text("  a \n\t b   c ") == "a b c"
    assert clean_text(None) == ""


def test_is_valid_length_uses_cleaned_text() -> None:
    assert is_valid_length("  ab ", 2, 5)
    assert not is_valid_length(" a ", 2, 5)
    assert not is_valid_length("abcdef", 2, 5)
    assert not is_valid_length(None, 1, 5)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("123456789", 123456789),
        (" 42 ", 42),
        ("0", None),
        ("-5", None),
        ("abc", None),
        ("", None),
        (None, None),
        # str.isdigit() is true for these, but int() rejects them or SQLite cannot store them
        ("²", None),
        ("٣٤", None),
        ("99999999999999999999", None),
        (str(2**63), None),
        (str(2**63 - 1), 2**63 - 1),
        ("+123", None),
        ("1 2", None),
    ],
)
def test_parse_telegram_id(text: str | None, expected: int | None) -> None:
    assert parse_telegram_id(text) == expected


def test_hesc_escapes_html_but_keeps_apostrophes() -> None:
    assert hesc("<b>&</b>") == "&lt;b&gt;&amp;&lt;/b&gt;"
    assert hesc("G'aniyevich") == "G'aniyevich"
    assert hesc(123) == "123"


def test_safe_filename_part() -> None:
    assert safe_filename_part("Aliyev Vali G'aniyevich") == "Aliyev_Vali_G_aniyevich"
    assert safe_filename_part("DI-21/01") == "DI-21_01"
    assert safe_filename_part("///") == "fayl"
    assert len(safe_filename_part("x" * 100)) == 40


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("🏠 TTJ", "ttj"),
        ("🏢 Kvartira", "kvartira"),
        ("🏡 O'zimning uyimda", "uy"),
        ("🏘️ Qarindoshinikida", "qarindosh"),
        ("ttj", "ttj"),
        ("Kvartira", "kvartira"),
        ("o'zimning uyimda", "uy"),
        ("uy", "uy"),
        ("qarindoshinikida", "qarindosh"),
        ("Qarindoshimnikida", "qarindosh"),
        ("qarindosh", "qarindosh"),
        ("qarindoshim", None),
        ("boshqa", None),
        (None, None),
        # apostrophe variants phone keyboards produce: ‘ (U+2018), ’ (U+2019, iOS smart punctuation),
        # ʻ (U+02BB, Gboard Uzbek), ʼ (U+02BC), ` and ´
        ("O‘zimning uyimda", "uy"),
        ("O’zimning uyimda", "uy"),
        ("Oʻzimning uyimda", "uy"),
        ("Oʼz uyi", "uy"),
        ("O`z uyim", "uy"),
        ("O´zimning uyimda", "uy"),
        ("  O’zimning   uyimda  ", "uy"),
        ("O’zga joyda", None),
    ],
)
def test_parse_residence(text: str | None, expected: str | None) -> None:
    assert parse_residence(text) == expected


def test_residence_label() -> None:
    assert residence_label("ttj") == "TTJ"
    assert residence_label("kvartira") == "Kvartira"
    assert residence_label("uy") == "O'z uyi"
    assert residence_label("qarindosh") == "Qarindoshinikida"
