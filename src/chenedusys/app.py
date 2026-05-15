"""QApplication bootstrap for ChenEduSys."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from chenedusys.core.config import load_config
from chenedusys.core.event_bus import EventBus
from chenedusys.core.logger import setup_logging


def create_app(argv: list[str] | None = None) -> tuple[QApplication, EventBus]:
    """Create and return the ``(QApplication, EventBus)`` pair.

    This is the single entry point that wires together the core
    infrastructure. All windows receive the event bus so they can
    publish/subscribe without importing each other.
    """
    config = load_config()
    setup_logging(level=config.log_level, log_dir=config.log_dir)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("ChenEduSys")
    app.setOrganizationName("ChenEduSys")

    bus = EventBus()

    return app, bus
