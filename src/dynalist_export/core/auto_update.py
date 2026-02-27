"""Auto-update logic: sync from Dynalist API before search operations."""

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
    """Run backup sync + re-import if enough time has elapsed.

    Silently skips if:
    - The cooldown has not expired
    - No API token is configured
    - Any error occurs during sync (logs warning, never blocks search)

    Args:
        conn: SQLite connection for the archive database.
        source_dir: Directory where .c.json backup files are stored.
    """
    if not is_update_needed(conn, AUTO_UPDATE_INTERVAL):
        return

    try:
        from dynalist_export.api import DynalistApi
        from dynalist_export.cli import run_backup
        from dynalist_export.core.importer.loader import import_source_dir
        from dynalist_export.writer import FileWriter

        api = DynalistApi()
        writer = FileWriter(str(source_dir), dry_run=False)
        run_backup(writer, api)
        import_source_dir(conn, source_dir)
    except RuntimeError:
        # No API token configured — read-only mode
        logger.debug("Auto-update skipped: no API token configured")
        return
    except Exception:
        logger.warning("Auto-update failed, continuing with existing data")
        return

    set_metadata(conn, "last_update_at", str(int(time.time())))
