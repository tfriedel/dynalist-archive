"""Tests for domain models."""

import pytest

from dynalist_export.models.node import Document


def test_document_is_frozen() -> None:
    doc = Document(file_id="abc", title="Test", filename="test")
    with pytest.raises(AttributeError):
        doc.title = "changed"  # type: ignore[misc]
