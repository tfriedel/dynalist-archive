"""Tests for cli.py — backup pipeline orchestration."""

from pathlib import Path

from dynalist_export.cli import run_backup
from dynalist_export.writer import FileWriter
from tests.unit.fakes import FakeApi
from tests.unit.test_downloader import _make_doc, _make_file_list


def _setup_fake_api() -> FakeApi:
    """Create a FakeApi with standard responses for a full sync."""
    fake_api = FakeApi()
    fake_api.add_response("file/list", _make_file_list())
    fake_api.add_response(
        "doc/check_for_updates",
        {"versions": {"doc1": 1}, "_code": "Ok"},
    )
    fake_api.add_response("doc/read", {**_make_doc(), "_code": "Ok"})
    return fake_api


def test_run_backup_syncs_and_writes_files(tmp_path: Path) -> None:
    """run_backup syncs documents and writes output files."""
    writer = FileWriter(tmp_path, dry_run=False)
    fake_api = _setup_fake_api()

    run_backup(writer, fake_api)

    output_files = list(tmp_path.rglob("*"))
    assert any(f.suffix == ".json" for f in output_files)
    assert any(f.suffix == ".txt" for f in output_files)


def test_run_backup_skip_clean_preserves_old_files(tmp_path: Path) -> None:
    """With skip_clean=True, old files are not deleted."""
    (tmp_path / "old.json").write_text("{}")
    writer = FileWriter(tmp_path, dry_run=False)
    fake_api = _setup_fake_api()

    run_backup(writer, fake_api, skip_clean=True)

    assert (tmp_path / "old.json").exists()


def test_run_backup_without_skip_clean_deletes_old_files(
    tmp_path: Path,
) -> None:
    """Without skip_clean, old files are deleted."""
    (tmp_path / "old.json").write_text("{}")
    writer = FileWriter(tmp_path, dry_run=False)
    fake_api = _setup_fake_api()

    run_backup(writer, fake_api, skip_clean=False)

    assert not (tmp_path / "old.json").exists()
