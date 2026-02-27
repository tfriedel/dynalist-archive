"""Tests for database schema."""

import sqlite3

from dynalist_export.core.database.schema import create_schema, get_schema_version, migrate_schema


def test_create_schema_creates_documents_table() -> None:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
    assert cursor.fetchone() is not None


def test_create_schema_creates_nodes_table_and_fts() -> None:
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "nodes" in tables
    assert "nodes_fts" in tables


def test_migrate_schema_on_empty_db_creates_schema_and_sets_version() -> None:
    conn = sqlite3.connect(":memory:")
    assert get_schema_version(conn) is None
    migrate_schema(conn)
    assert get_schema_version(conn) == 1
