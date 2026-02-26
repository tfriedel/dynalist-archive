# Development Guidelines

## Project Overview

CLI tool to back up Dynalist documents to local files. Syncs incrementally (only changed documents) and exports as `.c.json` (raw API) and `.txt` (human-readable).

## Architecture

```
src/dynalist_export/
├── config.py       # Constants: token paths, data dirs, cache prefix
├── api.py          # DynalistApi — HTTP client with caching
├── writer.py       # FileWriter — smart file writer with git commit support
├── downloader.py   # Downloader — sync logic, text conversion helpers
├── cli.py          # main() entry point with argparse
└── __init__.py     # Public API: DynalistApi, FileWriter, Downloader
```

## Quick Start

```bash
just setup           # Install deps and pre-commit hooks
uv run dynalist-backup --help
just test            # Run tests
just lint            # Check code quality
just format          # Format code
just ci              # Full CI pipeline
```

## Package Management

- ONLY use uv, NEVER pip
- Installation: `uv add package`
- Upgrading: `uv add --dev package --upgrade-package package`
- FORBIDDEN: `uv pip install`, `@latest` syntax

## Code Quality Standards

- Type hints required for all code
- Follow existing patterns exactly
- Use Google style for docstrings
- Ruff enforces: ANN, B, D, E, F, I, PTH, RUF, SIM, UP, W
- Use `pathlib.Path` instead of `os.path` (PTH rule)
- Use f-strings instead of %-formatting (UP rule)
- Use `raise ValueError`/`RuntimeError` instead of `assert` for validation

## Test-Driven Development (TDD)

- **ONE TEST AT A TIME**: Write failing test (RED) → minimal implementation (GREEN) → refactor (REFACTOR)
- **FAIL FIRST**: Always run the new test to confirm it fails before writing implementation
- **NO BULK TESTS**: TDD Guard blocks adding 4+ tests at once
- Framework: `uv run --frozen pytest`
- New features require tests; bug fixes require regression tests

## Version Control

- Conventional Commits style for commit messages
- Work on feature branches
- Never commit secrets (API tokens, .env files)

## Code Formatting and Linting

```bash
just format      # Format with ruff
just lint        # Check with ruff
just lint-fix    # Auto-fix issues
just pre-commit  # Run pre-commit hooks
```

## Pre-commit Hooks

- Uses `prek` (fast Rust-based pre-commit runner)
- `sync-with-uv` keeps `.pre-commit-config.yaml` versions in sync with `uv.lock`
- Config: `.pre-commit-config.yaml`
- Tools: sync-with-uv, uv-lock, Ruff, Zuban
