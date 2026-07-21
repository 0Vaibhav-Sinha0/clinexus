##############################################################################
# config/logging_config.py
#
# PURPOSE:
#   Central logging configuration for the entire Clinexus project.
#   Every module (agents, API, ingestion, processing, memory, etc.)
#   imports this file so that logs remain consistent across the application.
#
# USAGE:
#   from config.logging_config import setup_logging
#
#   logger = setup_logging(__name__)
#   logger.info("Application started")
##############################################################################

import logging
import sys


def setup_logging(name: str) -> logging.Logger:
    """
    Create and return a configured logger for a module.

    Args:
        name: Usually pass __name__.

    Returns:
        Configured logging.Logger instance.
    """

    logger = logging.getLogger(name)

    # Prevent duplicate handlers if the logger already exists
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Stream logs to stdout (captured automatically by Cloud Run)
    handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Prevent duplicate logging from the root logger
    logger.propagate = False

    return logger