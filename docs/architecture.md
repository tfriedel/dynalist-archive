# Dynalist Archive: MCP Server + CLI Tool

## Context

Dynalist is an outliner note-taking app with a tree-structured data model. An existing tool (`~/projects/dynalist_export`) syncs Dynalist documents to local `.c.json` files via the API. We want to add a search/navigation layer on top of this synced data -- a CLI tool and MCP server -- extending the existing project. Architecture follows `~/projects/mattermost_archive`.

The dataset is small (8 documents, ~11K nodes, 4.2MB JSON) but deeply nested (trees up to 10+ levels). The primary challenge is making tree-structured data searchable and navigable for an AI agent.

## Key Decisions

**SQLite with adjacency list + materialized path** -- No graph DB needed at this scale. FTS5 for full-text search. Materialized `path` column (`/root/abc123/def456`) enables subtree queries via `LIKE` prefix and instant breadcrumb computation.

**Extend `~/projects/dynalist_export`** -- Add the archive/search/MCP modules alongside the existing sync code. The existing `api.py`, `config.py`, and `downloader.py` are reused directly.

**7 MCP tools** (5 read + 2 write) -- "Consolidate over proliferate". One unified search tool handles global, per-doc, and subtree search. Outline is handled by `read_node` on root with `max_depth`.

**Re-import after writes** -- After successful API write, re-import that document from API to keep DB consistent.

**Import from existing `.c.json` files** -- The existing sync tool handles API rate limits and version checking. Archive imports its output. Auto-reimport on MCP startup when source files changed.

---

## SQLite Schema

```sql
CREATE TABLE documents (
    file_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,           -- basename from _raw_filenames.json
    version INTEGER,
    node_count INTEGER DEFAULT 0,
    imported_at INTEGER NOT NULL      -- Unix timestamp ms
);

CREATE TABLE nodes (
    id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    parent_id TEXT,                    -- NULL for root nodes
    content TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created INTEGER NOT NULL,         -- Unix timestamp ms
    modified INTEGER NOT NULL,
    sort_order INTEGER NOT NULL,      -- Position among siblings (0-based)
    depth INTEGER NOT NULL,           -- Tree depth (root=0)
    path TEXT NOT NULL,               -- Materialized: "/root/abc123/def456"
    checked INTEGER,                  -- Nullable boolean
    color INTEGER,
    child_count INTEGER DEFAULT 0,
    PRIMARY KEY (document_id, id),
    FOREIGN KEY (document_id) REFERENCES documents(file_id)
);

CREATE INDEX idx_nodes_parent ON nodes(document_id, parent_id);
CREATE INDEX idx_nodes_modified ON nodes(modified DESC);
CREATE INDEX idx_nodes_path ON nodes(path);

CREATE VIRTUAL TABLE nodes_fts USING fts5(
    content, note,
    content='nodes', content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sync_state (
    document_id TEXT PRIMARY KEY,
    version INTEGER,
    last_import_at INTEGER,
    source_hash TEXT                   -- SHA256 of .c.json file
);
```

## Domain Models (`models/node.py`)

```python
Document(frozen):  file_id, title, filename, version, node_count
Node(frozen):      id, document_id, parent_id, content, note, created, modified,
                   sort_order, depth, path, checked, color, child_count
Breadcrumb(frozen): node_id, content, depth
SearchResult(frozen): node, document_title, snippet, breadcrumbs, score
NodeContext(frozen): node, document, breadcrumbs, children, siblings
```

## MCP Tools (7 total)

### Read Tools (5)

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `dynalist_search` | FTS across all/doc/subtree | `query`, `document?`, `below_node?`, `include_breadcrumbs`, `limit`, `offset`, `response_format` |
| `dynalist_read_node` | Read node subtree as markdown or JSON | `node_id`, `document?`, `max_depth?`, `output_format` (markdown/json), `include_notes` |
| `dynalist_list_documents` | List all documents with stats | (none) |
| `dynalist_get_recent_changes` | Recently modified nodes | `document?`, `since?`, `limit`, `include_breadcrumbs` |
| `dynalist_get_node_context` | Node + breadcrumbs + siblings + children | `node_id`, `document?`, `sibling_count`, `child_limit` |

### Write Tools (2)

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `dynalist_edit_node` | Edit node via API, then re-import | `node_id`, `document`, `content?`, `note?`, `checked?` |
| `dynalist_add_node` | Add node via API, then re-import | `parent_id`, `document`, `content`, `note?`, `index` |

All tools include Dynalist URLs (`https://dynalist.io/d/{file_id}#z={node_id}`), `response_format` support, and `has_more`/`next_offset` pagination.

## CLI Commands

The existing `dynalist-backup` entry point stays for sync. New entry point: `dynalist-archive`.

```
dynalist-archive import [--source-dir] [--data-dir] [--force]
dynalist-archive search <query> [--document] [--below] [--limit] [--json]
dynalist-archive read <node_id> [--document] [--max-depth]
dynalist-archive documents
dynalist-archive recent [--document] [--limit]
dynalist-archive serve   # MCP server (stdio)
```

## Project Structure

Existing files untouched. New modules added under `src/dynalist_export/`:

```
src/dynalist_export/
├── __init__.py                         # (existing)
├── api.py                              # (existing) -- reused for write ops
├── cli.py                              # (existing) -- sync CLI
├── config.py                           # (existing) -- reused for paths
├── downloader.py                       # (existing) -- _iterate_contents() reused
├── writer.py                           # (existing)
│
├── archive_cli.py                      # NEW: Typer CLI for archive commands
├── logging_config.py                   # NEW: Loguru setup
├── models/
│   ├── __init__.py
│   └── node.py                         # Document, Node, Breadcrumb, SearchResult, NodeContext
├── core/
│   ├── importer/
│   │   ├── json_reader.py              # Parse .c.json -> (Document, list[Node])
│   │   └── loader.py                   # Orchestrate import: read files, compute tree, insert DB
│   ├── database/
│   │   └── schema.py                   # Create/migrate schema
│   ├── search/
│   │   └── searcher.py                 # FTS5 search with scoping (global/doc/subtree)
│   ├── tree/
│   │   ├── navigation.py               # Breadcrumbs, siblings, subtree retrieval
│   │   └── markdown.py                 # Node tree -> markdown rendering
│   └── write/
│       └── client.py                   # Dynalist API write + re-import trigger
└── mcp/
    └── server.py                       # FastMCP server, lifespan, tool definitions

skills/
└── dynalist-search/
    └── SKILL.md

tests/
└── unit/
    ├── conftest.py                     # In-memory DB fixtures, small test document JSON
    ├── test_archive_cli.py
    ├── test_json_reader.py
    ├── test_loader.py
    ├── test_markdown.py
    ├── test_mcp_tools.py
    ├── test_models.py
    ├── test_navigation.py
    ├── test_schema.py
    ├── test_searcher.py
    └── test_write_client.py
```

## Dependencies Added

```toml
# Added to existing pyproject.toml
"loguru>=0.7.0",
"mcp[cli]>=1.9.0",
"typer>=0.21.1",
"rich>=14.2.0",
```

New entry point in `[project.scripts]`:
```toml
dynalist-archive = "dynalist_export.archive_cli:app"
```

## Key Files Reused

| Source | What was reused |
|--------|--------------|
| `dynalist_export/downloader.py:184` `_iterate_contents()` | Tree walker algorithm -- ported to `json_reader.py` with path/depth computation |
| `dynalist_export/config.py` `DATA_DIRECTORIES` | Source dir for `.c.json` files |
| `dynalist_export/api.py` `DynalistApi` | API client for write operations |
| `mattermost_archive/mcp/server.py` | ServerContext + lifespan pattern, tool wrapper separation |
| `mattermost_archive/core/search/searcher.py` | FTS5 query building, sanitization, pagination |

## Implementation Phases

### Phase 1: Foundation
- Domain models (`models/node.py`)
- Schema creation (`core/database/schema.py`)
- JSON reader -- parse `.c.json` into `(Document, list[Node])` with tree metadata
- Loader -- orchestrate import (read files, hash check, insert DB, rebuild FTS)
- `dynalist-archive import` CLI command
- Add dependencies to `pyproject.toml`
- Tests for each module (TDD, one at a time per CLAUDE.md)

### Phase 2: Search
- FTS5 query parser (sanitization, prefix matching, phrase support)
- Searcher with scoping: global, per-document (`WHERE document_id = ?`), below-node (`WHERE path LIKE ? || '%'`)
- `dynalist-archive search` CLI command
- Tests

### Phase 3: Tree Navigation
- Breadcrumb computation (parse `path` column, batch-fetch ancestor content)
- Sibling retrieval (`WHERE parent_id = ? ORDER BY sort_order`)
- Subtree retrieval + markdown rendering (recursive depth-limited)
- `dynalist-archive read`, `documents`, `recent` CLI commands
- Tests

### Phase 4: MCP Server
- ServerContext + lifespan with auto-import
- All 5 read tools (separated core logic from MCP wrappers)
- Size warning system (estimate tokens, warn > 5000)
- `dynalist-archive serve` CLI command
- Tests

### Phase 5: Write + Polish
- Write client wrapping existing `DynalistApi` + re-import after write
- 2 write tools (`dynalist_edit_node`, `dynalist_add_node`)
- Skill file (`skills/dynalist-search/SKILL.md`)

## Verification

1. `dynalist-archive import` -- imports all 8 docs from `~/.local/share/dynalist-backup/`
2. `dynalist-archive documents` -- shows 8 documents, ~11K nodes
3. `dynalist-archive search "interview"` -- returns hits with breadcrumbs and Dynalist URLs
4. `dynalist-archive search "API" --document peat` -- scoped to one document
5. `dynalist-archive read <node_id>` -- renders subtree as markdown with context
6. `dynalist-archive recent` -- shows recently modified nodes
7. MCP: `dynalist-archive serve` via Claude Desktop config, test each tool
8. `uv run --frozen pytest` -- all 29 tests pass
9. `ruff check` -- no lint issues
