"""Content sync service — transfers PDF and synchronizes page/paint state between peers."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from chenedusys.core.event_bus import EventBus
from chenedusys.core.models import Point, Stroke
from chenedusys.transport.protocol import CONTENT, CONTROL, PAINT

logger = logging.getLogger(__name__)

# Content message types
MSG_PDF_TRANSFER = "pdf_transfer"
MSG_PAGE_CHANGE = "page_change"
MSG_STROKE = "stroke"
MSG_ERASE = "erase"
MSG_CLEAR = "clear"
MSG_PDF_CHUNK = "pdf_chunk"

_CHUNK_SIZE = 256 * 1024  # 256 KB chunks for PDF transfer


class ContentSync:
    """Synchronizes PDF content and paint strokes between teacher and students.

    Teacher is the source of truth:
    - Teacher loads a PDF → sends it to all students
    - Teacher changes page → notifies all students
    - Teacher draws a stroke → sends stroke data to all students
    - Student draws a stroke → sends stroke data to teacher (who relays)

    Uses the P2P CONTENT channel for PDF data and PAINT channel for strokes.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._pdf_data: bytes | None = None
        self._current_page: int = 0
        self._total_pages: int = 0
        self._send_fn = None  # set by set_send_function
        self._is_teacher = False
        self._chunk_buffer: dict[str, list[bytes]] = {}  # transfer_id -> chunks
        self._pending_chunks: dict[str, int] = {}  # transfer_id -> expected chunks

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_send_function(self, fn) -> None:
        """Set the function used to send data over P2P.

        For teacher: ``fn(channel, payload)`` broadcasts to all peers.
        For student: ``fn(channel, payload)`` sends to teacher.
        """
        self._send_fn = fn

    def set_role(self, is_teacher: bool) -> None:
        self._is_teacher = is_teacher

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def total_pages(self) -> int:
        return self._total_pages

    @property
    def has_pdf(self) -> bool:
        return self._pdf_data is not None

    @property
    def pdf_data(self) -> bytes | None:
        return self._pdf_data

    # ------------------------------------------------------------------
    # Teacher actions (broadcast to students)
    # ------------------------------------------------------------------

    def load_pdf(self, path: str) -> bool:
        """Load a PDF file and broadcast it to students."""
        try:
            import fitz
            doc = fitz.open(path)
            self._pdf_data = Path(path).read_bytes()
            self._total_pages = len(doc)
            self._current_page = 0
            doc.close()
        except Exception as exc:
            logger.error("Failed to load PDF: %s", exc)
            return False

        if self._send_fn and self._is_teacher:
            self._send_pdf_to_students()

        self._bus.publish(_SyncEvent("content.pdf_loaded", {
            "page_count": self._total_pages,
            "current_page": 0,
        }))
        return True

    def change_page(self, page_num: int) -> None:
        """Change the current page and notify peers."""
        if self._pdf_data is None:
            return
        if page_num < 0 or page_num >= self._total_pages:
            return
        self._current_page = page_num

        if self._send_fn and self._is_teacher:
            self._send_fn(CONTROL, {
                "type": MSG_PAGE_CHANGE,
                "page": page_num,
            })

        self._bus.publish(_SyncEvent("content.page_changed", {
            "page": page_num,
        }))

    def send_stroke(self, stroke: Stroke) -> None:
        """Send a completed paint stroke to peers."""
        if not self._send_fn:
            return

        msg = {
            "type": MSG_STROKE,
            "stroke": stroke.to_dict(),
        }

        if self._is_teacher:
            self._send_fn(PAINT, msg)
        else:
            self._send_fn(PAINT, msg)

    def send_erase(self, stroke_id: str) -> None:
        """Notify peers about an erased stroke."""
        if not self._send_fn:
            return
        self._send_fn(PAINT, {
            "type": MSG_ERASE,
            "stroke_id": stroke_id,
        })

    def send_clear(self, page_number: int) -> None:
        """Notify peers that a page was cleared."""
        if not self._send_fn:
            return
        self._send_fn(PAINT, {
            "type": MSG_CLEAR,
            "page_number": page_number,
        })

    # ------------------------------------------------------------------
    # Incoming message handler
    # ------------------------------------------------------------------

    def handle_message(self, channel: int, payload: Any) -> None:
        """Process an incoming P2P message on CONTENT or PAINT channel."""
        if channel == CONTENT and isinstance(payload, bytes):
            self._handle_pdf_chunk(payload)
        elif isinstance(payload, dict):
            msg_type = payload.get("type", "")
            if msg_type == MSG_PAGE_CHANGE:
                self._handle_page_change(payload)
            elif msg_type == MSG_STROKE:
                self._handle_stroke(payload)
            elif msg_type == MSG_ERASE:
                self._handle_erase(payload)
            elif msg_type == MSG_CLEAR:
                self._handle_clear(payload)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _send_pdf_to_students(self) -> None:
        """Send PDF data in chunks over the CONTENT channel."""
        if not self._pdf_data or not self._send_fn:
            return

        import uuid
        transfer_id = uuid.uuid4().hex[:8]
        total_chunks = (len(self._pdf_data) + _CHUNK_SIZE - 1) // _CHUNK_SIZE

        # Send metadata first
        self._send_fn(CONTROL, {
            "type": MSG_PDF_TRANSFER,
            "transfer_id": transfer_id,
            "total_chunks": total_chunks,
            "total_size": len(self._pdf_data),
            "page_count": self._total_pages,
        })

        # Send chunks
        for i in range(total_chunks):
            start = i * _CHUNK_SIZE
            end = min(start + _CHUNK_SIZE, len(self._pdf_data))
            chunk = self._pdf_data[start:end]
            # Prepend transfer header to each chunk
            header = f"{transfer_id}:{i}:{total_chunks}:".encode()
            self._send_fn(CONTENT, header + chunk)

        logger.info("Sent PDF (%d bytes, %d chunks)", len(self._pdf_data), total_chunks)

    def _handle_pdf_chunk(self, data: bytes) -> None:
        """Reassemble PDF from incoming chunks."""
        # Parse header: transfer_id:chunk_index:total_chunks:
        try:
            first_colon = data.index(b":")
            second_colon = data.index(b":", first_colon + 1)
            third_colon = data.index(b":", second_colon + 1)

            transfer_id = data[:first_colon].decode()
            chunk_index = int(data[first_colon + 1:second_colon].decode())
            total_chunks = int(data[second_colon + 1:third_colon].decode())
            chunk_data = data[third_colon + 1:]

            if transfer_id not in self._chunk_buffer:
                self._chunk_buffer[transfer_id] = [b""] * total_chunks

            self._chunk_buffer[transfer_id][chunk_index] = chunk_data

            # Check if all chunks received
            chunks = self._chunk_buffer[transfer_id]
            if all(c for c in chunks):
                self._pdf_data = b"".join(chunks)
                del self._chunk_buffer[transfer_id]

                import fitz
                doc = fitz.open(stream=self._pdf_data, filetype="pdf")
                self._total_pages = len(doc)
                doc.close()

                self._bus.publish(_SyncEvent("content.pdf_loaded", {
                    "page_count": self._total_pages,
                    "current_page": 0,
                }))
                logger.info("PDF received (%d bytes, %d pages)", len(self._pdf_data), self._total_pages)

        except (ValueError, IndexError) as exc:
            logger.warning("Failed to parse PDF chunk: %s", exc)

    def _handle_page_change(self, msg: dict) -> None:
        page = msg.get("page", 0)
        self._current_page = page
        self._bus.publish(_SyncEvent("content.page_changed", {"page": page}))

    def _handle_stroke(self, msg: dict) -> None:
        stroke_data = msg.get("stroke", {})
        stroke = Stroke.from_dict(stroke_data)
        self._bus.publish(_SyncEvent("content.remote_stroke", {"stroke": stroke}))

    def _handle_erase(self, msg: dict) -> None:
        self._bus.publish(_SyncEvent("content.remote_erase", {
            "stroke_id": msg.get("stroke_id", ""),
        }))

    def _handle_clear(self, msg: dict) -> None:
        self._bus.publish(_SyncEvent("content.remote_clear", {
            "page_number": msg.get("page_number", 0),
        }))


class _SyncEvent:
    __slots__ = ("topic", "data")

    def __init__(self, topic: str, data: dict) -> None:
        self.topic = topic
        self.data = data
