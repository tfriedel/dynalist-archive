"""Tests for tree navigation (breadcrumbs, siblings, subtree)."""

import sqlite3

from dynalist_export.core.tree.navigation import get_breadcrumbs, get_siblings
from dynalist_export.models.node import Breadcrumb


def test_breadcrumbs_for_nested_node(populated_db: sqlite3.Connection) -> None:
    """n1a is at /root/n1/n1a in doc1 -- breadcrumbs should be root, n1."""
    # Get the n1a node
    row = populated_db.execute(
        "SELECT path, document_id FROM nodes WHERE id = 'n1a' AND document_id = 'doc1'"
    ).fetchone()
    assert row is not None
    path, doc_id = row

    breadcrumbs = get_breadcrumbs(populated_db, document_id=doc_id, path=path)
    assert len(breadcrumbs) == 2
    assert breadcrumbs[0] == Breadcrumb(node_id="root", content="Notes", depth=0)
    assert breadcrumbs[1] == Breadcrumb(
        node_id="n1", content="Python is great for scripting", depth=1
    )


def test_siblings_of_middle_node(populated_db: sqlite3.Connection) -> None:
    """n1 has sibling n2 (both children of root in doc1)."""
    before, after = get_siblings(populated_db, document_id="doc1", parent_id="root", sort_order=0)
    assert len(before) == 0  # n1 is first child
    assert len(after) == 1
    assert after[0].id == "n2"
