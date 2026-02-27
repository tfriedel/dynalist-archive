"""Tests for the import loader that reads .c.json files into SQLite."""

import json
import sqlite3
from pathlib import Path

from dynalist_archive.core.database.schema import create_schema
from dynalist_archive.core.importer.loader import import_source_dir

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
        {"id": "a", "content": "Hello world", "note": "", "created": 1001, "modified": 2001},
    ],
}


def test_import_source_dir_loads_document_and_nodes(tmp_path: Path) -> None:
    """Import a minimal source dir and verify documents and nodes are in the DB."""
    # Set up source directory
    (tmp_path / "_raw_list.json").write_text(json.dumps(MINIMAL_FILE_LIST))
    (tmp_path / "_raw_filenames.json").write_text(json.dumps(MINIMAL_FILENAMES))
    (tmp_path / "test-doc.c.json").write_text(json.dumps(MINIMAL_DOC))

    conn = sqlite3.connect(":memory:")
    create_schema(conn)

    stats = import_source_dir(conn, tmp_path)

    assert stats.documents_imported == 1
    assert stats.nodes_imported == 2

    # Verify document row
    row = conn.execute("SELECT file_id, title, filename FROM documents").fetchone()
    assert row == ("doc1", "Test Doc", "test-doc")

    # Verify node rows
    nodes = conn.execute("SELECT id, content FROM nodes ORDER BY depth, sort_order").fetchall()
    assert len(nodes) == 2
    assert nodes[0] == ("root", "Root")
    assert nodes[1] == ("a", "Hello world")


def test_import_populates_fts_index(tmp_path: Path) -> None:
    """FTS triggers should make imported nodes searchable."""
    (tmp_path / "_raw_list.json").write_text(json.dumps(MINIMAL_FILE_LIST))
    (tmp_path / "_raw_filenames.json").write_text(json.dumps(MINIMAL_FILENAMES))
    (tmp_path / "test-doc.c.json").write_text(json.dumps(MINIMAL_DOC))

    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    import_source_dir(conn, tmp_path)

    # FTS5 search should find the node
    rows = conn.execute("SELECT content FROM nodes_fts WHERE nodes_fts MATCH 'hello'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "Hello world"


def test_import_skips_unchanged_files_on_second_run(tmp_path: Path) -> None:
    """Second import with same files should skip all documents."""
    (tmp_path / "_raw_list.json").write_text(json.dumps(MINIMAL_FILE_LIST))
    (tmp_path / "_raw_filenames.json").write_text(json.dumps(MINIMAL_FILENAMES))
    (tmp_path / "test-doc.c.json").write_text(json.dumps(MINIMAL_DOC))

    conn = sqlite3.connect(":memory:")
    create_schema(conn)

    first = import_source_dir(conn, tmp_path)
    assert first.documents_imported == 1

    second = import_source_dir(conn, tmp_path)
    assert second.documents_imported == 0
    assert second.documents_skipped == 1
