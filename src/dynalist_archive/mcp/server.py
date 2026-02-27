"""MCP server exposing Dynalist archive search and navigation tools."""

import asyncio
import os
import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

from dynalist_archive.config import resolve_data_directory
from dynalist_archive.core.auto_update import maybe_auto_update
from dynalist_archive.core.database.schema import get_metadata, migrate_schema, set_metadata
from dynalist_archive.core.search.searcher import search_nodes
from dynalist_archive.core.tree.markdown import render_subtree_as_markdown
from dynalist_archive.core.tree.navigation import get_breadcrumbs, get_children, get_siblings

_DEFAULT_SOURCE_DIR = resolve_data_directory()
_DEFAULT_DATA_DIR = Path("~/.local/share/dynalist-archive").expanduser()


def _build_url(document_id: str, node_id: str | None = None) -> str:
    url = f"https://dynalist.io/d/{document_id}"
    if node_id and node_id != "root":
        url += f"#z={node_id}"
    return url


def _resolve_document(conn: sqlite3.Connection, document: str) -> str | None:
    """Resolve a document name/filename/file_id to a file_id."""
    row = conn.execute(
        "SELECT file_id FROM documents WHERE title = ? OR file_id = ? OR filename = ?",
        (document, document, document),
    ).fetchone()
    return row[0] if row else None


def _breadcrumbs_str(conn: sqlite3.Connection, document_id: str, path: str) -> str:
    crumbs = get_breadcrumbs(conn, document_id=document_id, path=path)
    return " > ".join(c.content[:40] for c in crumbs) if crumbs else ""


# --- Core functions (testable without MCP context) ---


def dynalist_search(
    conn: sqlite3.Connection,
    *,
    query: str = "",
    document: str | None = None,
    below_node: str | None = None,
    include_breadcrumbs: bool = True,
    limit: int = 20,
    offset: int = 0,
    response_format: str = "concise",
) -> dict[str, Any]:
    """Search archived Dynalist nodes using full-text search.

    Returns nodes matching the query and/or filters.

    Query syntax: Words are ANDed. Use "quoted phrases" for exact matches.
    Prefix matching is automatic for 3+ char words.

    Args:
        query: Search text.
        document: Filter by document title/filename/file_id.
        below_node: Restrict to subtree below this node ID.
        include_breadcrumbs: Include ancestor chain in results.
        limit: Max results (1-50, default 20).
        offset: Pagination offset.
        response_format: "concise" or "detailed".
    """
    if not query.strip():
        return {"error": "No search query provided.", "results": [], "count": 0, "total": 0}

    limit = max(1, min(limit, 50))

    doc_id: str | None = None
    if document:
        doc_id = _resolve_document(conn, document)
        if not doc_id:
            return {
                "error": f"Document '{document}' not found.",
                "results": [],
                "count": 0,
                "total": 0,
            }

    below_path: str | None = None
    if below_node:
        row = conn.execute(
            "SELECT path FROM nodes WHERE id = ?" + (" AND document_id = ?" if doc_id else ""),
            (below_node, doc_id) if doc_id else (below_node,),
        ).fetchone()
        if row:
            below_path = row[0]
        else:
            return {
                "error": f"Node '{below_node}' not found.",
                "results": [],
                "count": 0,
                "total": 0,
            }

    results, total = search_nodes(
        conn,
        query=query,
        document_id=doc_id,
        below_node_path=below_path,
        limit=limit,
        offset=offset,
    )

    serialized = []
    for r in results:
        entry: dict[str, Any] = {
            "node_id": r.node.id,
            "document": r.document_title,
            "content": r.node.content if response_format == "detailed" else r.node.content[:120],
            "note": r.node.note,
            "snippet": r.snippet,
            "url": _build_url(r.node.document_id, r.node.id),
            "modified": datetime.fromtimestamp(r.node.modified / 1000, tz=UTC).isoformat(),
        }
        if response_format == "detailed":
            entry["path"] = r.node.path
            entry["depth"] = r.node.depth
        if include_breadcrumbs:
            entry["breadcrumbs"] = _breadcrumbs_str(conn, r.node.document_id, r.node.path)
        serialized.append(entry)

    output: dict[str, Any] = {
        "results": serialized,
        "count": len(serialized),
        "total": total,
        "has_more": offset + len(serialized) < total,
    }
    if output["has_more"]:
        output["next_offset"] = offset + limit
    return output


def dynalist_list_documents(conn: sqlite3.Connection) -> dict[str, Any]:
    """List all documents in the archive with metadata."""
    rows = conn.execute(
        "SELECT file_id, title, filename, node_count FROM documents ORDER BY title"
    ).fetchall()
    total_nodes = sum(r[3] for r in rows)
    return {
        "documents": [
            {
                "file_id": r[0],
                "title": r[1],
                "filename": r[2],
                "node_count": r[3],
                "url": _build_url(r[0]),
            }
            for r in rows
        ],
        "count": len(rows),
        "total_nodes": total_nodes,
    }


def dynalist_read_node(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    document: str | None = None,
    max_depth: int | None = None,
    output_format: str = "markdown",
    include_notes: bool = True,
) -> dict[str, Any]:
    """Read a node and its subtree as markdown or structured JSON.

    Args:
        node_id: Node ID to read.
        document: Document title/filename/file_id (needed if ambiguous).
        max_depth: Max depth levels to include (None = unlimited).
        output_format: "markdown" or "json".
        include_notes: Include node notes in output.
    """
    if document:
        doc_id = _resolve_document(conn, document)
        if not doc_id:
            return {"error": f"Document '{document}' not found."}
    else:
        row = conn.execute("SELECT document_id FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not row:
            return {"error": f"Node '{node_id}' not found."}
        doc_id = row[0]

    node_row = conn.execute(
        "SELECT path, content, depth FROM nodes WHERE document_id = ? AND id = ?",
        (doc_id, node_id),
    ).fetchone()
    if not node_row:
        return {"error": f"Node '{node_id}' not found in document."}

    path, content, _depth = node_row
    breadcrumbs = _breadcrumbs_str(conn, doc_id, path)

    if output_format == "markdown":
        md = render_subtree_as_markdown(
            conn,
            document_id=doc_id,
            node_id=node_id,
            max_depth=max_depth,
            include_notes=include_notes,
        )
        estimated_tokens = len(md) // 4
        result: dict[str, Any] = {
            "content": md,
            "node_id": node_id,
            "breadcrumbs": breadcrumbs,
            "url": _build_url(doc_id, node_id),
            "estimated_tokens": estimated_tokens,
        }
        if estimated_tokens > 5000:
            result["warning"] = (
                f"Large result (~{estimated_tokens} tokens). "
                "Consider using max_depth to limit output."
            )
        return result

    # JSON format — recursive tree up to max_depth
    def _build_children(parent_id: str, remaining_depth: int | None) -> list[dict[str, Any]]:
        children = get_children(conn, document_id=doc_id, parent_id=parent_id)
        result_list = []
        for c in children:
            entry: dict[str, Any] = {
                "id": c.id,
                "content": c.content,
                "note": c.note,
                "child_count": c.child_count,
            }
            if remaining_depth is None or remaining_depth > 1:
                next_depth = None if remaining_depth is None else remaining_depth - 1
                entry["children"] = _build_children(c.id, next_depth)
            result_list.append(entry)
        return result_list

    return {
        "node": {"id": node_id, "content": content, "path": path},
        "children": _build_children(node_id, max_depth),
        "breadcrumbs": breadcrumbs,
        "url": _build_url(doc_id, node_id),
    }


def dynalist_get_recent_changes(
    conn: sqlite3.Connection,
    *,
    document: str | None = None,
    since: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_breadcrumbs: bool = True,
) -> dict[str, Any]:
    """Get recently modified nodes.

    Args:
        document: Filter by document title/filename/file_id.
        since: Only show changes after this date (YYYY-MM-DD).
        limit: Max results.
        offset: Pagination offset.
        include_breadcrumbs: Include ancestor chain.
    """
    limit = max(1, min(limit, 100))

    where_parts: list[str] = []
    params: list[str | int] = []

    if document:
        doc_id = _resolve_document(conn, document)
        if not doc_id:
            return {"error": f"Document '{document}' not found.", "results": [], "count": 0}
        where_parts.append("n.document_id = ?")
        params.append(doc_id)

    if since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=UTC)
            where_parts.append("n.modified >= ?")
            params.append(int(since_dt.timestamp() * 1000))
        except ValueError:
            return {"error": f"Invalid date format '{since}'. Expected YYYY-MM-DD."}

    where_sql = "WHERE " + " AND ".join(where_parts) if where_parts else ""

    count_sql = f"SELECT COUNT(*) FROM nodes n {where_sql}"
    total = conn.execute(count_sql, params).fetchone()[0]

    query = (
        f"SELECT n.id, n.document_id, n.content, n.modified, n.created, n.path, d.title "
        f"FROM nodes n JOIN documents d ON d.file_id = n.document_id "
        f"{where_sql} ORDER BY n.modified DESC LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        entry: dict[str, Any] = {
            "node_id": r[0],
            "document": r[6],
            "content": r[2][:120],
            "modified": datetime.fromtimestamp(r[3] / 1000, tz=UTC).isoformat(),
            "created": datetime.fromtimestamp(r[4] / 1000, tz=UTC).isoformat(),
            "url": _build_url(r[1], r[0]),
        }
        if include_breadcrumbs:
            entry["breadcrumbs"] = _breadcrumbs_str(conn, r[1], r[5])
        results.append(entry)

    output: dict[str, Any] = {
        "results": results,
        "count": len(results),
        "total": total,
        "has_more": offset + len(results) < total,
    }
    if output["has_more"]:
        output["next_offset"] = offset + limit
    return output


def dynalist_get_node_context(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    document: str | None = None,
    sibling_count: int = 3,
    child_limit: int = 20,
) -> dict[str, Any]:
    """Get a node with breadcrumbs, siblings, and children.

    Args:
        node_id: Node ID.
        document: Document title/filename/file_id.
        sibling_count: Number of siblings before/after to include.
        child_limit: Max direct children to show.
    """
    if document:
        doc_id = _resolve_document(conn, document)
        if not doc_id:
            return {"error": f"Document '{document}' not found."}
    else:
        row = conn.execute("SELECT document_id FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if not row:
            return {"error": f"Node '{node_id}' not found."}
        doc_id = row[0]

    node_row = conn.execute(
        "SELECT id, document_id, parent_id, content, note, created, modified, "
        "sort_order, depth, path, checked, color, child_count "
        "FROM nodes WHERE document_id = ? AND id = ?",
        (doc_id, node_id),
    ).fetchone()
    if not node_row:
        return {"error": f"Node '{node_id}' not found."}

    path = node_row[9]
    parent_id = node_row[2]
    sort_order = node_row[7]

    breadcrumbs = _breadcrumbs_str(conn, doc_id, path)
    children = get_children(conn, document_id=doc_id, parent_id=node_id, limit=child_limit)
    before, after = get_siblings(
        conn,
        document_id=doc_id,
        parent_id=parent_id,
        sort_order=sort_order,
        count=sibling_count,
    )

    return {
        "node": {
            "id": node_row[0],
            "content": node_row[3],
            "note": node_row[4],
            "modified": datetime.fromtimestamp(node_row[6] / 1000, tz=UTC).isoformat(),
            "depth": node_row[8],
            "child_count": node_row[12],
        },
        "breadcrumbs": breadcrumbs,
        "url": _build_url(doc_id, node_id),
        "siblings_before": [{"id": s.id, "content": s.content[:80]} for s in before],
        "siblings_after": [{"id": s.id, "content": s.content[:80]} for s in after],
        "children": [
            {"id": c.id, "content": c.content[:80], "child_count": c.child_count} for c in children
        ],
    }


# --- Write core functions ---


def dynalist_edit_node(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    document: str,
    content: str | None = None,
    note: str | None = None,
    checked: bool | None = None,
) -> dict[str, Any]:
    """Edit a node's content, note, or checked state via the Dynalist API.

    Args:
        node_id: Node ID to edit.
        document: Document title/filename/file_id.
        content: New content text.
        note: New note text.
        checked: New checked state.
    """
    doc_id = _resolve_document(conn, document)
    if not doc_id:
        return {"error": f"Document '{document}' not found."}

    from dynalist_archive.api import DynalistApi
    from dynalist_archive.core.write.client import edit_node

    try:
        api = DynalistApi()
    except RuntimeError as e:
        return {"error": str(e)}
    return edit_node(
        conn,
        api,
        node_id=node_id,
        document_id=doc_id,
        content=content,
        note=note,
        checked=checked,
    )


def dynalist_add_node(
    conn: sqlite3.Connection,
    *,
    parent_id: str,
    document: str,
    content: str,
    note: str | None = None,
    index: int = -1,
    checked: bool | None = None,
) -> dict[str, Any]:
    """Add a new node under a parent via the Dynalist API.

    Args:
        parent_id: Parent node ID.
        document: Document title/filename/file_id.
        content: Content for the new node.
        note: Optional note text.
        index: Position among siblings (-1 = last).
        checked: Optional checked state.
    """
    doc_id = _resolve_document(conn, document)
    if not doc_id:
        return {"error": f"Document '{document}' not found."}

    from dynalist_archive.api import DynalistApi
    from dynalist_archive.core.write.client import add_node

    try:
        api = DynalistApi()
    except RuntimeError as e:
        return {"error": str(e)}
    return add_node(
        conn,
        api,
        parent_id=parent_id,
        document_id=doc_id,
        content=content,
        note=note,
        index=index,
        checked=checked,
    )


# --- MCP Server Setup ---


@dataclass
class ServerContext:
    """Shared resources for the MCP server lifetime."""

    conn: sqlite3.Connection
    source_dir: Path | None
    archive_dir: Path
    auto_update_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _resolve_paths() -> tuple[Path, Path]:
    archive_dir_env = os.environ.get("DYNALIST_ARCHIVE_DIR")
    archive_dir = Path(archive_dir_env) if archive_dir_env else _DEFAULT_DATA_DIR
    source_dir_env = os.environ.get("DYNALIST_SOURCE_DIR")
    source_dir = Path(source_dir_env) if source_dir_env else _DEFAULT_SOURCE_DIR
    return archive_dir, source_dir


def _maybe_auto_import(conn: sqlite3.Connection, source_dir: Path) -> None:
    """Re-import if source files are newer than last import."""
    if not source_dir.exists():
        return

    from dynalist_archive.core.importer.loader import import_source_dir

    stats = import_source_dir(conn, source_dir)
    if stats.documents_imported > 0:
        logger.info("Auto-imported {} documents", stats.documents_imported)


@asynccontextmanager
async def server_lifespan(_server: FastMCP) -> AsyncIterator[ServerContext]:
    """Open database on startup, close on shutdown."""
    archive_dir, source_dir = _resolve_paths()
    db_path = archive_dir / "archive.db"

    if not db_path.exists():
        archive_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        migrate_schema(conn)
    else:
        conn = sqlite3.connect(str(db_path))
        migrate_schema(conn)

    try:
        _maybe_auto_import(conn, source_dir)
        # Set initial cooldown if data exists but no timestamp yet,
        # preventing an unnecessary re-import on the first tool call.
        has_data = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] > 0
        if has_data and get_metadata(conn, "last_update_at") is None:
            set_metadata(conn, "last_update_at", str(int(time.time())))
        yield ServerContext(conn=conn, source_dir=source_dir, archive_dir=archive_dir)
    finally:
        conn.close()


mcp_server = FastMCP(
    "dynalist-archive",
    instructions="""\
Dynalist is a tree-structured outliner. Search results show matching nodes, but
the real content is usually in the **children** underneath them.

## Best Practice: Always Read Subtrees After Searching

1. Search with dynalist_search_tool to find relevant nodes.
2. For EACH interesting result, call dynalist_read_node_tool with its node_id
   to retrieve the full subtree (children, grandchildren, etc.).
3. Use max_depth=2 or 3 for large subtrees to avoid overwhelming output.

Search results only contain the matched node's content — they do NOT include
children. A node titled "monorepo" may have 10 child links and notes that only
appear when you read its subtree.

## Tips
- Read multiple search results, not just the first one.
- Use dynalist_get_node_context_tool to see siblings and position in the tree.
- Breadcrumbs show the ancestor path (e.g. "peat > archive > monorepo").
""",
    lifespan=server_lifespan,
)


def _ctx(mcp_ctx: Context) -> ServerContext:
    return mcp_ctx.request_context.lifespan_context  # type: ignore[return-value]


async def _auto_update(ctx: ServerContext) -> None:
    """Re-import changed files from disk if cooldown has elapsed.

    Uses a lock to prevent concurrent imports from corrupting the database.
    """
    if not ctx.source_dir:
        return
    async with ctx.auto_update_lock:
        maybe_auto_update(ctx.conn, ctx.source_dir)


# --- MCP Tool Wrappers ---


@mcp_server.tool()
async def dynalist_search_tool(
    ctx: Context,
    query: str = "",
    document: str | None = None,
    below_node: str | None = None,
    include_breadcrumbs: bool = True,
    limit: int = 20,
    offset: int = 0,
    response_format: str = "concise",
) -> dict[str, Any]:
    """Search archived Dynalist nodes using full-text search.

    Returns nodes matching the query. Query syntax: Words are ANDed.
    Use "quoted phrases" for exact matches. Prefix matching is automatic
    for 3+ char words.

    IMPORTANT: Dynalist is a tree-structured outliner. Search results only
    contain the matched node's own text — child nodes are NOT included.
    The real content is often in the children underneath a match. You MUST
    call dynalist_read_node_tool on each interesting result's node_id to
    retrieve the full subtree. Use max_depth=2 or 3 for large subtrees.

    Pagination: When has_more is true, use next_offset in a follow-up call.

    Args:
        query: Search text.
        document: Filter by document title/filename.
        below_node: Restrict to subtree below this node ID.
        include_breadcrumbs: Include ancestor chain in results.
        limit: Max results (1-50, default 20).
        offset: Pagination offset.
        response_format: "concise" or "detailed".
    """
    await _auto_update(_ctx(ctx))
    return dynalist_search(
        _ctx(ctx).conn,
        query=query,
        document=document,
        below_node=below_node,
        include_breadcrumbs=include_breadcrumbs,
        limit=limit,
        offset=offset,
        response_format=response_format,
    )


@mcp_server.tool()
async def dynalist_read_node_tool(
    ctx: Context,
    node_id: str,
    document: str | None = None,
    max_depth: int | None = None,
    output_format: str = "markdown",
    include_notes: bool = True,
) -> dict[str, Any]:
    """Read a node and its subtree as markdown or structured JSON.

    Use this after finding an interesting node via dynalist_search to see
    its full content. Pass the document's root node with max_depth to get
    a table of contents.

    Args:
        node_id: Node ID to read.
        document: Document title/filename/file_id.
        max_depth: Max depth levels (None = unlimited).
        output_format: "markdown" (human-readable) or "json" (structured).
        include_notes: Include node notes in output.
    """
    await _auto_update(_ctx(ctx))
    return dynalist_read_node(
        _ctx(ctx).conn,
        node_id=node_id,
        document=document,
        max_depth=max_depth,
        output_format=output_format,
        include_notes=include_notes,
    )


@mcp_server.tool()
async def dynalist_list_documents_tool(ctx: Context) -> dict[str, Any]:
    """List all documents in the Dynalist archive with metadata.

    Use this to discover document names for filtering searches.
    """
    await _auto_update(_ctx(ctx))
    return dynalist_list_documents(_ctx(ctx).conn)


@mcp_server.tool()
async def dynalist_get_recent_changes_tool(
    ctx: Context,
    document: str | None = None,
    since: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_breadcrumbs: bool = True,
) -> dict[str, Any]:
    """Get recently modified nodes across all documents.

    Use this to see what was recently added or changed.

    Args:
        document: Filter by document title/filename.
        since: Only changes after this date (YYYY-MM-DD).
        limit: Max results (1-100, default 20).
        offset: Pagination offset.
        include_breadcrumbs: Include ancestor chain.
    """
    await _auto_update(_ctx(ctx))
    return dynalist_get_recent_changes(
        _ctx(ctx).conn,
        document=document,
        since=since,
        limit=limit,
        offset=offset,
        include_breadcrumbs=include_breadcrumbs,
    )


@mcp_server.tool()
async def dynalist_get_node_context_tool(
    ctx: Context,
    node_id: str,
    document: str | None = None,
    sibling_count: int = 3,
    child_limit: int = 20,
) -> dict[str, Any]:
    """Get a node with its surrounding context.

    Returns the node with breadcrumbs (ancestors), siblings, and children.
    Use this after search to understand a node's position in the tree.

    Args:
        node_id: Node ID from search results.
        document: Document title/filename/file_id.
        sibling_count: Siblings before/after to include.
        child_limit: Max direct children to show.
    """
    await _auto_update(_ctx(ctx))
    return dynalist_get_node_context(
        _ctx(ctx).conn,
        node_id=node_id,
        document=document,
        sibling_count=sibling_count,
        child_limit=child_limit,
    )


@mcp_server.tool()
async def dynalist_edit_node_tool(
    ctx: Context,
    node_id: str,
    document: str,
    content: str | None = None,
    note: str | None = None,
    checked: bool | None = None,
) -> dict[str, Any]:
    """Edit a node's content, note, or checked state.

    Writes via the Dynalist API and re-syncs the local database.
    Use sparingly (rate-limited to 60 requests/min).

    Args:
        node_id: Node ID to edit.
        document: Document title/filename/file_id (required).
        content: New content text.
        note: New note text.
        checked: New checked state.
    """
    return dynalist_edit_node(
        _ctx(ctx).conn,
        node_id=node_id,
        document=document,
        content=content,
        note=note,
        checked=checked,
    )


@mcp_server.tool()
async def dynalist_add_node_tool(
    ctx: Context,
    parent_id: str,
    document: str,
    content: str,
    note: str | None = None,
    index: int = -1,
    checked: bool | None = None,
) -> dict[str, Any]:
    """Add a new node under a parent.

    Writes via the Dynalist API and re-syncs the local database.
    Use sparingly (rate-limited to 60 requests/min).

    Args:
        parent_id: Parent node ID.
        document: Document title/filename/file_id (required).
        content: Content for the new node.
        note: Optional note text.
        index: Position among siblings (-1 = last).
        checked: Optional checked state.
    """
    return dynalist_add_node(
        _ctx(ctx).conn,
        parent_id=parent_id,
        document=document,
        content=content,
        note=note,
        index=index,
        checked=checked,
    )


def run_mcp_server() -> None:
    """Run the MCP server with stdio transport."""
    from dynalist_archive.logging_config import configure_logging

    configure_logging(verbose=False)
    mcp_server.run(transport="stdio")
