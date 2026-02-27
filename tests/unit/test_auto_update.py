"""Tests for auto-update logic."""

import sqlite3
import time
from pathlib import Path

import pytest

from dynalist_export.core.auto_update import is_update_needed, maybe_auto_update, run_auto_backup
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


def test_maybe_auto_update_imports_from_disk_when_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = _fresh_db()
    calls: list[str] = []

    def fake_import(*_args: object, **_kwargs: object) -> object:
        calls.append("import")
        attrs = {"documents_imported": 0, "documents_skipped": 0, "nodes_imported": 0}
        return type("S", (), attrs)()

    monkeypatch.setattr("dynalist_export.core.importer.loader.import_source_dir", fake_import)

    maybe_auto_update(conn, tmp_path)

    assert "import" in calls
    assert get_metadata(conn, "last_update_at") is not None


def test_maybe_auto_update_skips_when_source_dir_missing() -> None:
    conn = _fresh_db()
    missing_dir = Path("/nonexistent/path/that/does/not/exist")

    maybe_auto_update(conn, missing_dir)

    assert get_metadata(conn, "last_update_at") is None


def test_maybe_auto_update_sets_cooldown_even_on_import_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = _fresh_db()

    def failing_import(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk read failed")

    monkeypatch.setattr("dynalist_export.core.importer.loader.import_source_dir", failing_import)

    maybe_auto_update(conn, tmp_path)

    # Cooldown should be set even on failure to prevent retry storms
    assert get_metadata(conn, "last_update_at") is not None


def test_run_auto_backup_fetches_from_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeApi:
        def __init__(self, *, from_cache: bool = False) -> None:
            calls.append("api_init")

    class FakeWriter:
        def __init__(self, datadir: object, dry_run: bool) -> None:
            calls.append("writer_init")
            assert dry_run is False

        def finalize(self, *, delete_others: bool = False) -> None:
            calls.append(f"finalize(delete_others={delete_others})")

    class FakeDownloader:
        def __init__(self, writer: object) -> None:
            calls.append("downloader_init")

        def sync_all(self, api: object) -> None:
            calls.append("sync_all")

    monkeypatch.setattr("dynalist_export.core.auto_update.DynalistApi", FakeApi)
    monkeypatch.setattr("dynalist_export.core.auto_update.FileWriter", FakeWriter)
    monkeypatch.setattr("dynalist_export.core.auto_update.Downloader", FakeDownloader)

    run_auto_backup(tmp_path)

    assert calls == [
        "api_init",
        "writer_init",
        "downloader_init",
        "sync_all",
        "finalize(delete_others=False)",
    ]


def test_run_auto_backup_handles_missing_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_no_token(*, from_cache: bool = False) -> None:
        raise RuntimeError("Cannot find dynalist token file")

    monkeypatch.setattr("dynalist_export.core.auto_update.DynalistApi", raise_no_token)

    # Should not raise
    run_auto_backup(tmp_path)


def test_run_auto_backup_handles_api_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeApi:
        def __init__(self, *, from_cache: bool = False) -> None:
            pass

    class FakeWriter:
        def __init__(self, datadir: object, dry_run: bool) -> None:
            pass

        def finalize(self, *, delete_others: bool = False) -> None:
            pass

    class FakeDownloader:
        def __init__(self, writer: object) -> None:
            pass

        def sync_all(self, api: object) -> None:
            raise RuntimeError("API request failed")

    monkeypatch.setattr("dynalist_export.core.auto_update.DynalistApi", FakeApi)
    monkeypatch.setattr("dynalist_export.core.auto_update.FileWriter", FakeWriter)
    monkeypatch.setattr("dynalist_export.core.auto_update.Downloader", FakeDownloader)

    # Should not raise
    run_auto_backup(tmp_path)


def test_maybe_auto_update_runs_backup_before_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = _fresh_db()
    calls: list[str] = []

    def fake_backup(source_dir: object) -> None:
        calls.append("backup")

    def fake_import(*_args: object, **_kwargs: object) -> object:
        calls.append("import")
        attrs = {"documents_imported": 0, "documents_skipped": 0, "nodes_imported": 0}
        return type("S", (), attrs)()

    monkeypatch.setattr("dynalist_export.core.auto_update.run_auto_backup", fake_backup)
    monkeypatch.setattr("dynalist_export.core.importer.loader.import_source_dir", fake_import)

    maybe_auto_update(conn, tmp_path)

    assert calls == ["backup", "import"]
