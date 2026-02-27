"""Dynalist API client with optional caching."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import requests

from dynalist_archive.config import API_CACHE_PREFIX, API_TOKEN_FILES


class DynalistApi:
    """Encapsulated Dynalist API with caching."""

    def __init__(self, *, from_cache: bool = False) -> None:
        self.from_cache = from_cache
        self.sess = requests.Session()
        self.logger = logging.getLogger("api")

        api_token_name: str | None = None
        for token_path in API_TOKEN_FILES:
            try:
                self.api_token = token_path.read_text(encoding="utf-8").strip()
                api_token_name = str(token_path)
                break
            except FileNotFoundError:
                pass
        else:
            msg = f"Cannot find dynalist token file, was looking at {API_TOKEN_FILES!r}"
            raise RuntimeError(msg)

        self.api_cache_prefix: str | None = API_CACHE_PREFIX

        if not self.from_cache:
            # We could imagine "write-only" cache mode, but for now, we do not bother.
            self.api_cache_prefix = None

        self.logger.debug(
            f"API ready: token from {api_token_name!r}, "
            f"from_cache {self.from_cache!r}, api_cache_prefix {self.api_cache_prefix!r}"
        )

        if self.api_cache_prefix:
            Path(self.api_cache_prefix).parent.mkdir(parents=True, exist_ok=True)

    def call(self, path: str, args: dict[str, Any]) -> dict[str, Any]:
        """Invoke dynalist API, return json."""
        name_last = path
        if args:
            params_str = json.dumps(args, sort_keys=True, separators=(",", ":"))
            if len(params_str) > 64:
                params_str = hashlib.sha1(params_str.encode("utf-8")).hexdigest()
            name_last += "--" + params_str

        log_name: str | None = None
        if self.api_cache_prefix:
            log_name = self.api_cache_prefix + name_last.replace("/", "--")

            if self.from_cache and Path(log_name).exists():
                self.logger.debug(f"Filled from cache: {log_name!r}")
                with open(log_name, encoding="utf-8") as f:
                    return json.load(f)  # type: ignore[no-any-return]

        self.logger.debug(f"Making request: {path!r} {repr(args)[:32]}")

        r = self.sess.post(
            f"https://dynalist.io/api/v1/{path}",
            json.dumps({"token": self.api_token, **args}),
        )
        r.raise_for_status()
        rv: dict[str, Any] = r.json()
        if rv["_code"] != "Ok" or rv.get("_msg"):
            msg = f"API call failed: ({path!r}, {args!r}) -> ({rv['_code']!r}, {rv.get('_msg')!r})"
            raise RuntimeError(msg)
        if self.api_cache_prefix and log_name:
            with open(log_name, "w", encoding="utf-8") as f:
                f.write(r.text)

        return rv
