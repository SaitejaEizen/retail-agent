from pathlib import Path

import pytest

from app.infra.settings import DB_PATH_ENV_VAR, load_settings


def test_default_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR10 / NFR4: without RETAIL_DB_PATH the DB lives at ./data/retail.db."""
    monkeypatch.delenv(DB_PATH_ENV_VAR, raising=False)
    assert load_settings().db_path == Path("./data/retail.db")


def test_db_path_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR10 / NFR4: RETAIL_DB_PATH overrides the DB location."""
    monkeypatch.setenv(DB_PATH_ENV_VAR, "/data/retail.db")
    assert load_settings().db_path == Path("/data/retail.db")


def test_blank_db_path_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR10 / NFR4: an empty RETAIL_DB_PATH is treated as unset."""
    monkeypatch.setenv(DB_PATH_ENV_VAR, "  ")
    assert load_settings().db_path == Path("./data/retail.db")
