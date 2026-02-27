"""Shared test fixtures."""

import json
import sqlite3
from pathlib import Path

import pytest

from dynalist_export.core.database.schema import create_schema
from dynalist_export.core.importer.loader import import_source_dir

MULTI_DOC_SOURCE = {
    "_raw_filenames.json": [
        {"_path": "_root_file", "id": "folder1"},
        {"_path": "notes", "id": "doc1"},
        {"_path": "recipes", "id": "doc2"},
    ],
    "notes.c.json": {
        "file_id": "doc1",
        "title": "Notes",
        "version": 1,
        "nodes": [
            {
                "id": "root",
                "content": "Notes",
                "note": "",
                "created": 1000,
                "modified": 2000,
                "children": ["n1", "n2"],
            },
            {
                "id": "n1",
                "content": "Python is great for scripting",
                "note": "use type hints",
                "created": 1001,
                "modified": 2001,
                "children": ["n1a"],
            },
            {
                "id": "n1a",
                "content": "FastAPI for web services",
                "note": "",
                "created": 1002,
                "modified": 2002,
            },
            {
                "id": "n2",
                "content": "Rust is fast",
                "note": "memory safety",
                "created": 1003,
                "modified": 2003,
            },
        ],
    },
    "recipes.c.json": {
        "file_id": "doc2",
        "title": "Recipes",
        "version": 1,
        "nodes": [
            {
                "id": "root",
                "content": "Recipes",
                "note": "",
                "created": 2000,
                "modified": 3000,
                "children": ["r1"],
            },
            {
                "id": "r1",
                "content": "Python cake recipe",
                "note": "not a real snake",
                "created": 2001,
                "modified": 3001,
            },
        ],
    },
}


@pytest.fixture
def populated_db(tmp_path: Path) -> sqlite3.Connection:
    """Return an in-memory DB with two documents imported."""
    source = tmp_path / "source"
    source.mkdir()
    for name, data in MULTI_DOC_SOURCE.items():
        (source / name).write_text(json.dumps(data))

    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    import_source_dir(conn, source)
    return conn
