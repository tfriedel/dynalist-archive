"""Orchestrate importing Dynalist .c.json files into SQLite."""

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from dynalist_export.core.importer.json_reader import parse_document_data
from dynalist_export.models.node import Node


@dataclass(frozen=True)
class ImportStats:
    """Summary of an import operation."""

    documents_imported: int
    documents_skipped: int
    nodes_imported: int


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _should_reimport(
    conn: sqlite3.Connection, document_id: str, source_hash: str
) -> bool:
    row = conn.execute(
        "SELECT source_hash FROM sync_state WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    if row is None:
        return True
    return row[0] != source_hash


def insert_nodes(conn: sqlite3.Connection, nodes: list[Node]) -> None:
    conn.executemany(
        """INSERT OR REPLACE INTO nodes
           (id, document_id, parent_id, content, note, created, modified,
            sort_order, depth, path, checked, color, child_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                n.id, n.document_id, n.parent_id, n.content, n.note,
                n.created, n.modified, n.sort_order, n.depth, n.path,
                n.checked, n.color, n.child_count,
            )
            for n in nodes
        ],
    )


def import_source_dir(
    conn: sqlite3.Connection,
    source_dir: Path,
    *,
    force: bool = False,
) -> ImportStats:
    """Import all .c.json files from source_dir into the database.

    Args:
        conn: SQLite connection (schema must already exist).
        source_dir: Directory containing .c.json and _raw_filenames.json.
        force: Re-import even if source file hasn't changed.

    Returns:
        ImportStats with counts of imported/skipped documents.
    """
    filenames_path = source_dir / "_raw_filenames.json"
    if not filenames_path.exists():
        msg = f"Missing _raw_filenames.json in {source_dir}"
        raise FileNotFoundError(msg)

    filenames_data: list[dict[str, str]] = json.loads(filenames_path.read_text())
    # Build mapping: file_id -> filename (path from _raw_filenames.json)
    id_to_filename = {entry["id"]: entry["_path"] for entry in filenames_data}

    docs_imported = 0
    docs_skipped = 0
    total_nodes = 0

    for json_path in sorted(source_dir.glob("*.c.json")):
        data = json.loads(json_path.read_text())
        file_id = data.get("file_id")
        if file_id is None:
            logger.warning("Skipping {}: no file_id", json_path.name)
            continue

        filename = id_to_filename.get(file_id, json_path.stem.removesuffix(".c"))
        source_hash = _file_hash(json_path)

        if not force and not _should_reimport(conn, file_id, source_hash):
            docs_skipped += 1
            continue

        doc, nodes = parse_document_data(data, filename=filename)

        try:
            # Clear old data for this document
            conn.execute("DELETE FROM nodes WHERE document_id = ?", (file_id,))
            conn.execute("DELETE FROM documents WHERE file_id = ?", (file_id,))

            # Insert document
            now_ms = int(time.time() * 1000)
            conn.execute(
                """INSERT INTO documents
                   (file_id, title, filename, version, node_count, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (doc.file_id, doc.title, doc.filename, doc.version, doc.node_count, now_ms),
            )

            # Insert nodes
            insert_nodes(conn, nodes)

            # Update sync state
            conn.execute(
                """INSERT OR REPLACE INTO sync_state
                   (document_id, version, last_import_at, source_hash)
                   VALUES (?, ?, ?, ?)""",
                (file_id, doc.version, now_ms, source_hash),
            )

            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Failed to import {}", json_path.name)
            continue

        docs_imported += 1
        total_nodes += len(nodes)
        logger.debug("Imported {} ({} nodes)", doc.title, len(nodes))

    logger.info(
        "Import complete: {} imported, {} skipped, {} total nodes",
        docs_imported, docs_skipped, total_nodes,
    )
    return ImportStats(
        documents_imported=docs_imported,
        documents_skipped=docs_skipped,
        nodes_imported=total_nodes,
    )
