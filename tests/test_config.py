"""Settings loading: .env encodings, token validation and clean shutdown on startup failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import main
from bot.config import ConfigError, load_settings
from bot.db import Database

_ENV_TEXT = "BOT_TOKEN=42:TEST\nSUPERADMIN_IDS=1001, 1002\n"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The process environment must not leak into (or override) the file being tested."""
    for key in ("BOT_TOKEN", "SUPERADMIN_IDS", "DB_PATH"):
        monkeypatch.delenv(key, raising=False)


def _write_env(tmp_path: Path, data: bytes) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_bytes(data)
    return env_file


@pytest.mark.parametrize(
    ("encoding", "data"),
    [("utf-8", _ENV_TEXT.encode("utf-8")), ("utf-8-bom", _ENV_TEXT.encode("utf-8-sig"))],
)
def test_env_file_with_and_without_bom(tmp_path: Path, encoding: str, data: bytes) -> None:
    settings = load_settings(_write_env(tmp_path, data))
    assert settings.bot_token == "42:TEST"
    assert settings.superadmin_ids == frozenset({1001, 1002})


def test_env_file_in_utf16_gives_clear_config_error(tmp_path: Path) -> None:
    env_file = _write_env(tmp_path, _ENV_TEXT.encode("utf-16"))  # what PowerShell 5.1 `>` produces
    with pytest.raises(ConfigError, match="UTF-8"):
        load_settings(env_file)


@pytest.mark.parametrize("token", ["abc", "42TEST", "42:", "42: TEST", ":TEST"])
def test_malformed_token_is_a_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setenv("BOT_TOKEN", token)
    monkeypatch.setenv("SUPERADMIN_IDS", "1")
    with pytest.raises(ConfigError, match="malformed"):
        load_settings(tmp_path / "missing.env")


def test_missing_token_is_a_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERADMIN_IDS", "1")
    with pytest.raises(ConfigError, match="BOT_TOKEN is not set"):
        load_settings(tmp_path / "missing.env")


async def test_main_exits_cleanly_on_malformed_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "abc")
    monkeypatch.setenv("SUPERADMIN_IDS", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bot.db"))
    opened: list[Any] = []
    monkeypatch.setattr(Database, "init", _spy(opened))
    with pytest.raises(SystemExit) as exc_info:
        await main.main()
    assert exc_info.value.code == 1
    assert not opened  # nothing (no DB worker thread) is started for a bad configuration


async def test_main_closes_db_when_startup_fails_after_opening_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unclosed aiosqlite connection keeps the process alive, so the DB must always be closed."""
    monkeypatch.setenv("BOT_TOKEN", "42:TEST")
    monkeypatch.setenv("SUPERADMIN_IDS", "1")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "bot.db"))
    closed: list[Any] = []
    original_close = Database.close

    async def close(self: Database) -> None:
        closed.append(self._conn is not None)  # was still open when the shutdown path ran
        await original_close(self)

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("startup failed")

    monkeypatch.setattr(Database, "close", close)
    monkeypatch.setattr(main, "setup_bot_commands", boom)
    with pytest.raises(RuntimeError, match="startup failed"):
        await main.main()
    assert closed == [True]


def _spy(calls: list[Any]) -> Any:
    async def spy(self: Any) -> None:
        calls.append(self)

    return spy
