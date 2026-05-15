"""Placeholder login window — will be replaced in Phase 2."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from chenedusys.core.event_bus import EventBus


class LoginWindow(QWidget):
    """Minimal placeholder window displayed on startup."""

    def __init__(self, bus: EventBus) -> None:
        super().__init__()
        self.bus = bus
        self.setWindowTitle("ChenEduSys")
        self.resize(400, 300)

        layout = QVBoxLayout(self)
        label = QLabel("Login")
        label.setStyleSheet("font-size: 24px; font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
