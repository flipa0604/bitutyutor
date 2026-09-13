"""Application settings loaded from the environment / ``.env`` file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aiogram.utils.token import TokenValidationError, validate_token
from dotenv import load_dotenv

DEFAULT_DB_PATH = "data/bot.db"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime configuration."""

    bot_token: str
    superadmin_ids: frozenset[int]
    db_path: Path

    def is_superadmin(self, user_id: int) -> bool:
        return user_id in self.superadmin_ids


def parse_superadmin_ids(raw: str | None) -> frozenset[int]:
    """Parse ``SUPERADMIN_IDS`` (comma-separated, whitespace tolerated) into a set of ints."""
    if raw is None or not raw.strip():
        raise ConfigError("SUPERADMIN_IDS is empty. Set it in .env, e.g. SUPERADMIN_IDS=111111111,222222222")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or int(part) <= 0:
            raise ConfigError(f"SUPERADMIN_IDS contains an invalid Telegram ID: {part!r}")
        ids.add(int(part))
    if not ids:
        raise ConfigError("SUPERADMIN_IDS does not contain any Telegram ID")
    return frozenset(ids)


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Load settings from ``env_file`` (default: ``<project>/.env``) and the process environment.

    Fails fast with :class:`ConfigError` when ``.env`` is not UTF-8, ``BOT_TOKEN`` is missing or
    malformed, or ``SUPERADMIN_IDS`` is invalid.
    """
    dotenv_path = Path(env_file) if env_file is not None else PROJECT_ROOT / ".env"
    if dotenv_path.is_file():
        try:
            # utf-8-sig: Windows editors/PowerShell often write a BOM, which would otherwise end up
            # inside the first key name ("﻿BOT_TOKEN") and look like a missing token.
            load_dotenv(dotenv_path, override=False, encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ConfigError(f"{dotenv_path} must be saved as UTF-8 (it is not valid UTF-8: {exc.reason})") from exc

    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise ConfigError("BOT_TOKEN is not set. Copy .env.example to .env and fill in the token from @BotFather")
    try:
        validate_token(token)
    except TokenValidationError as exc:
        raise ConfigError(f"BOT_TOKEN is malformed ({exc}). Paste the token exactly as @BotFather sent it") from exc

    superadmin_ids = parse_superadmin_ids(os.getenv("SUPERADMIN_IDS"))
    db_path = Path((os.getenv("DB_PATH") or "").strip() or DEFAULT_DB_PATH)
    return Settings(bot_token=token, superadmin_ids=superadmin_ids, db_path=db_path)
