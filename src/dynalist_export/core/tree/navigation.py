"""Tree navigation: breadcrumbs, siblings, subtree retrieval."""

import sqlite3

from dynalist_export.models.node import Breadcrumb, Node


def get_breadcrumbs(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    path: str,
) -> tuple[Breadcrumb, ...]:
    """Get ancestor breadcrumbs for a node given its path.

    Returns breadcrumbs in order from root to immediate parent (excludes the node itself).
    """
    parts = path.strip("/").split("/")
    # Exclude the node itself (last part)
    ancestor_ids = parts[:-1]
    if not ancestor_ids:
        return ()

    placeholders = ",".join("?" * len(ancestor_ids))
    rows = conn.execute(
        f"SELECT id, content, depth FROM nodes "
        f"WHERE document_id = ? AND id IN ({placeholders}) "
        f"ORDER BY depth",
        [document_id, *ancestor_ids],
    ).fetchall()

    return tuple(Breadcrumb(node_id=r[0], content=r[1], depth=r[2]) for r in rows)


def get_siblings(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    parent_id: str | None,
    sort_order: int,
    count: int = 3,
) -> tuple[tuple[Node, ...], tuple[Node, ...]]:
    """Get siblings before and after a node.

    Returns (siblings_before, siblings_after) tuples.
    """
    if parent_id is None:
        return (), ()

    rows_before = conn.execute(
        "SELECT id, document_id, parent_id, content, note, created, modified, "
        "sort_order, depth, path, checked, color, child_count "
        "FROM nodes WHERE document_id = ? AND parent_id = ? AND sort_order < ? "
        "ORDER BY sort_order DESC LIMIT ?",
        (document_id, parent_id, sort_order, count),
    ).fetchall()

    rows_after = conn.execute(
        "SELECT id, document_id, parent_id, content, note, created, modified, "
        "sort_order, depth, path, checked, color, child_count "
        "FROM nodes WHERE document_id = ? AND parent_id = ? AND sort_order > ? "
        "ORDER BY sort_order LIMIT ?",
        (document_id, parent_id, sort_order, count),
    ).fetchall()

    def to_node(row: tuple) -> Node:
        return Node(
            id=row[0], document_id=row[1], parent_id=row[2], content=row[3],
            note=row[4], created=row[5], modified=row[6], sort_order=row[7],
            depth=row[8], path=row[9], checked=row[10], color=row[11],
            child_count=row[12],
        )

    return (
        tuple(to_node(r) for r in reversed(rows_before)),
        tuple(to_node(r) for r in rows_after),
    )


def get_children(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    parent_id: str,
    limit: int = 50,
) -> tuple[Node, ...]:
    """Get direct children of a node, ordered by sort_order."""
    rows = conn.execute(
        "SELECT id, document_id, parent_id, content, note, created, modified, "
        "sort_order, depth, path, checked, color, child_count "
        "FROM nodes WHERE document_id = ? AND parent_id = ? "
        "ORDER BY sort_order LIMIT ?",
        (document_id, parent_id, limit),
    ).fetchall()

    return tuple(
        Node(
            id=r[0], document_id=r[1], parent_id=r[2], content=r[3],
            note=r[4], created=r[5], modified=r[6], sort_order=r[7],
            depth=r[8], path=r[9], checked=r[10], color=r[11],
            child_count=r[12],
        )
        for r in rows
    )
