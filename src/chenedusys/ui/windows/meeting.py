"""Meeting window — shows connection status, participants, and meeting controls."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chenedusys.core.event_bus import EventBus
from chenedusys.services.meeting import MeetingService

logger = logging.getLogger(__name__)


class MeetingWindow(QWidget):
    """Window shown during an active meeting session."""

    closed = Signal()

    def __init__(
        self,
        meeting_service: MeetingService,
        bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = meeting_service
        self._bus = bus
        self._subs = []

        self.setWindowTitle("ChenEduSys — Meeting")
        self.setMinimumSize(800, 500)
        self._setup_ui()
        self._subscribe_events()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        self._status_label = QLabel("Status: Connecting...")
        self._status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(self._status_label)
        header.addStretch()

        self._meeting_id_label = QLabel(f"Meeting: {self._service.meeting_id or '—'}")
        self._meeting_id_label.setStyleSheet("color: gray;")
        header.addWidget(self._meeting_id_label)
        layout.addLayout(header)

        # Participant bar placeholder
        self._participant_label = QLabel("Participants: loading...")
        self._participant_label.setStyleSheet(
            "padding: 8px; background-color: #f0f0f0; border-radius: 4px;"
        )
        layout.addWidget(self._participant_label)

        # Content area (placeholder for paint/PDF later)
        self._content_area = QLabel("Meeting content will appear here")
        self._content_area.setAlignment(Qt.AlignCenter)
        self._content_area.setStyleSheet(
            "background-color: white; border: 1px solid #ccc; "
            "border-radius: 4px; font-size: 16px; color: #999;"
        )
        layout.addWidget(self._content_area, stretch=1)

        # Controls
        controls = QHBoxLayout()
        self._mute_btn = QPushButton("Mute")
        self._mute_btn.setFixedWidth(80)
        self._mute_btn.clicked.connect(self._toggle_mute)
        controls.addWidget(self._mute_btn)

        controls.addStretch()

        self._end_btn = QPushButton("End Meeting")
        self._end_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        self._end_btn.setFixedWidth(120)
        self._end_btn.clicked.connect(self._end_meeting)
        controls.addWidget(self._end_btn)

        layout.addLayout(controls)

        self._muted = False
        self._update_status()

    # ------------------------------------------------------------------
    # Event subscriptions
    # ------------------------------------------------------------------

    def _subscribe_events(self) -> None:
        sub = self._bus.subscribe("network.p2p_connected", self._on_p2p_connected)
        self._subs.append(sub)
        sub = self._bus.subscribe("network.p2p_disconnected", self._on_p2p_disconnected)
        self._subs.append(sub)
        sub = self._bus.subscribe("network.p2p_connect_failed", self._on_p2p_failed)
        self._subs.append(sub)

    def _unsubscribe_events(self) -> None:
        for sub in self._subs:
            sub.unsubscribe()
        self._subs.clear()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_p2p_connected(self, event: object) -> None:
        self._update_status()
        self._update_participants()

    def _on_p2p_disconnected(self, event: object) -> None:
        self._update_status()
        self._update_participants()

    def _on_p2p_failed(self, event: object) -> None:
        self._status_label.setText("Status: Connection Failed")
        self._status_label.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: red;"
        )

    # ------------------------------------------------------------------
    # UI updates
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        if self._service.is_teacher:
            count = self._service.peers.__len__()
            if count > 0:
                self._status_label.setText(f"Status: Connected ({count} student(s))")
                self._status_label.setStyleSheet(
                    "font-weight: bold; font-size: 14px; color: green;"
                )
            else:
                self._status_label.setText("Status: Waiting for students...")
                self._status_label.setStyleSheet(
                    "font-weight: bold; font-size: 14px; color: orange;"
                )
        else:
            if self._service._client and self._service._client.connected:
                self._status_label.setText("Status: Connected to teacher")
                self._status_label.setStyleSheet(
                    "font-weight: bold; font-size: 14px; color: green;"
                )
            else:
                self._status_label.setText("Status: Connecting...")
                self._status_label.setStyleSheet(
                    "font-weight: bold; font-size: 14px; color: orange;"
                )

    def _update_participants(self) -> None:
        if self._service.is_teacher:
            names = list(self._service.peers.keys())
            total = len(names) + 1  # +1 for teacher
            self._participant_label.setText(
                f"Participants ({total}): You (teacher)"
                + (f", {', '.join(names)}" if names else "")
            )
        else:
            self._participant_label.setText("Participants: You (student), Teacher")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        self._mute_btn.setText("Unmute" if self._muted else "Mute")
        self._bus.publish(
            _SimpleEvent("audio.mute_toggle", {"muted": self._muted})
        )

    def _end_meeting(self) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(self._service.stop())
        self.close()

    def closeEvent(self, event) -> None:
        self._unsubscribe_events()
        self.closed.emit()
        super().closeEvent(event)


class _SimpleEvent:
    __slots__ = ("topic", "data")

    def __init__(self, topic: str, data: dict) -> None:
        self.topic = topic
        self.data = data
