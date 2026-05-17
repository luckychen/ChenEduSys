"""Edge-case tests for content sync and PDF handling."""

from __future__ import annotations

import pytest

from chenedusys.core.event_bus import EventBus
from chenedusys.core.models import Point, Stroke
from chenedusys.services.content_sync import ContentSync
from chenedusys.transport.protocol import CONTENT, CONTROL, PAINT


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def sync(bus):
    return ContentSync(bus)


def _make_pdf(pages=1):
    import fitz
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=200, height=200)
        page.insert_text((10, 50), f"Page {i}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestPdfEdgeCases:

    def test_single_page_pdf(self, sync, bus, tmp_path):
        import fitz
        doc = fitz.open()
        doc.new_page(width=100, height=100)  # blank page
        path = str(tmp_path / "single.pdf")
        doc.save(path)
        doc.close()

        result = sync.load_pdf(path)
        assert result is True
        assert sync.total_pages == 1

    def test_large_pdf(self, sync, bus, tmp_path):
        import fitz
        doc = fitz.open()
        for i in range(50):
            page = doc.new_page()
            page.insert_text((10, 50), f"Page {i}" * 100)
        path = str(tmp_path / "large.pdf")
        doc.save(path)
        doc.close()

        result = sync.load_pdf(path)
        assert result is True
        assert sync.total_pages == 50

    def test_invalid_pdf_data(self, sync):
        # Should not crash on garbage data
        sync._handle_pdf_chunk(b"not valid chunk data")
        # Should gracefully handle

    def test_chunk_reassembly_out_of_order(self, sync, bus):
        events = []
        bus.subscribe("content.pdf_loaded", lambda e: events.append(e))

        pdf_bytes = _make_pdf(1)
        chunk_size = 32
        total_chunks = (len(pdf_bytes) + chunk_size - 1) // chunk_size
        transfer_id = "ooo_test"

        # Send chunks in reverse order
        for i in range(total_chunks - 1, -1, -1):
            start = i * chunk_size
            end = min(start + chunk_size, len(pdf_bytes))
            header = f"{transfer_id}:{i}:{total_chunks}:".encode()
            sync.handle_message(CONTENT, header + pdf_bytes[start:end])

        assert len(events) == 1
        assert sync.pdf_data == pdf_bytes


class TestContentSyncEdgeCases:

    def test_page_change_out_of_range(self, sync):
        sync._pdf_data = b"fake"
        sync._total_pages = 5
        sync.change_page(10)  # should not change
        assert sync.current_page == 0
        sync.change_page(-1)
        assert sync.current_page == 0

    def test_page_change_no_pdf(self, sync):
        sync.change_page(0)  # should not crash

    def test_malformed_chunk_header(self, sync):
        # No colons
        sync.handle_message(CONTENT, b"justgarbagedata")
        # Should not crash

    def test_single_chunk_pdf(self, sync, bus):
        events = []
        bus.subscribe("content.pdf_loaded", lambda e: events.append(e))

        pdf_bytes = _make_pdf(1)
        header = f"single:0:1:".encode()
        sync.handle_message(CONTENT, header + pdf_bytes)

        assert len(events) == 1
        assert sync.pdf_data == pdf_bytes

    def test_send_stroke_with_many_points(self, sync):
        sent = []
        sync.set_send_function(lambda ch, payload: sent.append((ch, payload)))

        points = tuple(Point(x=i * 0.5, y=i * 1.5) for i in range(100))
        stroke = Stroke(points=points, color="#000000", width=1.0)
        sync.send_stroke(stroke)

        assert len(sent) == 1
        assert len(sent[0][1]["stroke"]["points"]) == 100

    def test_rapid_page_changes(self, sync, bus):
        sync._pdf_data = _make_pdf(10)
        sync._total_pages = 10
        sent = []
        sync.set_send_function(lambda ch, payload: sent.append((ch, payload)))
        sync.set_role(True)

        for i in range(10):
            sync.change_page(i)

        assert sync.current_page == 9
        assert len(sent) == 10
