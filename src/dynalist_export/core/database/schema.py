"""SQLite schema creation and migration for the Dynalist archive."""

import sqlite3

SCHEMA_VERSION = 1

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS documents (
    file_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    version INTEGER,
    node_count INTEGER DEFAULT 0,
    imported_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    parent_id TEXT,
    content TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL,
    modified INTEGER NOT NULL,
    sort_order INTEGER NOT NULL,
    depth INTEGER NOT NULL,
    path TEXT NOT NULL,
    checked INTEGER,
    color INTEGER,
    child_count INTEGER DEFAULT 0,
    PRIMARY KEY (document_id, id),
    FOREIGN KEY (document_id) REFERENCES documents(file_id)
);

CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(document_id, parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_modified ON nodes(modified DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path);

CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    content, note,
    content='nodes',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    document_id TEXT PRIMARY KEY,
    version INTEGER,
    last_import_at INTEGER,
    source_hash TEXT
);
"""

_FTS_TRIGGERS_SQL = """\
CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, content, note)
    VALUES (new.rowid, new.content, new.note);
END;

CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, content, note)
    VALUES ('delete', old.rowid, old.content, old.note);
END;

CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
    INSERT INTO nodes_fts(nodes_fts, rowid, content, note)
    VALUES ('delete', old.rowid, old.content, old.note);
    INSERT INTO nodes_fts(rowid, content, note)
    VALUES (new.rowid, new.content, new.note);
END;
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables, indexes, and triggers."""
    conn.executescript(_SCHEMA_SQL)
    conn.executescript(_FTS_TRIGGERS_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int | None:
    """Return the current schema version, or None if metadata table doesn't exist."""
    try:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return int(row[0]) if row else None


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Create or migrate the database schema to the latest version."""
    version = get_schema_version(conn)
    if version is None:
        create_schema(conn)
