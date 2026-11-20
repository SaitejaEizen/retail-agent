"""SQLite connection handling and startup initialisation (AD-7)."""

import logging
import sqlite3
from datetime import date
from pathlib import Path

from app.infra import seed

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

logger = logging.getLogger(__name__)


def connect(db_path: Path, *, create: bool = False) -> sqlite3.Connection:
    """Open a connection with foreign keys on and rows accessible by column name.

    Without ``create``, the file must already exist (``mode=rw``), so a missing
    database fails loudly instead of being silently recreated empty.
    """
    mode = "rwc" if create else "rw"
    uri = f"{Path(db_path).resolve().as_uri()}?mode={mode}"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path, today: date) -> None:
    """Create the DB file and parent directory if needed, apply the schema, seed if empty."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path, create=True)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        loaded = seed.load_seed(conn, today)
    finally:
        conn.close()
    if loaded:
        logger.info("Seeded %d orders (reference date %s)", loaded, today.isoformat())
    else:
        logger.info("Database already seeded; leaving existing rows untouched")
