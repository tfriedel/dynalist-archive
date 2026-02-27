"""Tests for JSON reader that parses .c.json files into domain models."""

from dynalist_export.core.importer.json_reader import parse_document_data

MINIMAL_DOC = {
    "file_id": "doc1",
    "title": "Test Doc",
    "version": 42,
    "nodes": [
        {
            "id": "root",
            "content": "Root",
            "note": "",
            "created": 1000,
            "modified": 2000,
            "children": ["a"],
        },
        {
            "id": "a",
            "content": "Child A",
            "note": "a note",
            "created": 1001,
            "modified": 2001,
        },
    ],
}


def test_parse_returns_document_with_correct_metadata() -> None:
    doc, _nodes = parse_document_data(MINIMAL_DOC, filename="test-doc")
    assert doc.file_id == "doc1"
    assert doc.title == "Test Doc"
    assert doc.filename == "test-doc"
    assert doc.version == 42
    assert doc.node_count == 2


def test_parse_computes_tree_metadata_for_nodes() -> None:
    _doc, nodes = parse_document_data(MINIMAL_DOC, filename="test-doc")
    root = nodes[0]
    child = nodes[1]

    assert root.id == "root"
    assert root.depth == 0
    assert root.path == "/root"
    assert root.parent_id is None
    assert root.child_count == 1

    assert child.id == "a"
    assert child.depth == 1
    assert child.path == "/root/a"
    assert child.parent_id == "root"
    assert child.content == "Child A"
    assert child.note == "a note"
    assert child.child_count == 0


MULTI_CHILD_DOC = {
    "file_id": "doc2",
    "title": "Multi",
    "version": 1,
    "nodes": [
        {
            "id": "root",
            "content": "",
            "note": "",
            "created": 1000,
            "modified": 2000,
            "children": ["a", "b", "c"],
        },
        {"id": "a", "content": "First", "note": "", "created": 1001, "modified": 2001},
        {
            "id": "b",
            "content": "Second",
            "note": "",
            "created": 1002,
            "modified": 2002,
            "children": ["b1"],
        },
        {"id": "b1", "content": "Nested", "note": "", "created": 1003, "modified": 2003},
        {"id": "c", "content": "Third", "note": "", "created": 1004, "modified": 2004},
    ],
}


def test_parse_assigns_sort_order_to_siblings() -> None:
    _doc, nodes = parse_document_data(MULTI_CHILD_DOC, filename="multi")
    by_id = {n.id: n for n in nodes}

    assert by_id["a"].sort_order == 0
    assert by_id["b"].sort_order == 1
    assert by_id["c"].sort_order == 2
    assert by_id["b1"].sort_order == 0  # only child of b
    assert by_id["b1"].depth == 2
    assert by_id["b1"].path == "/root/b/b1"
