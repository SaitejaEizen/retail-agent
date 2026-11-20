"""FastAPI dependencies. Tests replace these with dependency_overrides."""

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from app.infra.clock import Clock
from app.infra.db import connect
from app.infra.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_connection(request: Request) -> Iterator[sqlite3.Connection]:
    """One connection per request, always closed afterwards."""
    conn = connect(get_settings(request).db_path)
    try:
        yield conn
    finally:
        conn.close()
