"""Tests for markdown rendering of node trees."""

import sqlite3

from dynalist_archive.core.tree.markdown import render_subtree_as_markdown


def test_render_subtree_with_depth_limit(populated_db: sqlite3.Connection) -> None:
    """Render doc1 root with max_depth=1 should show root children but not grandchildren."""
    md = render_subtree_as_markdown(populated_db, document_id="doc1", node_id="root", max_depth=1)
    assert "Python is great for scripting" in md
    assert "Rust is fast" in md
    # n1a is at depth 2 relative to root, should be excluded
    assert "FastAPI" not in md


def test_render_subtree_with_depth_limit_shows_truncation(
    populated_db: sqlite3.Connection,
) -> None:
    """Nodes at the depth boundary with children show a truncation indicator."""
    md = render_subtree_as_markdown(populated_db, document_id="doc1", node_id="root", max_depth=1)
    # n1 has child_count=1, so we should see a truncation indicator
    assert "... (1 more child" in md
    assert "n1a" not in md  # the actual child content is still excluded


def test_render_subtree_no_truncation_for_childless_nodes(
    populated_db: sqlite3.Connection,
) -> None:
    """Leaf nodes at the depth boundary should not show truncation indicator."""
    md = render_subtree_as_markdown(populated_db, document_id="doc1", node_id="root", max_depth=1)
    # n2 has child_count=0, so no truncation indicator after "Rust is fast"
    lines = md.split("\n")
    rust_idx = next(i for i, line in enumerate(lines) if "Rust is fast" in line)
    # Lines after n2's note should not contain "..."
    remaining = "\n".join(lines[rust_idx + 2 :])  # skip content + note line
    assert "... (0 more" not in remaining


def test_render_subtree_no_truncation_without_max_depth(
    populated_db: sqlite3.Connection,
) -> None:
    """Full render without max_depth should never show truncation indicators."""
    md = render_subtree_as_markdown(populated_db, document_id="doc1", node_id="root")
    assert "... (" not in md


def test_render_full_subtree_includes_notes(populated_db: sqlite3.Connection) -> None:
    """Full render of n1 subtree should include notes and grandchildren."""
    md = render_subtree_as_markdown(populated_db, document_id="doc1", node_id="n1")
    assert "Python is great for scripting" in md
    assert "use type hints" in md  # note on n1
    assert "FastAPI for web services" in md  # child n1a
