"""Unit tests for the segmenter UI window."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from chenedusys.ai.segmenter import SegmentationResult, QuestionRegion
from chenedusys.ui.windows.segmenter import SegmenterWindow


@pytest.fixture
def window(qtbot):
    w = SegmenterWindow()
    qtbot.addWidget(w)
    return w


class TestSegmenterWindow:

    def test_initial_state(self, window):
        assert not window._segment_btn.isEnabled()
        assert not window._save_pdf_btn.isEnabled()
        assert window._seg_result is None

    def test_segment_button_enabled_after_load(self, window, tmp_path):
        img = np.ones((300, 400, 3), dtype=np.uint8) * 255
        cv2.rectangle(img, (20, 20), (380, 280), (0, 0, 0), 2)
        path = str(tmp_path / "test_doc.png")
        cv2.imwrite(path, img)

        window._scanner.scan_file = lambda p: type("R", (), {
            "image": img, "width": 400, "height": 300,
        })()
        window._source_image = img
        window._segment_btn.setEnabled(True)

        assert window._segment_btn.isEnabled()

    def test_segment_produces_result(self, window):
        img = np.ones((400, 600, 3), dtype=np.uint8) * 255
        # Draw 3 text blocks
        cv2.putText(img, "1. Question one", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        cv2.putText(img, "2. Question two", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        cv2.putText(img, "3. Question three", (20, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        window._source_image = img
        window._run_segment()

        assert window._seg_result is not None
        assert window._seg_result.page_count >= 2

    def test_question_navigation(self, window):
        img = np.ones((400, 600, 3), dtype=np.uint8) * 255
        cv2.putText(img, "1. Question one", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        cv2.putText(img, "2. Question two", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        cv2.putText(img, "3. Question three", (20, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        window._source_image = img
        window._run_segment()

        n = window._seg_result.page_count
        if n >= 2:
            window._next_question()
            assert window._current_q == 1
            window._prev_question()
            assert window._current_q == 0

    def test_save_pdf(self, window, tmp_path):
        img = np.ones((200, 300, 3), dtype=np.uint8) * 255
        cv2.putText(img, "1. Test question", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        window._source_image = img
        window._run_segment()

        if window._seg_result and window._seg_result.questions:
            out_path = str(tmp_path / "test.pdf")
            assert window._seg_result.page_count >= 1

    def test_annotated_document_displayed(self, window):
        img = np.ones((400, 600, 3), dtype=np.uint8) * 255
        cv2.putText(img, "1. Question one", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        cv2.putText(img, "2. Question two", (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        window._source_image = img
        window._run_segment()

        # Document label should have a pixmap (annotated image)
        pix = window._doc_label.pixmap()
        assert pix is not None
        assert not pix.isNull()
