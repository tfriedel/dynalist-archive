"""Tests for MCP tool core functions."""

import sqlite3

from dynalist_archive.mcp.server import (
    dynalist_get_node_context,
    dynalist_get_recent_changes,
    dynalist_list_documents,
    dynalist_read_node,
    dynalist_search,
)


def test_dynalist_search_returns_results_with_metadata(
    populated_db: sqlite3.Connection,
) -> None:
    result = dynalist_search(populated_db, query="python")
    assert result["count"] >= 2
    assert result["total"] >= 2
    assert len(result["results"]) >= 2
    first = result["results"][0]
    assert "node_id" in first
    assert "document" in first
    assert "content" in first
    assert "url" in first


def test_dynalist_list_documents_returns_all_docs(
    populated_db: sqlite3.Connection,
) -> None:
    result = dynalist_list_documents(populated_db)
    assert result["count"] == 2
    titles = {d["title"] for d in result["documents"]}
    assert titles == {"Notes", "Recipes"}


def test_dynalist_read_node_returns_markdown(
    populated_db: sqlite3.Connection,
) -> None:
    result = dynalist_read_node(populated_db, node_id="n1")
    assert "error" not in result
    assert "Python is great" in result["content"]
    assert "FastAPI" in result["content"]  # child included
    assert "url" in result
    assert "breadcrumbs" in result


def test_dynalist_read_node_json_includes_recursive_children(
    populated_db: sqlite3.Connection,
) -> None:
    """JSON format should include nested children up to max_depth."""
    result = dynalist_read_node(
        populated_db, node_id="root", document="doc1", output_format="json", max_depth=2
    )
    assert "error" not in result
    # Root's children should be present
    children = result["children"]
    assert len(children) >= 2  # n1 and n2
    # n1 has a child (n1a) which should be nested
    n1 = next(c for c in children if c["id"] == "n1")
    assert "children" in n1
    assert any(gc["id"] == "n1a" for gc in n1["children"])


def test_dynalist_read_node_json_truncates_at_max_depth(
    populated_db: sqlite3.Connection,
) -> None:
    """At max_depth boundary, nodes have child_count but no children key."""
    result = dynalist_read_node(
        populated_db, node_id="root", document="doc1", output_format="json", max_depth=1
    )
    assert "error" not in result
    n1 = next(c for c in result["children"] if c["id"] == "n1")
    assert n1["child_count"] == 1
    assert "children" not in n1  # truncated — signals "drill down"


def test_dynalist_get_recent_changes_returns_results(
    populated_db: sqlite3.Connection,
) -> None:
    result = dynalist_get_recent_changes(populated_db, limit=5)
    assert result["count"] >= 1
    assert result["total"] >= 1
    first = result["results"][0]
    assert "node_id" in first
    assert "modified" in first
    assert "url" in first


def test_dynalist_get_node_context_returns_structure(
    populated_db: sqlite3.Connection,
) -> None:
    result = dynalist_get_node_context(populated_db, node_id="n1")
    assert "error" not in result
    assert result["node"]["id"] == "n1"
    assert "breadcrumbs" in result
    assert "children" in result
    assert "siblings_before" in result
    assert "siblings_after" in result
    assert len(result["children"]) >= 1  # n1a is a child
