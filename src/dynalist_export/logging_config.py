"""Logging configuration for the Dynalist archive."""

import sys

from loguru import logger


def configure_logging(*, verbose: bool = False) -> None:
    """Configure loguru with appropriate level."""
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format="{level.icon} {message}")
