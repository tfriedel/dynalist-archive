"""Tests for FileWriter — smart file writer with git support."""

import json
import subprocess
from pathlib import Path

import pytest

from dynalist_export.writer import FileWriter


def test_init_creates_writer_for_valid_directory(tmp_path: Path) -> None:
    """FileWriter accepts an existing directory."""
    writer = FileWriter(tmp_path, dry_run=False)

    assert writer.datadir == str(tmp_path.resolve())
    assert writer.dry_run is False


def test_init_raises_for_missing_directory(tmp_path: Path) -> None:
    """FileWriter raises ValueError when directory does not exist."""
    missing = tmp_path / "does_not_exist"

    with pytest.raises(ValueError, match="not found"):
        FileWriter(missing, dry_run=False)


def test_init_dry_run_allows_missing_directory(tmp_path: Path) -> None:
    """In dry-run mode, missing directory is allowed."""
    missing = tmp_path / "does_not_exist"
    writer = FileWriter(missing, dry_run=True)

    assert writer.dry_run is True


def test_is_possible_output_accepts_json_and_txt(tmp_path: Path) -> None:
    """Only .json and .txt files are valid output files."""
    writer = FileWriter(tmp_path, dry_run=False)

    assert writer.is_possible_output("test.json") is True
    assert writer.is_possible_output("test.txt") is True
    assert writer.is_possible_output("test.py") is False
    assert writer.is_possible_output("test") is False


def test_make_unique_name_returns_base_when_no_collision(tmp_path: Path) -> None:
    """First call returns the base name unchanged."""
    writer = FileWriter(tmp_path, dry_run=False)

    result = writer.make_unique_name("notes")

    assert result == "notes"


def test_make_unique_name_appends_number_on_collision(tmp_path: Path) -> None:
    """Second call with same base appends -1."""
    writer = FileWriter(tmp_path, dry_run=False)
    writer.make_unique_name("notes")

    result = writer.make_unique_name("notes")

    assert result == "notes-1"


def test_make_unique_name_rejects_path_escaping(tmp_path: Path) -> None:
    """Absolute paths in base name are rejected."""
    writer = FileWriter(tmp_path, dry_run=False)

    with pytest.raises(ValueError, match="Path escapes datadir"):
        writer.make_unique_name("/etc/passwd")


def test_make_data_file_writes_json_from_data(tmp_path: Path) -> None:
    """Writing with data= serializes as pretty JSON."""
    writer = FileWriter(tmp_path, dry_run=False)

    writer.make_data_file("test.json", data={"key": "value"})

    written = (tmp_path / "test.json").read_text()
    assert json.loads(written) == {"key": "value"}


def test_make_data_file_writes_string_from_contents(tmp_path: Path) -> None:
    """Writing with contents= writes the string directly."""
    writer = FileWriter(tmp_path, dry_run=False)

    writer.make_data_file("notes.txt", contents="hello world")

    assert (tmp_path / "notes.txt").read_text() == "hello world"


def test_make_data_file_rejects_both_contents_and_data(tmp_path: Path) -> None:
    """Providing both contents and data raises ValueError."""
    writer = FileWriter(tmp_path, dry_run=False)

    with pytest.raises(ValueError, match="Cannot specify both"):
        writer.make_data_file("test.json", contents="text", data={"key": "val"})


def test_make_data_file_skips_unchanged_content(tmp_path: Path) -> None:
    """Writing identical content twice does not increment changed count."""
    writer = FileWriter(tmp_path, dry_run=False)
    writer.make_data_file("test.json", data={"a": 1})
    writer.make_data_file("test.json", data={"a": 1})

    assert writer._num_same == 1
    assert writer._num_changed == 0


def test_make_data_file_rejects_absolute_path(tmp_path: Path) -> None:
    """Absolute file paths are rejected."""
    writer = FileWriter(tmp_path, dry_run=False)

    with pytest.raises(ValueError, match="must be relative"):
        writer.make_data_file("/etc/test.json", data={})


def test_make_data_file_creates_subdirectories(tmp_path: Path) -> None:
    """Writing to a nested path creates parent directories."""
    writer = FileWriter(tmp_path, dry_run=False)

    writer.make_data_file("sub/dir/test.json", data={"nested": True})

    assert (tmp_path / "sub" / "dir" / "test.json").exists()


def test_try_read_json_returns_parsed_data(tmp_path: Path) -> None:
    """Reading an existing JSON file returns parsed contents."""
    writer = FileWriter(tmp_path, dry_run=False)
    (tmp_path / "data.json").write_text('{"x": 42}')

    result = writer.try_read_json("data.json")

    assert result == {"x": 42}


def test_try_read_json_returns_none_for_missing_file(tmp_path: Path) -> None:
    """Reading a nonexistent file returns None."""
    writer = FileWriter(tmp_path, dry_run=False)

    result = writer.try_read_json("missing.json")

    assert result is None


def test_check_git_raises_without_git_dir(tmp_path: Path) -> None:
    """check_git raises ValueError when .git directory is missing."""
    writer = FileWriter(tmp_path, dry_run=False)

    with pytest.raises(ValueError, match="does not have a git repo"):
        writer.check_git()


def test_check_git_passes_with_git_dir(tmp_path: Path) -> None:
    """check_git succeeds when .git directory exists."""
    (tmp_path / ".git").mkdir()
    writer = FileWriter(tmp_path, dry_run=False)

    writer.check_git()  # Should not raise


def test_finalize_reports_no_changes_when_nothing_written(tmp_path: Path) -> None:
    """Finalizing with no writes produces 'no changes' message."""
    writer = FileWriter(tmp_path, dry_run=False)

    writer.finalize()

    assert writer.short_diff_message == "no changes"


def test_finalize_generates_detailed_diff_message(tmp_path: Path) -> None:
    """Finalizing after writing new .txt files produces detailed message."""
    writer = FileWriter(tmp_path, dry_run=False)
    writer.make_data_file("notes.txt", contents="hello")

    writer.finalize()

    assert "notes" in writer.short_diff_message  # type: ignore[operator]


def test_finalize_deletes_old_files_when_requested(tmp_path: Path) -> None:
    """Finalize with delete_others=True removes files not written this session."""
    (tmp_path / "old.json").write_text("{}")
    writer = FileWriter(tmp_path, dry_run=False)
    writer.make_data_file("new.json", data={})

    writer.finalize(delete_others=True)

    assert not (tmp_path / "old.json").exists()
    assert (tmp_path / "new.json").exists()


def test_finalize_aborts_cleanup_on_suspicious_files(tmp_path: Path) -> None:
    """Finalize refuses to delete when non-output files are found."""
    (tmp_path / "script.py").write_text("print('hi')")
    writer = FileWriter(tmp_path, dry_run=False)

    with pytest.raises(SystemExit, match="suspicious"):
        writer.finalize(delete_others=True)


def _init_git_repo(path: Path) -> None:
    """Initialize a real git repo for testing."""
    subprocess.check_call(["git", "init", "--initial-branch=main"], cwd=path)
    subprocess.check_call(["git", "config", "user.email", "test@test.com"], cwd=path)
    subprocess.check_call(["git", "config", "user.name", "Test"], cwd=path)
    # Need an initial commit for git status to work properly
    (path / ".gitkeep").write_text("")
    subprocess.check_call(["git", "add", "."], cwd=path)
    subprocess.check_call(["git", "commit", "-m", "init", "--quiet"], cwd=path)


def test_git_commit_creates_commit_when_changes_exist(tmp_path: Path) -> None:
    """git_commit creates a commit when there are pending changes."""
    _init_git_repo(tmp_path)
    writer = FileWriter(tmp_path, dry_run=False)
    writer.make_data_file("test.json", data={"a": 1})
    writer.finalize()

    writer.git_commit(dry_run=False)

    log = subprocess.check_output(
        ["git", "log", "--oneline"], cwd=tmp_path
    ).decode()
    assert len(log.strip().splitlines()) == 2  # init + our commit


def test_git_commit_skips_when_no_changes(tmp_path: Path) -> None:
    """git_commit does nothing when working tree is clean."""
    _init_git_repo(tmp_path)
    writer = FileWriter(tmp_path, dry_run=False)
    writer.finalize()

    writer.git_commit(dry_run=False)  # Should not raise

    log = subprocess.check_output(
        ["git", "log", "--oneline"], cwd=tmp_path
    ).decode()
    assert len(log.strip().splitlines()) == 1  # Only init commit
