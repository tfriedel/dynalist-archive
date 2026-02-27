# dynalist-export

Back up and search your [Dynalist](https://dynalist.io) documents locally. Based on [theamk/dynalist-backup](https://github.com/theamk/dynalist-backup).

## Features

**Backup** (`dynalist-backup`)
- Incremental sync — only downloads documents that have changed
- Exports each document as `.c.json` (raw API data) and `.txt` (human-readable, git-diff-friendly)
- Optional git commit of changes after each sync
- Dry-run mode and request caching for development

**Archive & Search** (`dynalist-archive`)
- Imports `.c.json` exports into a searchable SQLite database with full-text search
- Search, browse, and read nodes as markdown or JSON
- Edit nodes and add new nodes via the Dynalist API
- Auto-syncs from Dynalist API and reimports into the database on search (5-minute cooldown)
- MCP server for LLM integration (Claude Code, etc.)

## Setup

### Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

### Install

```bash
uv sync
```

### Configure

1. Get your API token from Dynalist → Settings → Developer

2. Save it to a token file:

```bash
echo "your-api-token" > ~/.config/dynalist-backup-token.txt
```

3. Create data directories:

```bash
mkdir -p ~/.local/share/dynalist-backup
mkdir -p ~/.local/share/dynalist-archive
```

## Usage

### dynalist-backup

Syncs documents from the Dynalist API to local files.

```bash
uv run dynalist-backup
```

| Flag | Description |
|---|---|
| `-v, --verbose` | Print debug messages |
| `-C, --cache` | Cache API requests (for development) |
| `--data-dir DIR` | Override data directory |
| `--dry-run` | Preview changes without writing |
| `--skip-clean` | Don't delete old files |
| `--commit` | Git commit results (data dir must be a git repo) |

#### Git-tracked backups

```bash
cd ~/.local/share/dynalist-backup
git init
uv run dynalist-backup --commit
```

### dynalist-archive

Search, browse, and modify your archived Dynalist notes.

```bash
uv run dynalist-archive --help
```

#### Import

Import `.c.json` backup files into the archive database:

```bash
uv run dynalist-archive import
uv run dynalist-archive import --source-dir /path/to/backups --force
```

#### Search

```bash
uv run dynalist-archive search "meeting notes"
uv run dynalist-archive search "project plan" --document "Work" --limit 20
uv run dynalist-archive search "TODO" --json
```

#### Browse

```bash
uv run dynalist-archive documents              # List all documents
uv run dynalist-archive read NODE_ID            # Read a node as markdown
uv run dynalist-archive read NODE_ID --json     # Read as JSON tree
uv run dynalist-archive recent                  # Recently modified nodes
uv run dynalist-archive recent --document "Work"
```

#### Edit & Add

```bash
uv run dynalist-archive edit NODE_ID --document "Work" --content "Updated text"
uv run dynalist-archive add PARENT_ID --document "Work" --content "New item"
```

#### MCP Server

Start the MCP server for LLM integration (stdio transport):

```bash
uv run dynalist-archive serve
```

The MCP server exposes these tools:

| Tool | Description |
|---|---|
| `dynalist_search_tool` | Full-text search with pagination |
| `dynalist_read_node_tool` | Read a node subtree as markdown or JSON |
| `dynalist_list_documents_tool` | List all archived documents |
| `dynalist_get_recent_changes_tool` | Recently modified nodes |
| `dynalist_get_node_context_tool` | Node with breadcrumbs, siblings, children |
| `dynalist_edit_node_tool` | Edit a node via the Dynalist API |
| `dynalist_add_node_tool` | Add a new node via the Dynalist API |

### Configuration

#### Token file locations

The first file found is used:

- `~/.config/dynalist-backup-token.txt`
- `~/.config/secret/dynalist-backup-token.txt`
- `/run/user/<uid>/dynalist-token`

#### Backup data directory

The first directory found is used (or override with `--data-dir`):

- `~/.local/share/dynalist-backup`
- `~/.dynalist-backup`
- `~/.config/dynalist-backup`
- `/tmp/dynalist-export`

#### Archive data directory

Default: `~/.local/share/dynalist-archive` (override with `--data-dir` or `DYNALIST_ARCHIVE_DIR` env var).

The archive imports from the backup data directory by default (override with `--source-dir` or `DYNALIST_SOURCE_DIR` env var).

## Development

```bash
just setup       # Install deps and pre-commit hooks
just test        # Run tests
just lint        # Check code quality
just format      # Format code
just ci          # Full CI pipeline
```
