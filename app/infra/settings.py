"""Application settings, read once from environment variables (never from .env files)."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = "./data/retail.db"
DB_PATH_ENV_VAR = "RETAIL_DB_PATH"


@dataclass(frozen=True)
class Settings:
    db_path: Path


def load_settings() -> Settings:
    """Build Settings from the process environment, falling back to safe defaults."""
    raw = os.environ.get(DB_PATH_ENV_VAR, "").strip() or DEFAULT_DB_PATH
    return Settings(db_path=Path(raw))
