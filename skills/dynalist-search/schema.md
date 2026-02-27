# JSON Output Schemas

Reference documentation for `dynalist-archive` JSON output formats.

## Documents (`documents --json`)

```json
{
  "documents": [
    {
      "file_id": "abc123",
      "title": "My Notes",
      "filename": "my_notes",
      "node_count": 542,
      "url": "https://dynalist.io/d/abc123"
    }
  ],
  "count": 12,
  "total_nodes": 3456
}
```

### Document Object

| Field        | Type   | Description                        |
| ------------ | ------ | ---------------------------------- |
| `file_id`    | string | Unique Dynalist document ID        |
| `title`      | string | Document title                     |
| `filename`   | string | Local filename (without extension) |
| `node_count` | int    | Total nodes in this document       |
| `url`        | string | Dynalist permalink                 |

### Top-Level Fields

| Field         | Type | Description                     |
| ------------- | ---- | ------------------------------- |
| `count`       | int  | Number of documents             |
| `total_nodes` | int  | Sum of all document node counts |

## Search Results (`search --json`)

```json
{
  "results": [
    {
      "node_id": "xyz789",
      "document": "My Notes",
      "content": "First 120 chars of content...",
      "snippet": "...matching text with context...",
      "url": "https://dynalist.io/d/abc123#z=xyz789",
      "modified": "2024-01-22T14:30:00+00:00",
      "breadcrumbs": "Root > Section > Parent"
    }
  ],
  "count": 10,
  "total": 42,
  "has_more": true,
  "next_offset": 10
}
```

### Search Result Object

| Field         | Type   | Description                               |
| ------------- | ------ | ----------------------------------------- |
| `node_id`     | string | Unique node identifier                    |
| `document`    | string | Document title containing this node       |
| `content`     | string | First 120 characters of node content      |
| `snippet`     | string | Text excerpt around the match             |
| `url`         | string | Dynalist permalink                        |
| `modified`    | string | ISO 8601 modification timestamp           |
| `breadcrumbs` | string | Ancestor chain                            |

### Pagination Fields

| Field         | Type    | Description                                    |
| ------------- | ------- | ---------------------------------------------- |
| `count`       | int     | Number of results in this response             |
| `total`       | int     | Total matching nodes                           |
| `has_more`    | boolean | True if more results available                 |
| `next_offset` | int     | Offset for next page (only present if has_more)|

## Read Node — Markdown (`read <node_id>`)

Default output (no `--json` flag) is an indented markdown bullet list:

```
- Node content
    - Child node
        - Grandchild
        > Note text on grandchild
    - [x] Checked item
    - [ ] Unchecked item
    - Another child [+3 children]
```

Features:
- 4-space indentation per depth level
- Checkbox rendering: `- [ ]` and `- [x]`
- Notes rendered as `> quoted blocks`
- Truncation indicators (`[+N children]`) when cut off by `--max-depth`

## Read Node — JSON (`read <node_id> --json`)

```json
{
  "node": {
    "id": "xyz789",
    "content": "Node content text",
    "path": "/root/abc123/xyz789"
  },
  "children": [
    {
      "id": "child1",
      "content": "Child node text",
      "note": "Optional note",
      "child_count": 2,
      "children": []
    }
  ],
  "breadcrumbs": "Root > Parent > Grandparent",
  "url": "https://dynalist.io/d/abc123#z=xyz789",
  "estimated_tokens": 1500
}
```

### Node Object (root)

| Field     | Type   | Description                              |
| --------- | ------ | ---------------------------------------- |
| `id`      | string | Node identifier                          |
| `content` | string | Node text content                        |
| `path`    | string | Materialized tree path                   |

### Child Object (recursive)

| Field         | Type        | Description                                    |
| ------------- | ----------- | ---------------------------------------------- |
| `id`          | string      | Node identifier                                |
| `content`     | string      | Node text content                              |
| `note`        | string      | Note/annotation text                           |
| `child_count` | int         | Number of direct children                      |
| `children`    | array       | Nested child objects (recursive, up to max_depth)|

### Top-Level Fields

| Field              | Type        | Description                                  |
| ------------------ | ----------- | -------------------------------------------- |
| `breadcrumbs`      | string      | Ancestor chain: `"Root > Parent > Node"`     |
| `url`              | string      | Dynalist permalink                           |
| `estimated_tokens` | int         | Approximate token count (markdown only)      |
| `warning`          | string/null | Present when estimated_tokens > 5000         |

## Recent Changes (`recent --json`)

```json
{
  "results": [
    {
      "node_id": "xyz789",
      "document": "My Notes",
      "content": "First 120 chars of content...",
      "modified": "2024-01-22T14:30:00+00:00",
      "created": "2024-01-20T10:00:00+00:00",
      "url": "https://dynalist.io/d/abc123#z=xyz789",
      "breadcrumbs": "Root > Section > Parent"
    }
  ],
  "count": 20,
  "total": 156,
  "has_more": true,
  "next_offset": 20
}
```

### Recent Result Object

| Field         | Type   | Description                               |
| ------------- | ------ | ----------------------------------------- |
| `node_id`     | string | Unique node identifier                    |
| `document`    | string | Document title                            |
| `content`     | string | First 120 characters of node content      |
| `modified`    | string | ISO 8601 modification timestamp           |
| `created`     | string | ISO 8601 creation timestamp               |
| `url`         | string | Dynalist permalink                        |
| `breadcrumbs` | string | Ancestor chain                            |

### Pagination Fields

| Field         | Type    | Description                                    |
| ------------- | ------- | ---------------------------------------------- |
| `count`       | int     | Number of results in this response             |
| `total`       | int     | Total matching results                         |
| `has_more`    | boolean | True if more results available                 |
| `next_offset` | int     | Offset for next page (only present if has_more)|
