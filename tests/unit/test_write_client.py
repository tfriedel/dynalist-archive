"""Tests for the Dynalist API write client."""

import sqlite3
from unittest.mock import MagicMock

from dynalist_export.core.write.client import add_node, edit_node


def test_edit_node_calls_api_and_returns_success(
    populated_db: sqlite3.Connection,
) -> None:
    mock_api = MagicMock()
    mock_api.call.return_value = {"_code": "Ok"}

    result = edit_node(
        populated_db,
        mock_api,
        node_id="n1",
        document_id="doc1",
        content="Updated content",
    )

    assert result["success"] is True
    # First call is doc/edit, second is doc/read for re-import
    edit_call = mock_api.call.call_args_list[0]
    assert edit_call[0][0] == "doc/edit"
    changes = edit_call[0][1]["changes"]
    assert changes[0]["action"] == "edit"
    assert changes[0]["node_id"] == "n1"
    assert changes[0]["content"] == "Updated content"


def test_add_node_calls_api_and_returns_new_id(
    populated_db: sqlite3.Connection,
) -> None:
    mock_api = MagicMock()
    mock_api.call.return_value = {
        "_code": "Ok",
        "new_node_ids": ["new123"],
    }

    result = add_node(
        populated_db,
        mock_api,
        parent_id="n1",
        document_id="doc1",
        content="New child node",
    )

    assert result["success"] is True
    assert result["node_id"] == "new123"
    insert_call = mock_api.call.call_args_list[0]
    changes = insert_call[0][1]["changes"]
    assert changes[0]["action"] == "insert"
    assert changes[0]["parent_id"] == "n1"
    assert changes[0]["content"] == "New child node"
