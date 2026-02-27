"""FTS5 search engine for Dynalist archive."""

import re
import sqlite3

from dynalist_export.models.node import Node, SearchResult


def _sanitize_fts_token(token: str) -> str:
    """Remove FTS5 special characters (whitelist approach)."""
    return re.sub(r"[^\w]", "", token, flags=re.UNICODE)


def _prepare_fts_query(query: str) -> str:
    """Convert user query to FTS5 query with prefix matching.

    - 3+ char words get * suffix for prefix matching
    - Quoted phrases are preserved as-is
    - FTS5 operators AND, OR, NOT are preserved
    """
    if not query.strip():
        return ""

    tokens: list[str] = []
    i = 0
    while i < len(query):
        if query[i] == '"':
            end = query.find('"', i + 1)
            if end == -1:
                end = len(query)
            tokens.append(query[i : end + 1])
            i = end + 1
        elif query[i].isspace():
            i += 1
        else:
            end = i
            while end < len(query) and not query[end].isspace() and query[end] != '"':
                end += 1
            word = query[i:end]
            i = end

            if word.upper() in ("AND", "OR", "NOT"):
                tokens.append(word.upper())
                continue

            sanitized = _sanitize_fts_token(word)
            if not sanitized:
                continue
            if len(sanitized) >= 3:
                tokens.append(f"{sanitized}*")
            else:
                tokens.append(sanitized)

    return " ".join(tokens)


def _row_to_node(row: sqlite3.Row | tuple) -> Node:
    return Node(
        id=row[0],
        document_id=row[1],
        parent_id=row[2],
        content=row[3],
        note=row[4],
        created=row[5],
        modified=row[6],
        sort_order=row[7],
        depth=row[8],
        path=row[9],
        checked=row[10],
        color=row[11],
        child_count=row[12],
    )


def search_nodes(
    conn: sqlite3.Connection,
    *,
    query: str = "",
    document_id: str | None = None,
    below_node_path: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SearchResult], int]:
    """Search nodes using FTS5.

    Args:
        conn: Database connection.
        query: Search query text.
        document_id: Restrict to a specific document.
        below_node_path: Restrict to subtree under this path.
        limit: Max results to return.
        offset: Pagination offset.

    Returns:
        Tuple of (results, total_count).
    """
    fts_query = _prepare_fts_query(query)
    if not fts_query:
        return [], 0

    # Build the query joining FTS with nodes
    where_clauses = ["nodes_fts MATCH ?"]
    params: list[str | int] = [fts_query]

    if document_id:
        where_clauses.append("n.document_id = ?")
        params.append(document_id)

    if below_node_path:
        where_clauses.append("(n.path = ? OR n.path LIKE ? || '/%')")
        params.extend([below_node_path, below_node_path])

    where_sql = " AND ".join(where_clauses)

    count_sql = f"""
        SELECT COUNT(*)
        FROM nodes_fts
        JOIN nodes n ON n.rowid = nodes_fts.rowid
        WHERE {where_sql}
    """
    total = conn.execute(count_sql, params).fetchone()[0]

    select_sql = f"""
        SELECT n.id, n.document_id, n.parent_id, n.content, n.note,
               n.created, n.modified, n.sort_order, n.depth, n.path,
               n.checked, n.color, n.child_count,
               d.title as doc_title,
               snippet(nodes_fts, 0, '**', '**', '...', 32) as snippet
        FROM nodes_fts
        JOIN nodes n ON n.rowid = nodes_fts.rowid
        JOIN documents d ON d.file_id = n.document_id
        WHERE {where_sql}
        ORDER BY rank
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    rows = conn.execute(select_sql, params).fetchall()
    results = [
        SearchResult(
            node=_row_to_node(row),
            document_title=row[13],
            snippet=row[14],
        )
        for row in rows
    ]
    return results, total
