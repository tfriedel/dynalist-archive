"""Tests for markdown rendering of node trees."""

import sqlite3

from dynalist_export.core.tree.markdown import render_subtree_as_markdown


def test_render_subtree_with_depth_limit(populated_db: sqlite3.Connection) -> None:
    """Render doc1 root with max_depth=1 should show root children but not grandchildren."""
    md = render_subtree_as_markdown(populated_db, document_id="doc1", node_id="root", max_depth=1)
    assert "Python is great for scripting" in md
    assert "Rust is fast" in md
    # n1a is at depth 2 relative to root, should be excluded
    assert "FastAPI" not in md


def test_render_full_subtree_includes_notes(populated_db: sqlite3.Connection) -> None:
    """Full render of n1 subtree should include notes and grandchildren."""
    md = render_subtree_as_markdown(populated_db, document_id="doc1", node_id="n1")
    assert "Python is great for scripting" in md
    assert "use type hints" in md  # note on n1
    assert "FastAPI for web services" in md  # child n1a
