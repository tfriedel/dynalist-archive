"""Tests for auto-update logic."""

import sqlite3
import time
from pathlib import Path

import pytest

from dynalist_export.core.auto_update import is_update_needed, maybe_auto_update
from dynalist_export.core.database.schema import create_schema, get_metadata, set_metadata


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    return conn


def test_get_metadata_returns_none_for_missing_key() -> None:
    conn = _fresh_db()
    assert get_metadata(conn, "nonexistent") is None


def test_set_and_get_metadata_roundtrip() -> None:
    conn = _fresh_db()
    set_metadata(conn, "my_key", "my_value")
    assert get_metadata(conn, "my_key") == "my_value"


def test_is_update_needed_true_when_never_updated() -> None:
    conn = _fresh_db()
    assert is_update_needed(conn, interval=300) is True


def test_is_update_needed_false_within_cooldown() -> None:
    conn = _fresh_db()
    # Simulate a recent update
    set_metadata(conn, "last_update_at", str(int(time.time())))
    assert is_update_needed(conn, interval=300) is False


def test_is_update_needed_true_after_cooldown_expires() -> None:
    conn = _fresh_db()
    # Simulate an update 10 minutes ago
    set_metadata(conn, "last_update_at", str(int(time.time()) - 600))
    assert is_update_needed(conn, interval=300) is True


def test_maybe_auto_update_skips_within_cooldown(tmp_path: Path) -> None:
    conn = _fresh_db()
    set_metadata(conn, "last_update_at", str(int(time.time())))
    # Should return without doing anything (no API token needed)
    maybe_auto_update(conn, tmp_path)


def test_maybe_auto_update_runs_sync_when_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = _fresh_db()
    calls: list[str] = []

    def fake_run_backup(*_args: object, **_kwargs: object) -> None:
        calls.append("run_backup")

    def fake_import(*_args: object, **_kwargs: object) -> object:
        calls.append("import")
        attrs = {"documents_imported": 0, "documents_skipped": 0, "nodes_imported": 0}
        return type("S", (), attrs)()

    monkeypatch.setattr("dynalist_export.api.DynalistApi", lambda: None)
    monkeypatch.setattr("dynalist_export.cli.run_backup", fake_run_backup)
    monkeypatch.setattr("dynalist_export.core.importer.loader.import_source_dir", fake_import)
    monkeypatch.setattr("dynalist_export.writer.FileWriter", lambda *_a, **_kw: None)

    maybe_auto_update(conn, tmp_path)

    assert "run_backup" in calls
    assert "import" in calls
    assert get_metadata(conn, "last_update_at") is not None


def test_maybe_auto_update_skips_silently_without_api_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = _fresh_db()

    def raise_no_token() -> None:
        raise RuntimeError("No API token found")

    monkeypatch.setattr("dynalist_export.api.DynalistApi", raise_no_token)

    maybe_auto_update(conn, tmp_path)

    # Should not crash, and should not set last_update_at
    assert get_metadata(conn, "last_update_at") is None
