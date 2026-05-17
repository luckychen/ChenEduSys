"""Meeting window — shows connection status, participants, content, and controls."""

from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chenedusys.core.event_bus import EventBus
from chenedusys.services.content_sync import ContentSync
from chenedusys.services.meeting import MeetingService
from chenedusys.services.paint_engine import PaintEngine
from chenedusys.ui.widgets.audio_controls import AudioControls
from chenedusys.ui.widgets.content_view import ContentView
from chenedusys.ui.widgets.participant_bar import ParticipantBar

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

        self._paint_engine = PaintEngine(bus)
        self._content_sync = ContentSync(bus)
        self._content_sync.set_role(meeting_service.is_teacher)

        self.setWindowTitle("ChenEduSys — Meeting")
        self.setMinimumSize(1024, 700)
        self._setup_ui()
        self._subscribe_events()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # Header bar
        header = QHBoxLayout()
        self._status_label = QLabel("Status: Connecting...")
        self._status_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        header.addWidget(self._status_label)
        header.addStretch()

        self._meeting_id_label = QLabel(f"Meeting: {self._service.meeting_id or ''}")
        self._meeting_id_label.setStyleSheet("color: gray; font-size: 12px;")
        header.addWidget(self._meeting_id_label)
        layout.addLayout(header)

        # Participant bar
        self._participant_bar = ParticipantBar()
        layout.addWidget(self._participant_bar)

        # Content area (PDF + paint)
        self._content_view = ContentView(self._paint_engine)
        self._content_view.stroke_finished.connect(self._on_local_stroke)
        layout.addWidget(self._content_view, stretch=1)

        # Page navigation + controls bar
        nav = QHBoxLayout()

        self._load_pdf_btn = QPushButton("Open PDF")
        self._load_pdf_btn.setFixedWidth(80)
        self._load_pdf_btn.clicked.connect(self._open_pdf)
        nav.addWidget(self._load_pdf_btn)

        self._prev_btn = QPushButton("< Prev")
        self._prev_btn.setFixedWidth(60)
        self._prev_btn.clicked.connect(lambda: self._content_sync.change_page(
            self._content_sync.current_page - 1
        ))
        nav.addWidget(self._prev_btn)

        self._page_label = QLabel("Page: -")
        self._page_label.setStyleSheet("font-size: 12px;")
        nav.addWidget(self._page_label)

        self._next_btn = QPushButton("Next >")
        self._next_btn.setFixedWidth(60)
        self._next_btn.clicked.connect(lambda: self._content_sync.change_page(
            self._content_sync.current_page + 1
        ))
        nav.addWidget(self._next_btn)

        nav.addStretch()

        # Paint mode buttons
        self._pen_btn = QPushButton("Pen")
        self._pen_btn.setFixedWidth(50)
        self._pen_btn.setStyleSheet("background-color: #2ecc71; color: white;")
        self._pen_btn.clicked.connect(lambda: self._set_paint_mode("pen"))
        nav.addWidget(self._pen_btn)

        self._eraser_btn = QPushButton("Eraser")
        self._eraser_btn.setFixedWidth(60)
        self._eraser_btn.clicked.connect(lambda: self._set_paint_mode("eraser"))
        nav.addWidget(self._eraser_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(50)
        self._clear_btn.clicked.connect(self._clear_paint)
        nav.addWidget(self._clear_btn)

        nav.addStretch()

        # Audio controls
        self._audio_controls = AudioControls()
        self._audio_controls.mute_toggled.connect(self._toggle_mute)
        self._audio_controls.volume_changed.connect(self._set_volume)
        nav.addWidget(self._audio_controls)

        # End meeting
        self._end_btn = QPushButton("End")
        self._end_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        self._end_btn.setFixedWidth(60)
        self._end_btn.clicked.connect(self._end_meeting)
        nav.addWidget(self._end_btn)

        layout.addLayout(nav)

        self._muted = False
        self._update_status()

    # ------------------------------------------------------------------
    # Event subscriptions
    # ------------------------------------------------------------------

    def _subscribe_events(self) -> None:
        self._sub("network.p2p_connected", self._on_p2p_connected)
        self._sub("network.p2p_disconnected", self._on_p2p_disconnected)
        self._sub("network.p2p_connect_failed", self._on_p2p_failed)
        self._sub("content.pdf_loaded", self._on_pdf_loaded)
        self._sub("content.page_changed", self._on_page_changed)
        self._sub("content.remote_stroke", self._on_remote_stroke)
        self._sub("content.remote_erase", self._on_remote_erase)
        self._sub("content.remote_clear", self._on_remote_clear)
        self._sub("network.p2p_message", self._on_p2p_message)

    def _sub(self, topic: str, handler) -> None:
        self._subs.append(self._bus.subscribe(topic, handler))

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
        self._status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: red;")

    def _on_pdf_loaded(self, event: object) -> None:
        data = getattr(event, "data", {})
        page_count = data.get("page_count", 0)
        self._page_label.setText(f"Page: 1/{page_count}")
        self._paint_engine.page_number = 0

        # Render first page as background
        if self._content_sync.pdf_data:
            self._render_pdf_page(0)

    def _on_page_changed(self, event: object) -> None:
        page = getattr(event, "data", {}).get("page", 0)
        self._paint_engine.page_number = page
        self._page_label.setText(f"Page: {page + 1}/{self._content_sync.total_pages}")
        self._render_pdf_page(page)

    def _on_remote_stroke(self, event: object) -> None:
        from chenedusys.core.models import Stroke
        stroke = getattr(event, "data", {}).get("stroke")
        if stroke:
            self._paint_engine.apply_remote_stroke(stroke)
            self._content_view.update()

    def _on_remote_erase(self, event: object) -> None:
        # Erase by stroke ID — search and remove
        stroke_id = getattr(event, "data", {}).get("stroke_id", "")
        for s in list(self._paint_engine.strokes):
            if s.id == stroke_id:
                self._paint_engine.erase_at(s.points[0].x, s.points[0].y, radius=1000)
                break
        self._content_view.update()

    def _on_remote_clear(self, event: object) -> None:
        page = getattr(event, "data", {}).get("page_number", 0)
        self._paint_engine.page_number = page
        self._paint_engine.clear()
        self._content_view.update()

    def _on_p2p_message(self, event: object) -> None:
        data = getattr(event, "data", {})
        channel = data.get("channel")
        payload = data.get("payload")
        if channel is not None and payload is not None:
            self._content_sync.handle_message(channel, payload)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            self._content_sync.load_pdf(path)

    def _on_local_stroke(self, stroke) -> None:
        self._content_sync.send_stroke(stroke)

    def _set_paint_mode(self, mode: str) -> None:
        self._content_view.mode = mode
        if mode == "pen":
            self._pen_btn.setStyleSheet("background-color: #2ecc71; color: white;")
            self._eraser_btn.setStyleSheet("")
        else:
            self._eraser_btn.setStyleSheet("background-color: #e74c3c; color: white;")
            self._pen_btn.setStyleSheet("")

    def _clear_paint(self) -> None:
        page = self._paint_engine.page_number
        self._paint_engine.clear()
        self._content_sync.send_clear(page)
        self._content_view.update()

    def _toggle_mute(self, muted: bool) -> None:
        self._muted = muted

    def _set_volume(self, volume: float) -> None:
        pass  # wired to AudioService in full integration

    def _end_meeting(self) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(self._service.stop())
        self.close()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _render_pdf_page(self, page_num: int) -> None:
        """Render a PDF page and set it as the content view background."""
        if not self._content_sync.pdf_data:
            return
        try:
            import fitz
            doc = fitz.open(stream=self._content_sync.pdf_data, filetype="pdf")
            if page_num < len(doc):
                page = doc[page_num]
                # Render at screen-appropriate DPI
                dpi = 150
                pix = page.get_pixmap(dpi=dpi)
                from PySide6.QtGui import QImage
                img = QImage(
                    pix.samples, pix.width, pix.height,
                    pix.stride, QImage.Format.Format_RGB888,
                )
                pixmap = QPixmap.fromImage(img)
                self._content_view.set_pdf_background(pixmap)
            doc.close()
        except Exception as exc:
            logger.warning("Failed to render PDF page %d: %s", page_num, exc)

    def _update_status(self) -> None:
        if self._service.is_teacher:
            count = len(self._service.peers)
            if count > 0:
                self._status_label.setText(f"Connected ({count} student(s))")
                self._status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: green;")
            else:
                self._status_label.setText("Waiting for students...")
                self._status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: orange;")
        else:
            if self._service._client and self._service._client.connected:
                self._status_label.setText("Connected to teacher")
                self._status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: green;")
            else:
                self._status_label.setText("Connecting...")
                self._status_label.setStyleSheet("font-weight: bold; font-size: 13px; color: orange;")

    def _update_participants(self) -> None:
        if self._service.is_teacher:
            peers = self._service.peers
            self._participant_bar.set_participants([
                {"user_id": "teacher", "username": "You", "role": "teacher", "connected": True}
            ] + [
                {"user_id": pid, "username": pid, "role": "student", "connected": True}
                for pid in peers
            ])
        else:
            self._participant_bar.set_participants([
                {"user_id": "teacher", "username": "Teacher", "role": "teacher", "connected": True},
                {"user_id": "me", "username": "You", "role": "student", "connected": True},
            ])

    def closeEvent(self, event) -> None:
        self._unsubscribe_events()
        self.closed.emit()
        super().closeEvent(event)
