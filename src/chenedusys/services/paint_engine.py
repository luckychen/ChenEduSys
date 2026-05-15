"""Paint engine: stroke storage, undo, erase, viewport, and canvas state.

The PaintEngine owns the *model* — it knows nothing about Qt widgets.
The UI layer calls PaintEngine methods and renders whatever the engine
reports.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from chenedusys.core.event_bus import EventBus
from chenedusys.core.models import Point, Stroke

logger = logging.getLogger(__name__)


class PaintEngine:
    """Stateful canvas model backed by an ordered list of strokes.

    Coordinates are in *canvas space* (independent of viewport). The
    viewport is a rectangular window into that infinite canvas — panning
    shifts the viewport without moving any stroke.
    """

    def __init__(self, bus: EventBus, page_number: int = 0) -> None:
        self._bus = bus
        self._strokes: list[Stroke] = []
        self._page_number = page_number
        # Viewport offset (canvas-space origin visible at top-left of widget)
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0
        self._active = True
        self._current_stroke_points: list[Point] = []
        self._current_color: str = "#000000"
        self._current_width: float = 2.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def strokes(self) -> tuple[Stroke, ...]:
        return tuple(self._strokes)

    @property
    def stroke_count(self) -> int:
        return len(self._strokes)

    @property
    def offset(self) -> tuple[float, float]:
        return (self._offset_x, self._offset_y)

    @offset.setter
    def offset(self, value: tuple[float, float]) -> None:
        self._offset_x, self._offset_y = value

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def page_number(self) -> int:
        return self._page_number

    @page_number.setter
    def page_number(self, value: int) -> None:
        self._page_number = value

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def begin_stroke(self, color: str = "#000000", width: float = 2.0) -> None:
        if not self._active:
            return
        self._current_stroke_points = []
        self._current_color = color
        self._current_width = width

    def add_point(self, x: float, y: float) -> None:
        """Add a point in *canvas space* to the current stroke."""
        if not self._active:
            return
        self._current_stroke_points.append(Point(x=x, y=y))

    def end_stroke(self) -> Stroke | None:
        """Finish the current stroke, store it, fire event. Returns the stroke or None."""
        if not self._active or not self._current_stroke_points:
            self._current_stroke_points = []
            return None

        stroke = Stroke(
            points=tuple(self._current_stroke_points),
            color=self._current_color,
            width=self._current_width,
            page_number=self._page_number,
        )
        self._strokes.append(stroke)
        self._current_stroke_points = []

        from chenedusys.core.events import PaintStroke
        self._bus.publish(PaintStroke(
            stroke_id=stroke.id,
            points=tuple((p.x, p.y) for p in stroke.points),
            color=stroke.color,
            width=stroke.width,
        ))
        return stroke

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def undo(self) -> Stroke | None:
        """Remove and return the most recent stroke. Returns None if empty."""
        if not self._strokes:
            return None
        stroke = self._strokes.pop()
        return stroke

    # ------------------------------------------------------------------
    # Erase
    # ------------------------------------------------------------------

    def erase_at(self, x: float, y: float, radius: float = 10.0) -> list[Stroke]:
        """Erase all strokes that pass within *radius* of (x, y) in canvas space.

        Returns the list of removed strokes.
        """
        removed = []
        surviving: list[Stroke] = []
        for stroke in self._strokes:
            if self._stroke_near(stroke, x, y, radius):
                removed.append(stroke)
            else:
                surviving.append(stroke)

        self._strokes = surviving

        from chenedusys.core.events import PaintErase
        for stroke in removed:
            self._bus.publish(PaintErase(stroke_id=stroke.id))

        return removed

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear(self) -> int:
        """Remove all strokes for the current page. Returns count cleared."""
        before = len(self._strokes)
        self._strokes = [s for s in self._strokes if s.page_number != self._page_number]
        cleared = before - len(self._strokes)

        from chenedusys.core.events import PaintClear
        self._bus.publish(PaintClear(page_number=self._page_number))
        return cleared

    # ------------------------------------------------------------------
    # Remote stroke (received from peer)
    # ------------------------------------------------------------------

    def apply_remote_stroke(self, stroke: Stroke) -> None:
        """Add a stroke received from a remote peer."""
        self._strokes.append(stroke)

    # ------------------------------------------------------------------
    # Viewport helpers
    # ------------------------------------------------------------------

    def pan(self, dx: float, dy: float) -> None:
        """Shift the viewport by (dx, dy) pixels."""
        self._offset_x += dx
        self._offset_y += dy

    def canvas_to_screen(self, cx: float, cy: float) -> tuple[float, float]:
        """Convert canvas-space coordinates to screen-space."""
        return (cx - self._offset_x, cy - self._offset_y)

    def screen_to_canvas(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert screen-space coordinates to canvas-space."""
        return (sx + self._offset_x, sy + self._offset_y)

    def get_strokes_in_viewport(
        self, x: float, y: float, w: float, h: float
    ) -> tuple[Stroke, ...]:
        """Return strokes whose bounding box intersects the viewport rect."""
        result = []
        for s in self._strokes:
            if s.page_number != self._page_number:
                continue
            if not s.points:
                continue
            min_x = min(p.x for p in s.points) - s.width
            max_x = max(p.x for p in s.points) + s.width
            min_y = min(p.y for p in s.points) - s.width
            max_y = max(p.y for p in s.points) + s.width
            if max_x >= x and min_x <= x + w and max_y >= y and min_y <= y + h:
                result.append(s)
        return tuple(result)

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Disable all paint interactions."""
        self._active = False

    def resume(self) -> None:
        self._active = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _stroke_near(stroke: Stroke, x: float, y: float, radius: float) -> bool:
        """True if any point in *stroke* is within *radius* of (x, y)."""
        for pt in stroke.points:
            dist = math.hypot(pt.x - x, pt.y - y)
            if dist <= radius + stroke.width / 2:
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strokes": [s.to_dict() for s in self._strokes],
            "offset": [self._offset_x, self._offset_y],
            "page_number": self._page_number,
        }
