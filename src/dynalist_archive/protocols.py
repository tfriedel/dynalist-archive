"""Protocols for dependency injection in the backup tool."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ApiProtocol(Protocol):
    """Protocol for Dynalist API clients."""

    def call(self, path: str, args: dict[str, Any]) -> dict[str, Any]:
        """Invoke an API endpoint and return the JSON response."""
        ...


@runtime_checkable
class WriterProtocol(Protocol):
    """Protocol for file writers used by the downloader."""

    def make_data_file(
        self,
        fname_rel: str,
        *,
        contents: str | None = None,
        data: Any = None,
    ) -> None:
        """Write a file to the output directory."""
        ...

    def make_unique_name(self, base: str, *, suffix: str = "") -> str:
        """Generate a unique filename or prefix."""
        ...

    def try_read_json(self, fname_rel: str) -> Any | None:
        """Read JSON from a file, returning None if not found."""
        ...
