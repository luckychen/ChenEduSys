"""Touchpad drawing canvas widget.

Input model (designed for laptop touchpad):
  - **Ctrl held + mouse/touchpad move**  = draw (pen mode)
  - **Shift held + mouse/touchpad move**  = erase
  - **2-finger touchpad**                 = pan the viewport
  - **ESC**                               = stop current draw/erase action
  - No modifier + mouse move              = nothing (cursor only)

The canvas area is rendered with a dashed border and transparent
background. Touchpad/mouse position maps directly to canvas position.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QPen,
    QTouchEvent,
    QPainter,
    QColor,
    QMouseEvent,
)
from PySide6.QtWidgets import QWidget

from chenedusys.core.event_bus import EventBus
from chenedusys.core.events import PaintModeChange
from chenedusys.services.paint_engine import PaintEngine


class PaintCanvas(QWidget):
    """Widget that renders strokes and captures Ctrl/Shift + mouse input."""

    def __init__(
        self,
        engine: PaintEngine,
        bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.bus = bus

        self._active_mode: str = "none"  # "none" | "pen" | "eraser"
        self._drawing = False
        self._panning = False
        self._last_pan_pos: QPointF | None = None

        # Pen defaults
        self._pen_color = "#000000"
        self._pen_width = 2.0

        # Eraser
        self._eraser_radius = 10.0

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents, True)
        self.setAutoFillBackground(False)
        self.setMinimumSize(200, 200)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._active_mode

    # ------------------------------------------------------------------
    # Rendering — transparent background, dashed border, strokes
    # ------------------------------------------------------------------

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ox, oy = self.engine.offset

        # No background fill — fully transparent so content behind shows through

        # Render stored strokes
        for stroke in self.engine.strokes:
            self._render_stroke(painter, stroke, ox, oy)

        # Render in-progress stroke
        if self._drawing and self.engine._current_stroke_points:
            pts = self.engine._current_stroke_points
            if len(pts) >= 1:
                qpen = QPen(QColor(self._pen_color), self._pen_width)
                qpen.setCapStyle(Qt.PenCapStyle.RoundCap)
                qpen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(qpen)
                if len(pts) == 1:
                    p = pts[0]
                    painter.drawPoint(QPointF(p.x - ox, p.y - oy))
                else:
                    for i in range(len(pts) - 1):
                        p1, p2 = pts[i], pts[i + 1]
                        painter.drawLine(
                            QPointF(p1.x - ox, p1.y - oy),
                            QPointF(p2.x - ox, p2.y - oy),
                        )

        # Eraser cursor indicator
        if self._active_mode == "eraser":
            painter.setPen(QPen(QColor("#FF4444"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                self._last_mouse_pos,
                self._eraser_radius,
                self._eraser_radius,
            )

        painter.end()

    def _render_stroke(self, painter: QPainter, stroke, ox: float, oy: float) -> None:
        if not stroke.points:
            return
        qpen = QPen(QColor(stroke.color), stroke.width)
        qpen.setCapStyle(Qt.PenCapStyle.RoundCap)
        qpen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(qpen)

        pts = stroke.points
        if len(pts) == 1:
            p = pts[0]
            painter.drawPoint(QPointF(p.x - ox, p.y - oy))
            return

        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            painter.drawLine(
                QPointF(p1.x - ox, p1.y - oy),
                QPointF(p2.x - ox, p2.y - oy),
            )

    # ------------------------------------------------------------------
    # Determine active mode from keyboard modifiers
    # ------------------------------------------------------------------

    def _mode_from_modifiers(self, modifiers: Qt.KeyboardModifier) -> str:
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            return "pen"
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            return "eraser"
        return "none"

    def _update_mode(self, modifiers: Qt.KeyboardModifier) -> None:
        new_mode = self._mode_from_modifiers(modifiers)
        if new_mode != self._active_mode:
            # Finish current stroke if switching away from pen
            if self._drawing:
                self.engine.end_stroke()
                self._drawing = False
            self._active_mode = new_mode
            self.bus.publish(PaintModeChange(mode=new_mode))
            self.update()

    # ------------------------------------------------------------------
    # Mouse events — Ctrl=draw, Shift=erase, plain=nothing
    # ------------------------------------------------------------------

    _last_mouse_pos: QPointF = QPointF()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.engine.is_active:
            return
        pos = event.position()
        self._last_mouse_pos = pos
        self._update_mode(event.modifiers())

        if self._active_mode == "pen":
            if not self._drawing:
                # Start a new stroke on first Ctrl+move
                cx, cy = self.engine.screen_to_canvas(pos.x(), pos.y())
                self.engine.begin_stroke(self._pen_color, self._pen_width)
                self.engine.add_point(cx, cy)
                self._drawing = True
            else:
                cx, cy = self.engine.screen_to_canvas(pos.x(), pos.y())
                self.engine.add_point(cx, cy)
            self.update()

        elif self._active_mode == "eraser":
            cx, cy = self.engine.screen_to_canvas(pos.x(), pos.y())
            self.engine.erase_at(cx, cy, self._eraser_radius)
            self.update()

    # mousePressEvent / mouseReleaseEvent kept for compatibility
    # but drawing is driven entirely by Ctrl+move

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pass

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pass

    # ------------------------------------------------------------------
    # Touch events — 2-finger = pan
    # ------------------------------------------------------------------

    def event(self, event):
        if isinstance(event, QTouchEvent):
            return self._handle_touch(event)
        return super().event(event)

    def _handle_touch(self, event: QTouchEvent) -> bool:
        if not self.engine.is_active:
            event.ignore()
            return False

        points = event.points()

        if len(points) >= 2:
            # Cancel any in-progress draw
            if self._drawing:
                self.engine.end_stroke()
                self._drawing = False

            if event.type() in (QTouchEvent.Type.TouchBegin, QTouchEvent.Type.TouchUpdate):
                if not self._panning:
                    self._panning = True
                    self._last_pan_pos = points[0].position()
                else:
                    cur = points[0].position()
                    if self._last_pan_pos is not None:
                        dx = cur.x() - self._last_pan_pos.x()
                        dy = cur.y() - self._last_pan_pos.y()
                        self.engine.pan(dx, dy)
                        self.update()
                    self._last_pan_pos = cur

            elif event.type() == QTouchEvent.Type.TouchEnd:
                self._panning = False
                self._last_pan_pos = None

        event.accept()
        return True

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # ESC is not handled here — let it propagate to the parent window
        # so it can be used as a global quit/cancel shortcut.
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        # When Ctrl/Shift is released, end any in-progress action
        if not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
            if self._drawing:
                self.engine.end_stroke()
                self._drawing = False
            self._active_mode = "none"
            self.update()
        else:
            super().keyReleaseEvent(event)
