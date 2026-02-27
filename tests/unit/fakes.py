"""Fake implementations for testing the backup tool."""

import json
from typing import Any


class FakeApi:
    """In-memory fake for DynalistApi.

    Stores predefined responses and records all calls for assertions.
    """

    def __init__(self) -> None:
        self.responses: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def add_response(self, path: str, response: dict[str, Any]) -> None:
        """Register a response for a given API path."""
        self.responses[path] = response

    def call(self, path: str, args: dict[str, Any]) -> dict[str, Any]:
        """Return the predefined response and record the call."""
        self.calls.append((path, args))
        if path not in self.responses:
            msg = f"FakeApi: no response registered for {path!r}"
            raise KeyError(msg)
        return self.responses[path]


class FakeWriter:
    """In-memory fake for FileWriter.

    Stores files in a dict and implements unique name collision logic.
    """

    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self._unique_names: set[str] = set()

    def make_data_file(
        self,
        fname_rel: str,
        *,
        contents: str | None = None,
        data: Any = None,
    ) -> None:
        """Store file contents in memory."""
        if contents is not None:
            self.files[fname_rel] = contents
        else:
            self.files[fname_rel] = json.dumps(data, sort_keys=True, indent=4) + "\n"

    def make_unique_name(self, base: str, *, suffix: str = "") -> str:
        """Generate a unique name, appending -N on collision."""
        name = base
        count = 0
        while name + suffix in self._unique_names:
            count += 1
            name = f"{base}-{count}"
        self._unique_names.add(name + suffix)
        return name

    def try_read_json(self, fname_rel: str) -> Any | None:
        """Return stored JSON data, or None if not stored."""
        raw = self.files.get(fname_rel)
        if raw is None:
            return None
        return json.loads(raw)
