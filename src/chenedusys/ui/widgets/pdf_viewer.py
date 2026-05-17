"""PDF viewer widget — renders PDF pages as QImage using PyMuPDF."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

logger = logging.getLogger(__name__)

_DEFAULT_DPI = 150


class PdfViewer(QGraphicsView):
    """Displays a PDF document page with zoom and page navigation."""

    page_changed = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._doc = None  # fitz.Document
        self._current_page = 0
        self._page_count = 0
        self._dpi = _DEFAULT_DPI
        self._zoom = 1.0

        self.setRenderHint(self.RenderHint.Antialiasing)
        self.setRenderHint(self.RenderHint.SmoothPixmapTransform)
        self.setDragMode(self.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("background-color: #525252;")

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def current_page(self) -> int:
        return self._current_page

    def load_file(self, path: str) -> bool:
        """Load a PDF file. Returns True on success."""
        import fitz

        try:
            self._doc = fitz.open(path)
        except Exception as exc:
            logger.error("Failed to open PDF %s: %s", path, exc)
            return False

        self._page_count = len(self._doc)
        self._current_page = 0
        self._render_page(0)
        return True

    def load_bytes(self, data: bytes) -> bool:
        """Load a PDF from raw bytes. Returns True on success."""
        import fitz

        try:
            self._doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            logger.error("Failed to open PDF from bytes: %s", exc)
            return False

        self._page_count = len(self._doc)
        self._current_page = 0
        self._render_page(0)
        return True

    def set_page(self, page_num: int) -> None:
        """Go to a specific page (0-indexed)."""
        if self._doc is None or page_num < 0 or page_num >= self._page_count:
            return
        if page_num == self._current_page:
            return
        self._current_page = page_num
        self._render_page(page_num)
        self.page_changed.emit(page_num)

    def next_page(self) -> None:
        self.set_page(self._current_page + 1)

    def prev_page(self) -> None:
        self.set_page(self._current_page - 1)

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.25, min(4.0, zoom))
        if self._doc:
            self._render_page(self._current_page)

    def get_page_bytes(self, page_num: int, dpi: int = 150) -> bytes | None:
        """Render a page to PNG bytes. Used for sending to peers."""
        if self._doc is None:
            return None
        try:
            page = self._doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            return pix.tobytes("png")
        except Exception as exc:
            logger.warning("Failed to render page %d: %s", page_num, exc)
            return None

    def fit_to_view(self) -> None:
        """Scale the page to fit the viewport."""
        if self._pixmap_item and self._pixmap_item.pixmap():
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _render_page(self, page_num: int) -> None:
        if self._doc is None:
            return
        try:
            page = self._doc[page_num]
            mat = page.get_pixmap(dpi=self._dpi)
            img = QImage(
                mat.samples,
                mat.width,
                mat.height,
                mat.stride,
                QImage.Format.Format_RGB888,
            )
            pixmap = QPixmap.fromImage(img)

            self._scene.clear()
            self._pixmap_item = self._scene.addPixmap(pixmap)
            self._scene.setSceneRect(self._pixmap_item.boundingRect())
            self.fit_to_view()
        except Exception as exc:
            logger.error("Render page %d failed: %s", page_num, exc)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_to_view()

    def close_document(self) -> None:
        if self._doc:
            self._doc.close()
        self._doc = None
        self._page_count = 0
        self._current_page = 0
        self._scene.clear()
        self._pixmap_item = None
