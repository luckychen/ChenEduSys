"""Structured logging setup for ChenEduSys.

Configures the root ``chenedusys`` logger with:
  - Console handler (stdout)
  - File handler with rotation (5 MB per file, 3 backups)
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def setup_logging(level: str = "INFO", log_dir: str | Path | None = None) -> None:
    """Initialize the ``chenedusys`` logger.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    logger = logging.getLogger("chenedusys")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler (rotating)
    if log_dir is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path / "chenedusys.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.debug("Logging initialized (level=%s)", level)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``chenedusys`` namespace."""
    if not name.startswith("chenedusys"):
        name = f"chenedusys.{name}"
    return logging.getLogger(name)
