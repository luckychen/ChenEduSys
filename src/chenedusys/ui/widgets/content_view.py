"""Content view — combines PDF background with paint overlay."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from chenedusys.core.models import Stroke
from chenedusys.services.paint_engine import PaintEngine

logger = logging.getLogger(__name__)


class ContentView(QWidget):
    """Widget that renders a PDF page as background with paint strokes on top.

    Input handling:
    - Ctrl + move = draw (pen mode)
    - Shift + move = erase
    - Two-finger touch = pan viewport

    All paint coordinates are in canvas space; the PDF page is rendered
    as a fixed background layer.
    """

    page_change_requested = Signal(int)
    stroke_finished = Signal(object)  # Stroke object

    def __init__(
        self,
        paint_engine: PaintEngine,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._engine = paint_engine
        self._pdf_pixmap = None  # QPixmap for current page background
        self._pen_active = False
        self._eraser_active = False
        self._mode = "pen"  # "pen" or "eraser"

        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet("background-color: white;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value in ("pen", "eraser"):
            self._mode = value

    def set_pdf_background(self, pixmap) -> None:
        """Set the PDF page as background image."""
        self._pdf_pixmap = pixmap
        self.update()

    def clear_pdf_background(self) -> None:
        self._pdf_pixmap = None
        self.update()

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:
        modifiers = event.modifiers()
        cx, cy = self._engine.screen_to_canvas(event.position().x(), event.position().y())

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if not self._pen_active:
                self._pen_active = True
                self._engine.begin_stroke()
            self._engine.add_point(cx, cy)
            self.update()

        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            if self._mode == "eraser" or modifiers & Qt.KeyboardModifier.ShiftModifier:
                self._engine.erase_at(cx, cy, radius=15)
                self.update()

        # Update cursor for eraser
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            from PySide6.QtGui import QCursor
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._pen_active:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Control and self._pen_active:
            self._pen_active = False
            stroke = self._engine.end_stroke()
            if stroke:
                self.stroke_finished.emit(stroke)
            self.update()
        super().keyReleaseEvent(event)

    def touchEvent(self, event) -> None:
        points = event.points()
        if len(points) >= 2:
            # Two-finger pan
            p1 = points[0].position()
            p2 = points[1].position()
            cx = (p1.x() + p2.x()) / 2
            cy = (p1.y() + p2.y()) / 2
            if hasattr(self, "_last_touch_center"):
                dx = cx - self._last_touch_center[0]
                dy = cy - self._last_touch_center[1]
                self._engine.pan(dx, dy)
                self.update()
            self._last_touch_center = (cx, cy)
        event.accept()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # White background
        painter.fillRect(self.rect(), QBrush(QColor("white")))

        # PDF page background
        if self._pdf_pixmap:
            ox, oy = self._engine.offset
            painter.drawPixmap(int(-ox), int(-oy), self._pdf_pixmap)

        # Paint strokes
        viewport = (self._engine.offset[0], self._engine.offset[1],
                    self.width(), self.height())
        strokes = self._engine.get_strokes_in_viewport(*viewport)
        for stroke in strokes:
            self._draw_stroke(painter, stroke)

        # Current in-progress stroke
        if self._pen_active and self._engine._current_stroke_points:
            current = Stroke(
                points=tuple(self._engine._current_stroke_points),
                color=self._engine._current_color,
                width=self._engine._current_width,
                page_number=self._engine.page_number,
            )
            self._draw_stroke(painter, current)

        # Eraser cursor indicator
        if self._eraser_active:
            painter.setPen(QPen(QColor(255, 0, 0, 120), 1))
            painter.setBrush(QBrush(QColor(255, 0, 0, 40)))
            from PySide6.QtGui import QCursor
            pos = self.mapFromGlobal(QCursor.pos())
            painter.drawEllipse(pos, 15, 15)

        painter.end()

    def _draw_stroke(self, painter: QPainter, stroke: Stroke) -> None:
        if len(stroke.points) < 2:
            if len(stroke.points) == 1:
                ox, oy = self._engine.offset
                p = stroke.points[0]
                painter.setPen(QPen(QColor(stroke.color), stroke.width))
                painter.drawPoint(int(p.x - ox), int(p.y - oy))
            return

        ox, oy = self._engine.offset
        pen = QPen(QColor(stroke.color), stroke.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        from PySide6.QtCore import QPointF
        points = [QPointF(p.x - ox, p.y - oy) for p in stroke.points]
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])
