"""Scanner window — load a document photo and convert to a clean scanned image."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from chenedusys.ai.scanner import DocumentScanner, ScanResult

logger = logging.getLogger(__name__)


def _numpy_to_pixmap(img: np.ndarray) -> QPixmap:
    """Convert an OpenCV BGR image to a QPixmap."""
    if img is None:
        return QPixmap()
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class ScannerWindow(QWidget):
    """Window for scanning document photos into clean PNGs."""

    scan_saved = Signal(str)  # emits saved file path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scanner = DocumentScanner()
        self._current_result: ScanResult | None = None
        self._source_path: str | None = None

        self.setWindowTitle("ChenEduSys — Document Scanner")
        self.setMinimumSize(900, 600)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()

        self._open_btn = QPushButton("Open Photo")
        self._open_btn.setFixedWidth(100)
        self._open_btn.clicked.connect(self._open_photo)
        toolbar.addWidget(self._open_btn)

        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setFixedWidth(70)
        self._scan_btn.setEnabled(False)
        self._scan_btn.clicked.connect(self._run_scan)
        toolbar.addWidget(self._scan_btn)

        self._save_btn = QPushButton("Save PNG")
        self._save_btn.setFixedWidth(80)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_result)
        toolbar.addWidget(self._save_btn)

        toolbar.addStretch()

        self._status = QLabel("Open a document photo to begin")
        self._status.setStyleSheet("color: gray; font-size: 12px;")
        toolbar.addWidget(self._status)

        layout.addLayout(toolbar)

        # Image panels side by side
        panels = QHBoxLayout()

        # Original
        orig_col = QVBoxLayout()
        orig_col.addWidget(self._make_panel_label("Original"))
        self._orig_label = QLabel("No image loaded")
        self._orig_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._orig_label.setMinimumSize(400, 400)
        self._orig_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._orig_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5;")
        orig_col.addWidget(self._orig_label)
        panels.addLayout(orig_col, stretch=1)

        # Scanned
        scan_col = QVBoxLayout()
        scan_col.addWidget(self._make_panel_label("Scanned"))
        self._scan_label = QLabel("No scan yet")
        self._scan_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scan_label.setMinimumSize(400, 400)
        self._scan_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._scan_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5;")
        scan_col.addWidget(self._scan_label)
        panels.addLayout(scan_col, stretch=1)

        layout.addLayout(panels, stretch=1)

    @staticmethod
    def _make_panel_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold; font-size: 13px;")
        return label

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Document Photo", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff);;All Files (*)",
        )
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            self._status.setText("Failed to load image")
            self._status.setStyleSheet("color: red; font-size: 12px;")
            return

        self._source_path = path
        self._current_result = None
        self._save_btn.setEnabled(False)
        self._scan_btn.setEnabled(True)

        self._display_image(self._orig_label, img)
        self._scan_label.clear()
        self._scan_label.setText("Click Scan")
        self._status.setText(f"Loaded: {Path(path).name} ({img.shape[1]}x{img.shape[0]})")
        self._status.setStyleSheet("color: gray; font-size: 12px;")

    def _run_scan(self) -> None:
        if not self._source_path:
            return
        self._status.setText("Scanning...")
        self._status.setStyleSheet("color: orange; font-size: 12px;")

        result = self._scanner.scan_file(self._source_path)
        if result is None:
            self._status.setText("Scan failed — no document detected")
            self._status.setStyleSheet("color: red; font-size: 12px;")
            return

        self._current_result = result
        self._save_btn.setEnabled(True)
        self._display_image(self._scan_label, result.image)
        self._status.setText(
            f"Scan complete: {result.width}x{result.height}"
        )
        self._status.setStyleSheet("color: green; font-size: 12px;")

    def _save_result(self) -> None:
        if self._current_result is None:
            return

        default_name = "scan.png"
        if self._source_path:
            stem = Path(self._source_path).stem
            default_name = f"{stem}_scan.png"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Scanned Image", default_name,
            "PNG (*.png);;All Files (*)",
        )
        if not path:
            return

        if self._scanner.save(self._current_result, path):
            self._status.setText(f"Saved: {path}")
            self._status.setStyleSheet("color: green; font-size: 12px;")
            self.scan_saved.emit(path)
        else:
            self._status.setText("Save failed")
            self._status.setStyleSheet("color: red; font-size: 12px;")

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _display_image(self, label: QLabel, img: np.ndarray) -> None:
        pixmap = _numpy_to_pixmap(img)
        if pixmap.isNull():
            return
        self._set_scaled_pixmap(label, pixmap)

    def _set_scaled_pixmap(self, label: QLabel, pixmap: QPixmap) -> None:
        size = label.size()
        scaled = pixmap.scaled(
            size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        """Re-scale images when window resizes."""
        super().resizeEvent(event)
        for label in (self._orig_label, self._scan_label):
            pix = label.pixmap()
            if pix and not pix.isNull():
                self._set_scaled_pixmap(label, pix)
