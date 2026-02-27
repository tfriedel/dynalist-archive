"""Write operations against the Dynalist API with local DB re-sync."""

import sqlite3
from typing import Any

from loguru import logger

from dynalist_archive.api import DynalistApi


def edit_node(
    conn: sqlite3.Connection,
    api: DynalistApi,
    *,
    node_id: str,
    document_id: str,
    content: str | None = None,
    note: str | None = None,
    checked: bool | None = None,
) -> dict[str, Any]:
    """Edit a node via the Dynalist API.

    Args:
        conn: Database connection (for re-import after write).
        api: Dynalist API client.
        node_id: ID of the node to edit.
        document_id: ID of the document containing the node.
        content: New content text.
        note: New note text.
        checked: New checked state.
    """
    change: dict[str, Any] = {"action": "edit", "node_id": node_id}
    if content is not None:
        change["content"] = content
    if note is not None:
        change["note"] = note
    if checked is not None:
        change["checked"] = checked

    if len(change) == 2:  # only action + node_id
        return {"success": False, "error": "No fields to update."}

    try:
        result = api.call("doc/edit", {"file_id": document_id, "changes": [change]})
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    if result.get("_code") != "Ok":
        return {"success": False, "error": f"API reported edit failed: {result}"}

    _reimport_document(conn, api, document_id)
    return {"success": True, "node_id": node_id}


def add_node(
    conn: sqlite3.Connection,
    api: DynalistApi,
    *,
    parent_id: str,
    document_id: str,
    content: str,
    note: str | None = None,
    index: int = -1,
    checked: bool | None = None,
) -> dict[str, Any]:
    """Add a new node via the Dynalist API.

    Args:
        conn: Database connection (for re-import after write).
        api: Dynalist API client.
        parent_id: ID of the parent node.
        document_id: ID of the document.
        content: Content text for the new node.
        note: Optional note text.
        index: Position among siblings (-1 = last).
        checked: Optional checked state.
    """
    change: dict[str, Any] = {
        "action": "insert",
        "parent_id": parent_id,
        "content": content,
        "index": index,
    }
    if note is not None:
        change["note"] = note
    if checked is not None:
        change["checked"] = checked

    try:
        result = api.call("doc/edit", {"file_id": document_id, "changes": [change]})
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    if result.get("_code") != "Ok":
        return {"success": False, "error": f"API reported insert failed: {result}"}

    new_ids = result.get("new_node_ids", [])
    new_id = new_ids[0] if new_ids else None

    _reimport_document(conn, api, document_id)
    output: dict[str, Any] = {"success": True}
    if new_id:
        output["node_id"] = new_id
    return output


def _reimport_document(conn: sqlite3.Connection, api: DynalistApi, document_id: str) -> None:
    """Re-import a single document from the API after a write."""
    import time

    from dynalist_archive.core.importer.json_reader import parse_document_data
    from dynalist_archive.core.importer.loader import insert_nodes

    try:
        doc_data = api.call("doc/read", {"file_id": document_id})
        row = conn.execute(
            "SELECT title, filename FROM documents WHERE file_id = ?",
            (document_id,),
        ).fetchone()
        if not row:
            logger.warning("Document {} not found in DB for re-import", document_id)
            return

        doc_json = {
            "file_id": document_id,
            "title": doc_data.get("title", row[0]),
            "version": doc_data.get("version", 0),
            "nodes": doc_data.get("nodes", []),
        }
        doc, nodes = parse_document_data(doc_json, filename=row[1])

        # Clear and re-insert
        conn.execute("DELETE FROM nodes WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM documents WHERE file_id = ?", (document_id,))

        now_ms = int(time.time() * 1000)
        conn.execute(
            """INSERT INTO documents (file_id, title, filename, version, node_count, imported_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (doc.file_id, doc.title, doc.filename, doc.version, doc.node_count, now_ms),
        )
        insert_nodes(conn, nodes)

        # Update sync_state so the next import_source_dir doesn't overwrite
        conn.execute(
            """INSERT OR REPLACE INTO sync_state
               (document_id, version, last_import_at, source_hash)
               VALUES (?, ?, ?, ?)""",
            (document_id, doc.version, now_ms, "api-write"),
        )

        conn.commit()
        logger.info("Re-imported document {} after write", document_id)
    except Exception:
        conn.rollback()
        logger.exception("Failed to re-import document {} after write", document_id)
