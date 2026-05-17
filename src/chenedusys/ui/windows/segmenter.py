"""Segmenter window — split scanned document into per-question PDF pages."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from chenedusys.ai.scanner import DocumentScanner
from chenedusys.ai.segmenter import QuestionSegmenter, SegmentationResult
from chenedusys.ai.question_pdf import questions_to_pdf

logger = logging.getLogger(__name__)


def _numpy_to_pixmap(img: np.ndarray) -> QPixmap:
    if img is None:
        return QPixmap()
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class SegmenterWindow(QWidget):
    """Window for segmenting a scanned document into per-question pages."""

    pdf_saved = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scanner = DocumentScanner()
        self._segmenter = QuestionSegmenter()
        self._source_image: np.ndarray | None = None
        self._scan_result = None
        self._seg_result: SegmentationResult | None = None

        self.setWindowTitle("ChenEduSys — Question Segmenter")
        self.setMinimumSize(1000, 650)
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

        self._segment_btn = QPushButton("Segment")
        self._segment_btn.setFixedWidth(80)
        self._segment_btn.setEnabled(False)
        self._segment_btn.clicked.connect(self._run_segment)
        toolbar.addWidget(self._segment_btn)

        self._save_pdf_btn = QPushButton("Save PDF")
        self._save_pdf_btn.setFixedWidth(80)
        self._save_pdf_btn.setEnabled(False)
        self._save_pdf_btn.clicked.connect(self._save_pdf)
        toolbar.addWidget(self._save_pdf_btn)

        toolbar.addStretch()

        self._status = QLabel("Open a scanned document to begin")
        self._status.setStyleSheet("color: gray; font-size: 12px;")
        toolbar.addWidget(self._status)

        layout.addLayout(toolbar)

        # Preview area: document with bounding boxes on left, question list on right
        preview = QHBoxLayout()

        # Document preview
        self._doc_label = QLabel("No document loaded")
        self._doc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._doc_label.setMinimumSize(600, 500)
        self._doc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._doc_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5;")
        preview.addWidget(self._doc_label, stretch=3)

        # Question list
        right_col = QVBoxLayout()
        right_col.addWidget(self._make_label("Detected Questions"))

        self._q_count_label = QLabel("Questions: -")
        self._q_count_label.setStyleSheet("font-size: 12px; color: gray;")
        right_col.addWidget(self._q_count_label)

        self._q_preview_label = QLabel()
        self._q_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._q_preview_label.setMinimumSize(250, 350)
        self._q_preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._q_preview_label.setStyleSheet("border: 1px solid #ddd; background: #fafafa;")
        right_col.addWidget(self._q_preview_label, stretch=1)

        # Navigation
        nav = QHBoxLayout()
        self._prev_q_btn = QPushButton("<")
        self._prev_q_btn.setFixedWidth(30)
        self._prev_q_btn.clicked.connect(self._prev_question)
        nav.addWidget(self._prev_q_btn)

        self._q_nav_label = QLabel("- / -")
        self._q_nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self._q_nav_label)

        self._next_q_btn = QPushButton(">")
        self._next_q_btn.setFixedWidth(30)
        self._next_q_btn.clicked.connect(self._next_question)
        nav.addWidget(self._next_q_btn)

        right_col.addLayout(nav)
        preview.addLayout(right_col, stretch=1)

        layout.addLayout(preview, stretch=1)

        self._current_q = 0

    @staticmethod
    def _make_label(text: str) -> QLabel:
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

        # Scan the photo first
        scan = self._scanner.scan_file(path)
        if scan is None:
            self._status.setText("Failed to scan image")
            self._status.setStyleSheet("color: red; font-size: 12px;")
            return

        self._source_image = scan.image
        self._seg_result = None
        self._save_pdf_btn.setEnabled(False)
        self._segment_btn.setEnabled(True)

        self._display_image(self._doc_label, self._source_image)
        self._q_preview_label.clear()
        self._q_preview_label.setText("Click Segment")
        self._q_count_label.setText("Questions: -")
        self._status.setText(f"Scanned: {Path(path).name} ({scan.width}x{scan.height})")
        self._status.setStyleSheet("color: green; font-size: 12px;")

    def _run_segment(self) -> None:
        if self._source_image is None:
            return
        self._status.setText("Segmenting...")
        self._status.setStyleSheet("color: orange; font-size: 12px;")

        self._seg_result = self._segmenter.segment(self._source_image)
        n = self._seg_result.page_count

        if n == 0:
            self._status.setText("No questions detected")
            self._status.setStyleSheet("color: red; font-size: 12px;")
            return

        self._current_q = 0
        self._save_pdf_btn.setEnabled(True)
        self._q_count_label.setText(f"Questions: {n}")
        self._show_document_with_boxes()
        self._show_current_question()
        self._status.setText(f"Found {n} question(s)")
        self._status.setStyleSheet("color: green; font-size: 12px;")

    def _save_pdf(self) -> None:
        if self._seg_result is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Question PDF", "questions.pdf",
            "PDF (*.pdf);;All Files (*)",
        )
        if not path:
            return

        if questions_to_pdf(self._seg_result, path):
            self._status.setText(f"Saved: {path}")
            self._status.setStyleSheet("color: green; font-size: 12px;")
            self.pdf_saved.emit(path)
        else:
            self._status.setText("Save failed")
            self._status.setStyleSheet("color: red; font-size: 12px;")

    def _prev_question(self) -> None:
        if self._seg_result and self._current_q > 0:
            self._current_q -= 1
            self._show_current_question()

    def _next_question(self) -> None:
        if self._seg_result and self._current_q < self._seg_result.page_count - 1:
            self._current_q += 1
            self._show_current_question()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _display_image(self, label: QLabel, img: np.ndarray) -> None:
        pixmap = _numpy_to_pixmap(img)
        if pixmap.isNull():
            return
        self._set_scaled(label, pixmap)

    def _set_scaled(self, label: QLabel, pixmap: QPixmap) -> None:
        size = label.size()
        scaled = pixmap.scaled(
            size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)

    def _show_document_with_boxes(self) -> None:
        """Show the scanned document with question bounding boxes drawn."""
        if self._source_image is None or self._seg_result is None:
            return

        annotated = self._source_image.copy()
        colors = [
            (0, 120, 255), (0, 200, 0), (200, 0, 200),
            (200, 200, 0), (0, 200, 200), (200, 100, 0),
        ]

        for i, q in enumerate(self._seg_result.questions):
            x, y, w, h = q.bbox
            color = colors[i % len(colors)]
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            cv2.putText(annotated, f"Q{i + 1}", (x + 5, y + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        self._display_image(self._doc_label, annotated)

    def _show_current_question(self) -> None:
        if not self._seg_result or not self._seg_result.questions:
            return
        q = self._seg_result.questions[self._current_q]
        self._display_image(self._q_preview_label, q.image)
        self._q_nav_label.setText(f"{self._current_q + 1} / {self._seg_result.page_count}")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._source_image is not None:
            if self._seg_result:
                self._show_document_with_boxes()
            else:
                self._display_image(self._doc_label, self._source_image)
        if self._seg_result and self._seg_result.questions:
            self._show_current_question()
