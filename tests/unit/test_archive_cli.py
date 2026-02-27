"""Tests for the archive CLI."""

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dynalist_export.archive_cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_auto_update() -> Iterator[None]:
    """Disable auto-update in CLI tests to prevent real API calls."""
    with patch("dynalist_export.archive_cli.maybe_auto_update"):
        yield


MINIMAL_FILE_LIST = {
    "_code": "Ok",
    "root_file_id": "folder1",
    "files": [
        {"id": "folder1", "title": "Root", "type": "folder", "children": ["doc1"]},
        {"id": "doc1", "title": "Test Doc", "type": "document"},
    ],
}

MINIMAL_FILENAMES = [
    {"_path": "_root_file", "id": "folder1"},
    {"_path": "test-doc", "id": "doc1"},
]

MINIMAL_DOC = {
    "file_id": "doc1",
    "title": "Test Doc",
    "version": 1,
    "nodes": [
        {
            "id": "root",
            "content": "Root",
            "note": "",
            "created": 1000,
            "modified": 2000,
            "children": ["a"],
        },
        {"id": "a", "content": "Hello", "note": "", "created": 1001, "modified": 2001},
    ],
}


def test_import_command_creates_database(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    data = tmp_path / "data"

    (source / "_raw_list.json").write_text(json.dumps(MINIMAL_FILE_LIST))
    (source / "_raw_filenames.json").write_text(json.dumps(MINIMAL_FILENAMES))
    (source / "test-doc.c.json").write_text(json.dumps(MINIMAL_DOC))

    result = runner.invoke(app, ["import", "--source-dir", str(source), "--data-dir", str(data)])
    assert result.exit_code == 0, result.output
    assert (data / "archive.db").exists()


def _setup_and_import(tmp_path: Path) -> Path:
    """Helper: create source, import, return data dir."""
    source = tmp_path / "source"
    source.mkdir()
    data = tmp_path / "data"

    (source / "_raw_list.json").write_text(json.dumps(MINIMAL_FILE_LIST))
    (source / "_raw_filenames.json").write_text(json.dumps(MINIMAL_FILENAMES))
    (source / "test-doc.c.json").write_text(json.dumps(MINIMAL_DOC))

    result = runner.invoke(app, ["import", "--source-dir", str(source), "--data-dir", str(data)])
    assert result.exit_code == 0
    return data


def test_search_command_returns_results(tmp_path: Path) -> None:
    data = _setup_and_import(tmp_path)
    result = runner.invoke(app, ["search", "Hello", "--data-dir", str(data)])
    assert result.exit_code == 0, result.output
    assert "Hello" in result.output


def test_documents_command_lists_documents(tmp_path: Path) -> None:
    data = _setup_and_import(tmp_path)
    result = runner.invoke(app, ["documents", "--data-dir", str(data)])
    assert result.exit_code == 0, result.output
    assert "Test Doc" in result.output


def test_read_json_outputs_valid_json(tmp_path: Path) -> None:
    data = _setup_and_import(tmp_path)
    result = runner.invoke(
        app, ["read", "root", "--document", "doc1", "--json", "--data-dir", str(data)]
    )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["node"]["id"] == "root"
    assert "children" in parsed


def test_documents_json_outputs_valid_json(tmp_path: Path) -> None:
    data = _setup_and_import(tmp_path)
    result = runner.invoke(app, ["documents", "--json", "--data-dir", str(data)])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["count"] == 1
    assert parsed["documents"][0]["title"] == "Test Doc"


def test_recent_json_outputs_valid_json(tmp_path: Path) -> None:
    data = _setup_and_import(tmp_path)
    result = runner.invoke(app, ["recent", "--json", "--data-dir", str(data)])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["count"] >= 1
    assert "node_id" in parsed["results"][0]
    assert "modified" in parsed["results"][0]


def test_edit_command_returns_json(tmp_path: Path) -> None:
    data = _setup_and_import(tmp_path)
    with patch(
        "dynalist_export.mcp.server.dynalist_edit_node",
        return_value={"success": True, "node_id": "a"},
    ):
        result = runner.invoke(
            app,
            [
                "edit", "a", "--document", "doc1",
                "--content", "Updated", "--json", "--data-dir", str(data),
            ],
        )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["success"] is True
    assert parsed["node_id"] == "a"


def test_add_command_returns_json(tmp_path: Path) -> None:
    data = _setup_and_import(tmp_path)
    with patch(
        "dynalist_export.mcp.server.dynalist_add_node",
        return_value={"success": True, "node_id": "new123"},
    ):
        result = runner.invoke(
            app,
            [
                "add", "root", "--document", "doc1",
                "--content", "New item", "--json", "--data-dir", str(data),
            ],
        )
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["success"] is True
    assert parsed["node_id"] == "new123"


def test_serve_command_shows_help() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0, result.output
    assert "MCP" in result.output or "server" in result.output.lower()
