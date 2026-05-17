"""Unit tests for the scanner UI window."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from PySide6.QtWidgets import QLabel

from chenedusys.ai.scanner import ScanResult
from chenedusys.ui.windows.scanner import ScannerWindow, _numpy_to_pixmap


@pytest.fixture
def window(qtbot):
    w = ScannerWindow()
    qtbot.addWidget(w)
    return w


class TestScannerWindow:

    def test_initial_state(self, window):
        assert not window._scan_btn.isEnabled()
        assert not window._save_btn.isEnabled()
        assert window._current_result is None

    def test_numpy_to_pixmap_valid(self):
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        img[:, :, 1] = 128  # some green
        pixmap = _numpy_to_pixmap(img)
        assert not pixmap.isNull()
        assert pixmap.width() == 200
        assert pixmap.height() == 100

    def test_numpy_to_pixmap_none(self):
        pixmap = _numpy_to_pixmap(None)
        assert pixmap.isNull()

    def test_scan_button_enabled_after_load(self, window, tmp_path):
        img = np.ones((300, 400, 3), dtype=np.uint8) * 255
        cv2.rectangle(img, (20, 20), (380, 280), (0, 0, 0), 2)
        path = str(tmp_path / "test_doc.png")
        cv2.imwrite(path, img)

        window._source_path = path
        loaded = cv2.imread(path)
        window._display_image(window._orig_label, loaded)
        window._scan_btn.setEnabled(True)
        window._save_btn.setEnabled(False)

        assert window._scan_btn.isEnabled()
        assert not window._save_btn.isEnabled()

    def test_run_scan_produces_result(self, window, tmp_path):
        img = np.ones((300, 400, 3), dtype=np.uint8) * 255
        cv2.rectangle(img, (20, 20), (380, 280), (0, 0, 0), 2)
        path = str(tmp_path / "test_doc.png")
        cv2.imwrite(path, img)

        window._source_path = path
        window._run_scan()

        assert window._current_result is not None
        assert window._save_btn.isEnabled()

    def test_save_result(self, window, tmp_path):
        img = np.ones((300, 400, 3), dtype=np.uint8) * 255
        result = ScanResult(img)
        window._current_result = result

        out_path = str(tmp_path / "out.png")
        success = window._scanner.save(result, out_path)
        assert success

        loaded = cv2.imread(out_path)
        assert loaded is not None

    def test_display_image_sets_pixmap(self, window):
        img = np.zeros((200, 300, 3), dtype=np.uint8)
        window._display_image(window._orig_label, img)
        pix = window._orig_label.pixmap()
        assert pix is not None
        assert not pix.isNull()
