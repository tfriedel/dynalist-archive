---
name: dynalist-search
description: Search and browse archived Dynalist notes. Use when finding notes, outlines, or navigating tree-structured content.
---

# Dynalist Search

Search and navigate locally archived Dynalist notes using `dynalist-archive`.

## Quick Reference

```bash
# List all documents
dynalist-archive documents

# Search across all documents
dynalist-archive search "topic" --json

# Search within a specific document
dynalist-archive search "topic" --document "Notes" --json

# Read a node and its subtree
dynalist-archive read <node_id>

# Recent changes
dynalist-archive recent --limit 20
```

## Common Options

| Option            | Description                                        |
| ----------------- | -------------------------------------------------- |
| `--json`, `-j`    | Structured JSON output (for search command)        |
| `--document`, `-D`| Filter by document title, filename, or file_id     |
| `--below`, `-b`   | Restrict search to subtree below a node path       |
| `--limit`, `-n`   | Max results (default: 10)                          |
| `--max-depth`, `-m`| Max depth levels for read command                 |
| `--data-dir`, `-d`| Custom archive database directory                  |

## Workflows

### Find and Explore Notes

Two-step workflow: search first, then read subtree.

```bash
# 1. Search for topic
dynalist-archive search "interview questions" --json

# 2. Read the full subtree of an interesting node
dynalist-archive read <node_id>

# 3. Read with depth limit for large subtrees
dynalist-archive read <node_id> --max-depth 2
```

### Search Within a Document

```bash
# Filter by document title
dynalist-archive search "recipe" --document "Recipes" --json

# Filter by document filename
dynalist-archive search "python" --document "notes" --json
```

### Browse Document Structure

```bash
# List all documents with node counts
dynalist-archive documents

# Read root of a document (table of contents)
dynalist-archive read root --document "Notes" --max-depth 1
```

### Import/Update Archive

```bash
# Import from default source directory
dynalist-archive import

# Import from custom source
dynalist-archive import --source-dir ~/dynalist-backup/ --data-dir ~/.local/share/dynalist-archive/

# Force re-import all files
dynalist-archive import --force
```

## Data Model

Dynalist documents are tree-structured outlines:
- Each **document** contains a tree of **nodes**
- Each **node** has: content, optional note, children, creation/modification timestamps
- Nodes have a **path** (materialized path like `/root/abc123/def456`) for tree navigation
- Node IDs are stable and can be used in Dynalist URLs: `https://dynalist.io/d/{file_id}#z={node_id}`

## FTS5 Query Syntax

| Pattern        | Meaning        | Example                              |
|----------------|----------------|--------------------------------------|
| `word1 word2`  | Both words (AND) | `python web`                       |
| `"exact phrase"`| Exact match   | `"interview questions"`              |
| `word*`        | Prefix match   | `deploy*` (matches deploy, deployed) |

Words with 3+ characters automatically get prefix matching.

## Tips

- Use `--json` for structured output when piping to `jq`
- Use `--max-depth 1` or `2` to preview large subtrees without overwhelming output
- Node IDs from search results can be used with `read` command
- The archive auto-imports on MCP server startup when source files have changed
- Documents can be referenced by title, filename, or file_id
