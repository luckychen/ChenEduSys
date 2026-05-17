"""Unit tests for content sync service."""

from __future__ import annotations

import pytest

from chenedusys.core.event_bus import EventBus
from chenedusys.core.models import Point, Stroke
from chenedusys.services.content_sync import (
    ContentSync,
    MSG_CLEAR,
    MSG_ERASE,
    MSG_PAGE_CHANGE,
    MSG_PDF_TRANSFER,
    MSG_STROKE,
)
from chenedusys.transport.protocol import CONTENT, CONTROL, PAINT


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def sync(bus):
    return ContentSync(bus)


class TestContentSyncInit:

    def test_initial_state(self, sync):
        assert sync.current_page == 0
        assert sync.total_pages == 0
        assert not sync.has_pdf
        assert sync.pdf_data is None

    def test_set_role(self, sync):
        sync.set_role(True)
        assert sync._is_teacher


class TestContentSyncMessages:

    def test_page_change_message(self, sync, bus):
        events = []
        bus.subscribe("content.page_changed", lambda e: events.append(e))
        sync.handle_message(CONTROL, {"type": MSG_PAGE_CHANGE, "page": 3})
        assert sync.current_page == 3
        assert len(events) == 1
        assert events[0].data["page"] == 3

    def test_stroke_message(self, sync, bus):
        events = []
        bus.subscribe("content.remote_stroke", lambda e: events.append(e))

        stroke_dict = Stroke(
            points=(Point(x=10, y=20), Point(x=30, y=40)),
            color="#ff0000",
            width=3.0,
            page_number=0,
        ).to_dict()

        sync.handle_message(PAINT, {"type": MSG_STROKE, "stroke": stroke_dict})
        assert len(events) == 1
        received = events[0].data["stroke"]
        assert isinstance(received, Stroke)
        assert received.color == "#ff0000"
        assert len(received.points) == 2

    def test_erase_message(self, sync, bus):
        events = []
        bus.subscribe("content.remote_erase", lambda e: events.append(e))
        sync.handle_message(PAINT, {"type": MSG_ERASE, "stroke_id": "abc123"})
        assert len(events) == 1
        assert events[0].data["stroke_id"] == "abc123"

    def test_clear_message(self, sync, bus):
        events = []
        bus.subscribe("content.remote_clear", lambda e: events.append(e))
        sync.handle_message(PAINT, {"type": MSG_CLEAR, "page_number": 2})
        assert len(events) == 1
        assert events[0].data["page_number"] == 2

    def test_unknown_message_type_ignored(self, sync):
        sync.handle_message(CONTROL, {"type": "unknown"})
        # Should not raise

    def test_pdf_chunk_reassembly(self, sync, bus):
        events = []
        bus.subscribe("content.pdf_loaded", lambda e: events.append(e))

        # Create a minimal valid PDF
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((10, 50), "Test PDF")
        pdf_bytes = doc.tobytes()
        doc.close()

        # Simulate chunked transfer
        chunk_size = 64
        total_chunks = (len(pdf_bytes) + chunk_size - 1) // chunk_size
        transfer_id = "test123"

        # First, send the metadata (would come via CONTROL)
        # Then send chunks via CONTENT
        for i in range(total_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, len(pdf_bytes))
            header = f"{transfer_id}:{i}:{total_chunks}:".encode()
            chunk = header + pdf_bytes[start:end]
            sync.handle_message(CONTENT, chunk)

        assert len(events) == 1
        assert sync.has_pdf
        assert sync.total_pages == 1
        assert sync.pdf_data == pdf_bytes


class TestContentSyncSend:

    def test_send_stroke(self, sync):
        sent = []
        sync.set_send_function(lambda ch, payload: sent.append((ch, payload)))

        stroke = Stroke(
            points=(Point(x=1, y=2),),
            color="#000000",
            width=2.0,
        )
        sync.send_stroke(stroke)
        assert len(sent) == 1
        assert sent[0][0] == PAINT
        assert sent[0][1]["type"] == MSG_STROKE
        assert sent[0][1]["stroke"]["points"][0]["x"] == 1

    def test_send_erase(self, sync):
        sent = []
        sync.set_send_function(lambda ch, payload: sent.append((ch, payload)))
        sync.send_erase("stroke_abc")
        assert len(sent) == 1
        assert sent[0][1]["stroke_id"] == "stroke_abc"

    def test_send_clear(self, sync):
        sent = []
        sync.set_send_function(lambda ch, payload: sent.append((ch, payload)))
        sync.send_clear(0)
        assert len(sent) == 1
        assert sent[0][1]["page_number"] == 0

    def test_send_without_function_is_noop(self, sync):
        stroke = Stroke(points=(Point(x=1, y=2),))
        sync.send_stroke(stroke)  # should not raise

    def test_change_page_sends_to_peers(self, sync):
        import fitz
        doc = fitz.open()
        doc.new_page()
        doc.new_page()
        pdf_bytes = doc.tobytes()
        doc.close()

        sync._pdf_data = pdf_bytes
        sync._total_pages = 2

        sent = []
        sync.set_send_function(lambda ch, payload: sent.append((ch, payload)))
        sync.set_role(True)
        sync.change_page(1)
        assert len(sent) == 1
        assert sent[0][1]["page"] == 1


class TestPdfLoad:

    def test_load_pdf_file(self, sync, bus, tmp_path):
        events = []
        bus.subscribe("content.pdf_loaded", lambda e: events.append(e))

        import fitz
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 72), f"Page {i + 1}")
        path = str(tmp_path / "test.pdf")
        doc.save(path)
        doc.close()

        result = sync.load_pdf(path)
        assert result is True
        assert sync.has_pdf
        assert sync.total_pages == 3
        assert sync.current_page == 0
        assert len(events) == 1
        assert events[0].data["page_count"] == 3

    def test_load_nonexistent_file(self, sync):
        result = sync.load_pdf("/nonexistent/file.pdf")
        assert result is False
        assert not sync.has_pdf
