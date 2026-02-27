"""Parse Dynalist .c.json files into domain models."""

from collections import deque
from typing import Any

from dynalist_export.models.node import Document, Node


def parse_document_data(data: dict[str, Any], *, filename: str) -> tuple[Document, list[Node]]:
    """Parse a Dynalist document dict into a Document and list of Nodes.

    Args:
        data: Raw document data (as from a .c.json file).
        filename: The filename/basename for this document.

    Returns:
        Tuple of (Document, list of Nodes with tree metadata).
    """
    raw_nodes = data["nodes"]
    doc = Document(
        file_id=data["file_id"],
        title=data["title"],
        filename=filename,
        version=data.get("version"),
        node_count=len(raw_nodes),
    )

    nodes_by_id = {n["id"]: n for n in raw_nodes}
    result: list[Node] = []

    # BFS to compute depth, path, sort_order, parent_id.
    # sort_order comes from the position in the parent's children array.
    todo: deque[tuple[str, str | None, int, str, int]] = deque([("root", None, 0, "", 0)])
    while todo:
        node_id, parent_id, depth, parent_path, sort_order = todo.popleft()
        raw = nodes_by_id.pop(node_id)
        path = f"{parent_path}/{node_id}"
        children = raw.get("children", [])

        result.append(
            Node(
                id=node_id,
                document_id=doc.file_id,
                parent_id=parent_id,
                content=raw.get("content", ""),
                note=raw.get("note", ""),
                created=raw["created"],
                modified=raw["modified"],
                sort_order=sort_order,
                depth=depth,
                path=path,
                checked=raw.get("checked"),
                color=raw.get("color"),
                child_count=len(children),
            )
        )

        for i, child_id in enumerate(children):
            todo.append((child_id, node_id, depth + 1, path, i))

    if nodes_by_id:
        msg = f"Orphaned nodes: {sorted(nodes_by_id.keys())!r}"
        raise ValueError(msg)

    return doc, result
