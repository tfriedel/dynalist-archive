"""Domain models for the Dynalist archive."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    """A Dynalist document."""

    file_id: str
    title: str
    filename: str
    version: int | None = None
    node_count: int = 0


@dataclass(frozen=True)
class Node:
    """A single node in a Dynalist document tree."""

    id: str
    document_id: str
    parent_id: str | None
    content: str
    note: str
    created: int
    modified: int
    sort_order: int
    depth: int
    path: str
    checked: bool | None = None
    color: int | None = None
    child_count: int = 0


@dataclass(frozen=True)
class Breadcrumb:
    """A single ancestor in a breadcrumb trail."""

    node_id: str
    content: str
    depth: int


@dataclass(frozen=True)
class SearchResult:
    """A search hit with context."""

    node: Node
    document_title: str
    snippet: str
    breadcrumbs: tuple[Breadcrumb, ...] = ()
    score: float = 0.0


@dataclass(frozen=True)
class NodeContext:
    """A node with its surrounding context."""

    node: Node
    document: Document
    breadcrumbs: tuple[Breadcrumb, ...]
    children: tuple[Node, ...]
    siblings_before: tuple[Node, ...]
    siblings_after: tuple[Node, ...]
