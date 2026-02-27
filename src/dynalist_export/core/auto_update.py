"""Auto-update logic: re-import changed files from disk before search."""

import sqlite3
import time
from pathlib import Path

from loguru import logger

from dynalist_export.config import AUTO_UPDATE_INTERVAL
from dynalist_export.core.database.schema import get_metadata, set_metadata


def is_update_needed(conn: sqlite3.Connection, interval: int) -> bool:
    """Check if archive needs updating based on interval.

    Args:
        conn: SQLite connection with metadata table.
        interval: Minimum seconds between updates.

    Returns:
        True if an update should be performed.
    """
    last_update = get_metadata(conn, "last_update_at")
    if last_update is None:
        return True
    return (time.time() - int(last_update)) >= interval


def maybe_auto_update(conn: sqlite3.Connection, source_dir: Path) -> None:
    """Re-import changed .c.json files from disk if cooldown has expired.

    Does not make API calls; use ``dynalist-backup`` to sync from the
    Dynalist API to disk first.

    Skips without blocking if:
    - The cooldown has not expired.
    - The source directory does not exist.

    On import failure, logs a warning and sets the cooldown to prevent
    retry storms.

    Args:
        conn: SQLite connection for the archive database.
        source_dir: Directory where .c.json backup files are stored.
    """
    if not is_update_needed(conn, AUTO_UPDATE_INTERVAL):
        return

    if not source_dir.exists():
        return

    try:
        from dynalist_export.core.importer.loader import import_source_dir

        import_source_dir(conn, source_dir)
    except Exception:
        logger.warning("Auto-import failed, continuing with existing data", exc_info=True)

    set_metadata(conn, "last_update_at", str(int(time.time())))
