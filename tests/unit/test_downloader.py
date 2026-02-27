"""Tests for Downloader — sync logic and text conversion."""

from typing import Any

import pytest

from dynalist_export.downloader import (
    Downloader,
    _dict_to_readable,
    _iterate_contents,
    _record_to_text,
)
from tests.unit.fakes import FakeApi, FakeWriter


def _make_doc(
    title: str = "Test Doc",
    file_id: str = "doc1",
    version: int = 1,
    nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a minimal Dynalist document for testing."""
    if nodes is None:
        nodes = [
            {
                "id": "root",
                "content": title,
                "note": "",
                "created": 1000,
                "modified": 2000,
                "children": ["n1"],
            },
            {
                "id": "n1",
                "content": "First item",
                "note": "a note",
                "created": 1001,
                "modified": 2001,
            },
        ]
    return {"title": title, "file_id": file_id, "version": version, "nodes": nodes}


def test_iterate_contents_yields_nodes_in_preorder() -> None:
    """Nodes are yielded in pre-order (parent before children)."""
    contents = {
        "nodes": [
            {"id": "root", "content": "top", "children": ["a", "b"]},
            {"id": "a", "content": "child-a", "children": ["a1"]},
            {"id": "a1", "content": "grandchild"},
            {"id": "b", "content": "child-b"},
        ]
    }

    ids = [node["id"] for node in _iterate_contents(contents)]

    assert ids == ["root", "a", "a1", "b"]


def test_iterate_contents_tracks_parent_chain() -> None:
    """Each node includes the list of ancestor IDs."""
    contents = {
        "nodes": [
            {"id": "root", "content": "top", "children": ["a"]},
            {"id": "a", "content": "child", "children": ["a1"]},
            {"id": "a1", "content": "grandchild"},
        ]
    }

    nodes = list(_iterate_contents(contents))

    assert nodes[0]["_parents"] == []
    assert nodes[1]["_parents"] == ["root"]
    assert nodes[2]["_parents"] == ["root", "a"]


def test_iterate_contents_raises_on_orphaned_nodes() -> None:
    """Nodes not reachable from root cause a ValueError."""
    contents = {
        "nodes": [
            {"id": "root", "content": "top"},
            {"id": "orphan", "content": "lost"},
        ]
    }

    with pytest.raises(ValueError, match="orphaned nodes"):
        list(_iterate_contents(contents))


def test_dict_to_readable_formats_bool_as_bare_key() -> None:
    """True values render as just the key name."""
    result = _dict_to_readable({"checked": True})

    assert result == "checked"


def test_dict_to_readable_formats_strings_with_single_quotes_unquoted() -> None:
    """Strings whose repr uses double quotes are shown bare (contains single quote)."""
    result = _dict_to_readable({"note": "it's"})

    assert result == "note=it's"


def test_dict_to_readable_formats_comma_values_with_repr() -> None:
    """Values with commas use repr to avoid ambiguity."""
    result = _dict_to_readable({"data": "a,b"})

    assert result == "data='a,b'"


def test_record_to_text_converts_document_to_formatted_text() -> None:
    """Document is rendered with title, indentation, and marker prefixes."""
    doc = _make_doc()

    text = _record_to_text(doc)

    assert text.startswith("### FILE: Test Doc\n")
    assert "* First item\n" in text
    assert "_ a note\n" in text


def test_record_to_text_uses_dot_for_continuation_lines() -> None:
    """Multiline content uses * for first line, . for subsequent."""
    doc = _make_doc(
        nodes=[
            {
                "id": "root",
                "content": "line1\nline2",
                "note": "",
                "created": 1000,
                "modified": 2000,
            },
        ]
    )

    text = _record_to_text(doc)

    assert "* line1\n" in text
    assert ". line2\n" in text


# --- Sync method tests using FakeApi + FakeWriter ---


def _make_file_list(
    root_id: str = "root1",
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a file/list API response."""
    if files is None:
        files = [
            {"id": root_id, "title": "Root", "type": "folder", "children": ["doc1"]},
            {"id": "doc1", "title": "My Notes", "type": "document"},
        ]
    return {"root_file_id": root_id, "files": files, "_code": "Ok"}


def test_sync_file_list_calls_api_and_writes_raw_list() -> None:
    """_sync_file_list fetches file list and saves it via writer."""
    fake_api = FakeApi()
    fake_writer = FakeWriter()
    file_list = _make_file_list()
    fake_api.add_response("file/list", file_list)
    downloader = Downloader(fake_writer)

    result = downloader._sync_file_list(fake_api)

    assert result == file_list
    assert "_raw_list.json" in fake_writer.files
    assert fake_api.calls == [("file/list", {})]


def test_sync_file_list_raises_on_unexpected_keys() -> None:
    """_sync_file_list validates the response schema."""
    fake_api = FakeApi()
    fake_writer = FakeWriter()
    bad_response = {"root_file_id": "r", "files": [], "_code": "Ok", "extra": 1}
    fake_api.add_response("file/list", bad_response)
    downloader = Downloader(fake_writer)

    with pytest.raises(ValueError, match="bad files keys"):
        downloader._sync_file_list(fake_api)


def test_assign_obj_filenames_walks_hierarchy() -> None:
    """_assign_obj_filenames assigns paths to each file in the hierarchy."""
    fake_writer = FakeWriter()
    raw_list = _make_file_list()
    downloader = Downloader(fake_writer)

    result = downloader._assign_obj_filenames(raw_list)

    paths = [f["_path"] for f in result]
    assert "_root_file" in paths[0]
    assert any("My Notes" in p for p in paths)


def test_get_contents_skips_unchanged_documents() -> None:
    """_get_contents reuses cached content when version matches."""
    fake_api = FakeApi()
    fake_writer = FakeWriter()
    doc = _make_doc(version=5)
    # Pre-populate cache with matching version
    fake_writer.make_data_file("notes.c.json", data=doc)
    downloader = Downloader(fake_writer)

    file_index = [{"type": "document", "_path": "notes", "id": "doc1"}]
    versions_info = {"doc1": 5}

    result = downloader._get_contents(fake_api, file_index, versions_info)

    assert "notes" in result
    assert fake_api.calls == []  # No API call made


def test_get_contents_fetches_changed_documents() -> None:
    """_get_contents fetches from API when version differs."""
    fake_api = FakeApi()
    fake_writer = FakeWriter()
    new_doc = {**_make_doc(version=6), "_code": "Ok"}
    fake_api.add_response("doc/read", new_doc)
    # Pre-populate with old version
    fake_writer.make_data_file("notes.c.json", data=_make_doc(version=5))
    downloader = Downloader(fake_writer)

    file_index = [{"type": "document", "_path": "notes", "id": "doc1"}]
    versions_info = {"doc1": 6}

    result = downloader._get_contents(fake_api, file_index, versions_info)

    assert "notes" in result
    assert len(fake_api.calls) == 1


def test_sync_all_orchestrates_full_pipeline() -> None:
    """sync_all runs file list, versions, filenames, contents, and text generation."""
    fake_api = FakeApi()
    fake_writer = FakeWriter()

    fake_api.add_response("file/list", _make_file_list())
    fake_api.add_response(
        "doc/check_for_updates",
        {
            "versions": {"doc1": 1},
            "_code": "Ok",
        },
    )
    doc_response = {**_make_doc(), "_code": "Ok"}
    fake_api.add_response("doc/read", doc_response)

    downloader = Downloader(fake_writer)
    downloader.sync_all(fake_api)

    assert downloader.file_index is not None
    assert downloader.doc_contents is not None
    # Should have written .c.json and .txt files
    assert any(f.endswith(".c.json") for f in fake_writer.files)
    assert any(f.endswith(".txt") for f in fake_writer.files)
