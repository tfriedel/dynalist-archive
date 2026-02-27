"""Auto-update logic: fetch from API and re-import before search."""

import sqlite3
import time
from pathlib import Path

from loguru import logger

from dynalist_export.api import DynalistApi
from dynalist_export.config import AUTO_UPDATE_INTERVAL
from dynalist_export.core.database.schema import get_metadata, set_metadata
from dynalist_export.downloader import Downloader
from dynalist_export.writer import FileWriter


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


def run_auto_backup(source_dir: Path) -> None:
    """Fetch fresh data from the Dynalist API and write .c.json files to disk.

    Silently returns on any failure (missing token, API errors, etc.)
    so the caller can continue with existing on-disk data.
    """
    try:
        api = DynalistApi(from_cache=False)
        writer = FileWriter(source_dir, dry_run=False)
        downloader = Downloader(writer)
        downloader.sync_all(api)
        writer.finalize(delete_others=False)
    except Exception:
        logger.warning("Auto-backup from API failed, continuing with existing data", exc_info=True)


def maybe_auto_update(conn: sqlite3.Connection, source_dir: Path) -> None:
    """Fetch fresh data from the Dynalist API and re-import into the archive.

    When the cooldown has expired, fetches updated documents from the
    Dynalist API to disk, then re-imports changed .c.json files into SQLite.

    Skips without blocking if:
    - The cooldown has not expired.
    - The source directory does not exist.

    On failure, logs a warning and sets the cooldown to prevent
    retry storms.

    Args:
        conn: SQLite connection for the archive database.
        source_dir: Directory where .c.json backup files are stored.
    """
    if not is_update_needed(conn, AUTO_UPDATE_INTERVAL):
        return

    if not source_dir.exists():
        return

    run_auto_backup(source_dir)

    try:
        from dynalist_export.core.importer.loader import import_source_dir

        import_source_dir(conn, source_dir)
    except Exception:
        logger.warning("Auto-import failed, continuing with existing data", exc_info=True)

    set_metadata(conn, "last_update_at", str(int(time.time())))
