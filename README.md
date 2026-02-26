# dynalist-export

Back up your [Dynalist](https://dynalist.io) documents to local files. Based on [theamk/dynalist-backup](https://github.com/theamk/dynalist-backup).

## Features

- Incremental sync — only downloads documents that have changed
- Exports each document as `.c.json` (raw API data) and `.txt` (human-readable, git-diff-friendly)
- Optional git commit of changes after each sync
- Dry-run mode for previewing changes
- Request caching for development

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

3. Create a data directory:

```bash
mkdir -p ~/.local/share/dynalist-backup
```

## Usage

```bash
uv run dynalist-backup
```

### Options

| Flag | Description |
|---|---|
| `-v, --verbose` | Print debug messages |
| `-C, --cache` | Cache API requests (for development) |
| `--data-dir DIR` | Override data directory |
| `--dry-run` | Preview changes without writing |
| `--skip-clean` | Don't delete old files |
| `--commit` | Git commit results (data dir must be a git repo) |

### Git-tracked backups

To automatically commit each backup:

```bash
cd ~/.local/share/dynalist-backup
git init
uv run dynalist-backup --commit
```

### Token file locations

The first file found is used:

- `~/.config/dynalist-backup-token.txt`
- `~/.config/secret/dynalist-backup-token.txt`
- `/run/user/<uid>/dynalist-token`

### Data directory locations

The first directory found is used (or override with `--data-dir`):

- `~/.local/share/dynalist-backup`
- `~/.dynalist-backup`
- `~/.config/dynalist-backup`
- `/tmp/dynalist-export`

## Development

```bash
just setup       # Install deps and pre-commit hooks
just test        # Run tests
just lint        # Check code quality
just format      # Format code
just ci          # Full CI pipeline
```
