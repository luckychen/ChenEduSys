"""Participant bar — shows connected users and their status."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from chenedusys.core.models import User


class ParticipantBar(QWidget):
    """Horizontal bar showing meeting participants with status indicators."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._participants: list[dict] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(8)
        self._labels: list[QLabel] = []

    def set_participants(self, participants: list[dict]) -> None:
        """Update the participant list.

        Each dict should have: ``user_id``, ``username``, ``role``,
        and optionally ``connected`` (bool).
        """
        self._participants = participants
        self._rebuild()

    def add_participant(self, user_id: str, username: str, role: str, connected: bool = True) -> None:
        self._participants.append({
            "user_id": user_id,
            "username": username,
            "role": role,
            "connected": connected,
        })
        self._rebuild()

    def remove_participant(self, user_id: str) -> None:
        self._participants = [p for p in self._participants if p["user_id"] != user_id]
        self._rebuild()

    def set_connected(self, user_id: str, connected: bool) -> None:
        for p in self._participants:
            if p["user_id"] == user_id:
                p["connected"] = connected
                break
        self._rebuild()

    def _rebuild(self) -> None:
        # Clear existing
        for label in self._labels:
            self._layout.removeWidget(label)
            label.deleteLater()
        self._labels.clear()

        for p in self._participants:
            name = p.get("username", p.get("user_id", "?"))
            role = p.get("role", "student")
            connected = p.get("connected", True)

            indicator = "+" if connected else "-"
            role_icon = "[T]" if role == "teacher" else "  "
            text = f"{indicator} {role_icon} {name}"

            label = QLabel(text)
            label.setAlignment(Qt.AlignVCenter)
            if connected:
                label.setStyleSheet("color: #2ecc71; font-size: 12px;")
            else:
                label.setStyleSheet("color: #95a5a6; font-size: 12px;")
            self._layout.addWidget(label)
            self._labels.append(label)

        self._layout.addStretch()
