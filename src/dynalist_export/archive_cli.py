"""CLI for the Dynalist archive (search, read, MCP server)."""

import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from dynalist_export.config import resolve_data_directory
from dynalist_export.core.database.schema import migrate_schema
from dynalist_export.core.importer.loader import import_source_dir
from dynalist_export.core.search.searcher import search_nodes
from dynalist_export.core.tree.markdown import render_subtree_as_markdown
from dynalist_export.logging_config import configure_logging

app = typer.Typer(help="Dynalist archive: search and browse your Dynalist notes.")

# Default source: where dynalist-backup stores .c.json files (first existing dir)
_DEFAULT_SOURCE_DIR = resolve_data_directory()

# Default archive location
_DEFAULT_DATA_DIR = Path("~/.local/share/dynalist-archive").expanduser()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    configure_logging(verbose=verbose)


@app.command(name="import")
def import_cmd(
    source_dir: Annotated[
        Path | None,
        typer.Option("--source-dir", "-s", help="Directory with .c.json files"),
    ] = None,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", "-d", help="Archive database directory"),
    ] = None,
    force: bool = typer.Option(False, "--force", "-f", help="Re-import all files"),
) -> None:
    """Import Dynalist export files into the archive database."""
    src = source_dir or _DEFAULT_SOURCE_DIR
    dst = data_dir or _DEFAULT_DATA_DIR

    if not src.exists():
        logger.error("Source directory not found: {}", src)
        raise typer.Exit(1)

    dst.mkdir(parents=True, exist_ok=True)
    db_path = dst / "archive.db"

    conn = sqlite3.connect(str(db_path))
    try:
        migrate_schema(conn)
        stats = import_source_dir(conn, src, force=force)
        typer.echo(
            f"Imported {stats.documents_imported} documents "
            f"({stats.nodes_imported} nodes), "
            f"skipped {stats.documents_skipped}"
        )
    finally:
        conn.close()


def _open_db(data_dir: Path | None) -> sqlite3.Connection:
    """Open the archive database, raising if it doesn't exist."""
    dst = data_dir or _DEFAULT_DATA_DIR
    db_path = dst / "archive.db"
    if not db_path.exists():
        logger.error("Archive database not found: {}. Run 'import' first.", db_path)
        raise typer.Exit(1)
    return sqlite3.connect(str(db_path))


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    document: Annotated[
        str | None,
        typer.Option("--document", "-D", help="Restrict to a document (title or file_id)"),
    ] = None,
    below: Annotated[
        str | None,
        typer.Option("--below", "-b", help="Restrict to subtree below this node path"),
    ] = None,
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", "-d", help="Archive database directory"),
    ] = None,
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Search for nodes matching a query."""
    import json as json_mod

    conn = _open_db(data_dir)
    try:
        # Resolve document name to ID if needed
        doc_id: str | None = None
        if document:
            row = conn.execute(
                "SELECT file_id FROM documents WHERE title = ? OR file_id = ? OR filename = ?",
                (document, document, document),
            ).fetchone()
            if row:
                doc_id = row[0]
            else:
                typer.echo(f"Document '{document}' not found.")
                raise typer.Exit(1)

        results, total = search_nodes(
            conn, query=query, document_id=doc_id, below_node_path=below, limit=limit
        )

        if output_json:
            data = {
                "results": [
                    {
                        "node_id": r.node.id,
                        "document": r.document_title,
                        "content": r.node.content,
                        "snippet": r.snippet,
                        "path": r.node.path,
                    }
                    for r in results
                ],
                "total": total,
            }
            typer.echo(json_mod.dumps(data, indent=2))
        else:
            typer.echo(f"Found {total} results (showing {len(results)}):\n")
            for r in results:
                typer.echo(f"  [{r.document_title}] {r.node.content[:80]}")
                if r.node.note:
                    typer.echo(f"    note: {r.node.note[:60]}")
                typer.echo(f"    id={r.node.id}  path={r.node.path}")
                typer.echo()
    finally:
        conn.close()


def _resolve_document_id(conn: sqlite3.Connection, document: str) -> str | None:
    """Resolve a document name/filename/file_id to a file_id."""
    row = conn.execute(
        "SELECT file_id FROM documents WHERE title = ? OR file_id = ? OR filename = ?",
        (document, document, document),
    ).fetchone()
    return row[0] if row else None


@app.command()
def documents(
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", "-d", help="Archive database directory"),
    ] = None,
) -> None:
    """List all archived documents."""
    conn = _open_db(data_dir)
    try:
        rows = conn.execute(
            "SELECT file_id, title, filename, node_count FROM documents ORDER BY title"
        ).fetchall()
        typer.echo(f"{len(rows)} documents:\n")
        for file_id, title, filename, node_count in rows:
            typer.echo(f"  {title} ({filename}) - {node_count} nodes  [id={file_id}]")
    finally:
        conn.close()


@app.command()
def read(
    node_id: str = typer.Argument(..., help="Node ID to read"),
    document: Annotated[
        str | None,
        typer.Option("--document", "-D", help="Document title/filename/file_id"),
    ] = None,
    max_depth: Annotated[
        int | None,
        typer.Option("--max-depth", "-m", help="Max depth levels to render"),
    ] = None,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", "-d", help="Archive database directory"),
    ] = None,
) -> None:
    """Read a node and its subtree as markdown."""
    conn = _open_db(data_dir)
    try:
        if document:
            doc_id = _resolve_document_id(conn, document)
            if not doc_id:
                typer.echo(f"Document '{document}' not found.")
                raise typer.Exit(1)
        else:
            row = conn.execute("SELECT document_id FROM nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                typer.echo(f"Node '{node_id}' not found.")
                raise typer.Exit(1)
            doc_id = row[0]

        md = render_subtree_as_markdown(
            conn, document_id=doc_id, node_id=node_id, max_depth=max_depth
        )
        if md:
            typer.echo(md)
        else:
            typer.echo(f"Node '{node_id}' not found in document.")
    finally:
        conn.close()


@app.command()
def serve() -> None:
    """Start the MCP server (stdio transport)."""
    from dynalist_export.mcp.server import run_mcp_server

    run_mcp_server()


@app.command()
def recent(
    document: Annotated[
        str | None,
        typer.Option("--document", "-D", help="Restrict to a document"),
    ] = None,
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", "-d", help="Archive database directory"),
    ] = None,
) -> None:
    """Show recently modified nodes."""
    from datetime import UTC, datetime

    conn = _open_db(data_dir)
    try:
        query = (
            "SELECT n.id, n.document_id, n.content, n.modified, n.path, d.title "
            "FROM nodes n JOIN documents d ON d.file_id = n.document_id "
        )
        params: list[str | int] = []

        if document:
            doc_id = _resolve_document_id(conn, document)
            if not doc_id:
                typer.echo(f"Document '{document}' not found.")
                raise typer.Exit(1)
            query += "WHERE n.document_id = ? "
            params.append(doc_id)

        query += "ORDER BY n.modified DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        for node_id_val, _doc_id, content, modified, path, doc_title in rows:
            dt = datetime.fromtimestamp(modified / 1000, tz=UTC)
            typer.echo(f"  [{doc_title}] {content[:80]}")
            typer.echo(f"    {dt:%Y-%m-%d %H:%M}  id={node_id_val}  path={path}")
            typer.echo()
    finally:
        conn.close()
