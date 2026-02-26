"""Configuration constants for dynalist-backup."""

import os
from pathlib import Path

# API token location. First file found is used.
API_TOKEN_FILES: list[Path] = [
    Path("~/.config/dynalist-backup-token.txt").expanduser(),
    Path("~/.config/secret/dynalist-backup-token.txt").expanduser(),
    Path(f"/run/user/{os.getuid()}/dynalist-token"),
]

# Directory with data. First directory which is found is used.
DATA_DIRECTORIES: list[Path] = [
    Path("~/.local/share/dynalist-backup").expanduser(),
    Path("~/.dynalist-backup").expanduser(),
    Path("~/.config/dynalist-backup").expanduser(),
    Path("/tmp/dynalist-export"),
]

# Cache directory, used only when --cache is passed.
API_CACHE_PREFIX: str = "/tmp/dynalist-backup-cache/cache-"
