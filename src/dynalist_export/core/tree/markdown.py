"""Render node subtrees as markdown."""

import io
import sqlite3


def render_subtree_as_markdown(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    node_id: str,
    max_depth: int | None = None,
    include_notes: bool = True,
) -> str:
    """Render a node and its descendants as indented markdown.

    Args:
        conn: Database connection.
        document_id: The document containing the node.
        node_id: The root node to start rendering from.
        max_depth: Max levels below the start node to include (None = unlimited).
        include_notes: Whether to include node notes.

    Returns:
        Markdown string with bullet-list hierarchy.
    """
    # Get the start node to determine its depth
    start_row = conn.execute(
        "SELECT depth, path FROM nodes WHERE document_id = ? AND id = ?",
        (document_id, node_id),
    ).fetchone()
    if start_row is None:
        return ""

    start_depth = start_row[0]
    start_path = start_row[1]

    # Fetch all nodes in the subtree
    query = (
        "SELECT id, content, note, depth, checked, child_count "
        "FROM nodes WHERE document_id = ? AND (path = ? OR path LIKE ? || '/%') "
    )
    params: list[str | int] = [document_id, start_path, start_path]

    if max_depth is not None:
        query += "AND depth <= ? "
        params.append(start_depth + max_depth)

    query += "ORDER BY path, sort_order"

    rows = conn.execute(query, params).fetchall()

    max_absolute_depth = start_depth + max_depth if max_depth is not None else None

    out = io.StringIO()
    for row in rows:
        node_id_val, content, note, depth, checked, child_count = row
        relative_depth = depth - start_depth
        indent = "    " * relative_depth

        # Format checkbox
        prefix = "- "
        if checked is not None:
            prefix = "- [x] " if checked else "- [ ] "

        # Write content lines
        lines = content.split("\n")
        out.write(f"{indent}{prefix}{lines[0]}\n")
        for line in lines[1:]:
            out.write(f"{indent}  {line}\n")

        # Write notes
        if include_notes and note:
            for note_line in note.split("\n"):
                out.write(f"{indent}  > {note_line}\n")

        # Truncation indicator when children are cut off by max_depth
        if max_absolute_depth is not None and depth == max_absolute_depth and child_count > 0:
            child_indent = "    " * (relative_depth + 1)
            noun = "child" if child_count == 1 else "children"
            out.write(f"{child_indent}- ... ({child_count} more {noun}, id={node_id_val})\n")

    return out.getvalue()
