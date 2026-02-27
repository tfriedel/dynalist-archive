"""Tests for the FTS5 search engine."""

import sqlite3

from dynalist_archive.core.search.searcher import search_nodes


def test_search_finds_matching_content(populated_db: sqlite3.Connection) -> None:
    results, total = search_nodes(populated_db, query="python")
    assert total >= 2
    contents = [r.node.content for r in results]
    assert any("Python" in c for c in contents)


def test_search_scoped_to_document(populated_db: sqlite3.Connection) -> None:
    results, total = search_nodes(populated_db, query="python", document_id="doc1")
    assert total == 1
    assert results[0].node.content == "Python is great for scripting"


def test_search_below_node(populated_db: sqlite3.Connection) -> None:
    """Search only within a subtree (n1 and its children)."""
    # n1 has child n1a ("FastAPI for web services") -- search for "web" below n1
    results, total = search_nodes(populated_db, query="web", below_node_path="/root/n1")
    assert total == 1
    assert results[0].node.id == "n1a"


def test_search_pagination(populated_db: sqlite3.Connection) -> None:
    results_page1, total = search_nodes(populated_db, query="python", limit=1, offset=0)
    results_page2, _ = search_nodes(populated_db, query="python", limit=1, offset=1)
    assert total >= 2
    assert len(results_page1) == 1
    assert len(results_page2) == 1
    assert results_page1[0].node.id != results_page2[0].node.id
