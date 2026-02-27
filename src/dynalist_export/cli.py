"""Command-line interface for dynalist-backup."""

import argparse
import logging
from pathlib import Path

from dynalist_export.api import DynalistApi
from dynalist_export.config import DATA_DIRECTORIES
from dynalist_export.downloader import Downloader
from dynalist_export.protocols import ApiProtocol
from dynalist_export.writer import FileWriter


def run_backup(
    writer: FileWriter,
    api: ApiProtocol,
    *,
    skip_clean: bool = False,
    commit: bool = False,
) -> None:
    """Execute the backup pipeline.

    Args:
        writer: File writer for the output directory.
        api: API client for fetching Dynalist data.
        skip_clean: If True, do not delete old files.
        commit: If True, create a git commit after syncing.
    """
    if commit:
        writer.check_git()

    downloader = Downloader(writer)
    downloader.sync_all(api)

    writer.finalize(delete_others=not skip_clean)

    if commit:
        writer.git_commit(dry_run=writer.dry_run)


def main() -> None:
    """Run the dynalist backup CLI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true", help="Print debug messages")
    parser.add_argument(
        "-C",
        "--cache",
        action="store_true",
        help="Cache requests and use cache. Returns stale data, but prevents ratelimits "
        "while developing",
    )
    parser.add_argument("--data-dir", metavar="DIR", help="Data directory (must be a git root)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write anything")
    parser.add_argument("--skip-clean", action="store_true", help="Do not delete old files")
    parser.add_argument("--commit", action="store_true", help="Git commit results")
    args = parser.parse_args()

    logging.basicConfig(
        level=(logging.DEBUG if args.verbose else logging.INFO),
        format="[%(levelname).1s] %(name)s: %(message)s",
    )

    data_dir: str
    if args.data_dir:
        data_dir = str(Path(args.data_dir).expanduser())
    else:
        for candidate in DATA_DIRECTORIES:
            if candidate.is_dir():
                data_dir = str(candidate)
                break
        else:
            msg = f"Cannot find data directories, none of those exist: {DATA_DIRECTORIES!r}"
            raise RuntimeError(msg)

    writer = FileWriter(data_dir, dry_run=args.dry_run)
    api = DynalistApi(from_cache=args.cache)
    run_backup(writer, api, skip_clean=args.skip_clean, commit=args.commit)
