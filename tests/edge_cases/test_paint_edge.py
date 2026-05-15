"""Edge-case tests for paint component."""

from __future__ import annotations

from chenedusys.core.event_bus import EventBus
from chenedusys.core.models import Point
from chenedusys.services.paint_engine import PaintEngine


class TestFastDrawing:

    def test_1000_points_in_one_stroke(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        for i in range(1000):
            engine.add_point(float(i), float(i))
        stroke = engine.end_stroke()
        assert stroke is not None
        assert len(stroke.points) == 1000

    def test_many_strokes_rapidly(self, bus: EventBus):
        engine = PaintEngine(bus)
        for i in range(500):
            engine.begin_stroke()
            engine.add_point(float(i), 0)
            engine.end_stroke()
        assert engine.stroke_count == 500


class TestSinglePointStroke:

    def test_single_point_stroke_stored(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(5, 5)
        stroke = engine.end_stroke()
        assert stroke is not None
        assert len(stroke.points) == 1
        assert stroke.points[0] == Point(x=5, y=5)


class TestBoundaryStrokes:

    def test_stroke_at_zero_zero(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(0, 0)
        engine.end_stroke()
        assert engine.stroke_count == 1

    def test_stroke_at_large_coordinates(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(99999, 99999)
        engine.end_stroke()
        assert engine.stroke_count == 1

    def test_stroke_at_negative_coordinates(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(-500, -500)
        engine.end_stroke()
        assert engine.stroke_count == 1


class TestPanning:

    def test_pan_negative_then_back(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(100, 100)
        engine.end_stroke()

        # Pan far away
        engine.pan(10000, 10000)
        assert engine.offset == (10000, 10000)

        # Pan back
        engine.pan(-10000, -10000)
        assert engine.offset == (0, 0)

        # Strokes should still be at original position
        assert engine.strokes[0].points[0] == Point(x=100, y=100)

    def test_pan_does_not_affect_stroke_storage(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(50, 50)
        engine.end_stroke()

        engine.pan(1000, 1000)
        assert engine.stroke_count == 1
        assert engine.strokes[0].points[0] == Point(x=50, y=50)


class TestIdenticalPoints:

    def test_all_points_same_position(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        for _ in range(10):
            engine.add_point(100, 100)
        stroke = engine.end_stroke()
        assert stroke is not None
        assert len(stroke.points) == 10
        assert all(p == Point(100, 100) for p in stroke.points)


class TestRapidModeSwitch:

    def test_draw_after_rapid_mode_changes(self, bus: EventBus):
        """Drawing should still work after toggling modes many times."""
        engine = PaintEngine(bus)

        # Simulate rapid mode switching — just begin/end strokes
        for _ in range(50):
            engine.begin_stroke()
            engine.add_point(1, 1)
            engine.end_stroke()

        assert engine.stroke_count == 50

        # Final draw still works
        engine.begin_stroke(color="#FF0000", width=5.0)
        engine.add_point(99, 99)
        stroke = engine.end_stroke()
        assert stroke is not None
        assert stroke.color == "#FF0000"
        assert stroke.width == 5.0


class TestManyStrokesPerformance:

    def test_500_strokes_still_functional(self, bus: EventBus):
        engine = PaintEngine(bus)
        for i in range(500):
            engine.begin_stroke()
            engine.add_point(float(i), float(i))
            engine.end_stroke()

        assert engine.stroke_count == 500

        # Erase near (250, 250)
        removed = engine.erase_at(250, 250, radius=2)
        assert len(removed) >= 1
        remaining = engine.stroke_count
        assert remaining == 500 - len(removed)

        # Clear all remaining
        cleared = engine.clear()
        assert cleared == remaining
        assert engine.stroke_count == 0


class TestEraserEdgeCases:

    def test_erase_at_exact_stroke_point(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(100, 100)
        engine.end_stroke()

        removed = engine.erase_at(100, 100, radius=0.1)
        assert len(removed) == 1

    def test_erase_respects_stroke_width(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke(width=20.0)
        engine.add_point(100, 100)
        engine.end_stroke()

        # Erasing near the stroke should work even with small radius
        # because the stroke itself is 20px wide
        removed = engine.erase_at(110, 100, radius=0.1)
        assert len(removed) == 1

    def test_erase_on_empty_canvas(self, bus: EventBus):
        engine = PaintEngine(bus)
        removed = engine.erase_at(0, 0, radius=100)
        assert removed == []


class TestViewportEdgeCases:

    def test_viewport_with_no_strokes(self, bus: EventBus):
        engine = PaintEngine(bus)
        visible = engine.get_strokes_in_viewport(0, 0, 1000, 1000)
        assert visible == ()

    def test_viewport_covers_all_strokes(self, bus: EventBus):
        engine = PaintEngine(bus)
        for i in range(10):
            engine.begin_stroke()
            engine.add_point(float(i * 10), float(i * 10))
            engine.end_stroke()

        visible = engine.get_strokes_in_viewport(0, 0, 100, 100)
        assert len(visible) == 10

    def test_viewport_covers_none(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(5000, 5000)
        engine.end_stroke()

        visible = engine.get_strokes_in_viewport(0, 0, 100, 100)
        assert len(visible) == 0
