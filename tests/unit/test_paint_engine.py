"""Unit tests for PaintEngine."""

from __future__ import annotations

from chenedusys.core.event_bus import EventBus
from chenedusys.core.models import Point, Stroke
from chenedusys.services.paint_engine import PaintEngine


class TestStrokeStorage:

    def test_add_one_stroke(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke(color="#000000", width=2.0)
        engine.add_point(0, 0)
        engine.add_point(10, 20)
        stroke = engine.end_stroke()

        assert stroke is not None
        assert engine.stroke_count == 1
        assert len(stroke.points) == 2
        assert stroke.points[0] == Point(x=0, y=0)

    def test_add_multiple_strokes(self, bus: EventBus):
        engine = PaintEngine(bus)
        for _ in range(5):
            engine.begin_stroke()
            engine.add_point(1, 1)
            engine.end_stroke()
        assert engine.stroke_count == 5

    def test_stroke_properties_preserved(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke(color="#FF0000", width=3.5)
        engine.add_point(5, 5)
        engine.add_point(15, 15)
        engine.add_point(25, 25)
        stroke = engine.end_stroke()

        assert stroke is not None
        assert stroke.color == "#FF0000"
        assert stroke.width == 3.5
        assert len(stroke.points) == 3

    def test_end_stroke_without_begin_returns_none(self, bus: EventBus):
        engine = PaintEngine(bus)
        assert engine.end_stroke() is None

    def test_end_stroke_with_no_points_returns_none(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        assert engine.end_stroke() is None

    def test_empty_stroke_count(self, bus: EventBus):
        engine = PaintEngine(bus)
        assert engine.stroke_count == 0

    def test_strokes_property_returns_tuple(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(1, 1)
        engine.end_stroke()
        assert isinstance(engine.strokes, tuple)


class TestUndo:

    def test_undo_removes_last_stroke(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(1, 1)
        s1 = engine.end_stroke()
        engine.begin_stroke()
        engine.add_point(2, 2)
        s2 = engine.end_stroke()

        undone = engine.undo()
        assert undone == s2
        assert engine.stroke_count == 1
        assert engine.strokes[0] == s1

    def test_undo_empty_returns_none(self, bus: EventBus):
        engine = PaintEngine(bus)
        assert engine.undo() is None


class TestErase:

    def test_erase_stroke_by_point(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(50, 50)
        engine.add_point(60, 60)
        stroke = engine.end_stroke()
        assert stroke is not None

        removed = engine.erase_at(55, 55, radius=10)
        assert len(removed) == 1
        assert removed[0].id == stroke.id
        assert engine.stroke_count == 0

    def test_erase_with_radius(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(0, 0)
        engine.add_point(100, 100)
        engine.end_stroke()

        # Point far from stroke — should not erase
        removed = engine.erase_at(500, 500, radius=10)
        assert len(removed) == 0
        assert engine.stroke_count == 1

        # Point near stroke — should erase
        removed = engine.erase_at(5, 5, radius=10)
        assert len(removed) == 1
        assert engine.stroke_count == 0

    def test_erase_only_nearby_strokes(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(10, 10)
        engine.end_stroke()
        engine.begin_stroke()
        engine.add_point(1000, 1000)
        s2 = engine.end_stroke()

        removed = engine.erase_at(10, 10, radius=5)
        assert len(removed) == 1
        assert engine.stroke_count == 1
        assert engine.strokes[0].id == s2.id


class TestClear:

    def test_clear_all_strokes(self, bus: EventBus):
        engine = PaintEngine(bus)
        for _ in range(3):
            engine.begin_stroke()
            engine.add_point(1, 1)
            engine.end_stroke()
        assert engine.stroke_count == 3

        cleared = engine.clear()
        assert cleared == 3
        assert engine.stroke_count == 0

    def test_clear_empty_canvas(self, bus: EventBus):
        engine = PaintEngine(bus)
        assert engine.clear() == 0

    def test_clear_only_current_page(self, bus: EventBus):
        engine = PaintEngine(bus, page_number=0)
        engine.begin_stroke()
        engine.add_point(1, 1)
        engine.end_stroke()  # page 0

        engine.page_number = 1
        engine.begin_stroke()
        engine.add_point(2, 2)
        engine.end_stroke()  # page 1

        cleared = engine.clear()  # clears page 1 only
        assert cleared == 1
        assert engine.stroke_count == 1  # page 0 stroke remains
        assert engine.strokes[0].page_number == 0


class TestViewport:

    def test_screen_to_canvas_round_trip(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.offset = (100, 200)
        cx, cy = engine.screen_to_canvas(50, 75)
        assert cx == 150
        assert cy == 275

        sx, sy = engine.canvas_to_screen(cx, cy)
        assert sx == 50
        assert sy == 75

    def test_pan_shifts_offset(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.pan(30, -20)
        assert engine.offset == (30, -20)
        engine.pan(10, 10)
        assert engine.offset == (40, -10)

    def test_get_strokes_in_viewport(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(50, 50)
        engine.add_point(60, 60)
        engine.end_stroke()

        engine.begin_stroke()
        engine.add_point(500, 500)
        engine.end_stroke()

        visible = engine.get_strokes_in_viewport(0, 0, 100, 100)
        assert len(visible) == 1
        assert visible[0].points[0].x == 50

    def test_negative_offset_viewport(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.offset = (-500, -500)
        cx, cy = engine.screen_to_canvas(0, 0)
        assert cx == -500
        assert cy == -500


class TestRemoteStroke:

    def test_apply_remote_stroke(self, bus: EventBus):
        engine = PaintEngine(bus)
        remote = Stroke(points=(Point(10, 10), Point(20, 20)), color="#FF0000")
        engine.apply_remote_stroke(remote)
        assert engine.stroke_count == 1
        assert engine.strokes[0].id == remote.id


class TestActivation:

    def test_stop_disables_drawing(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.stop()
        engine.begin_stroke()
        engine.add_point(1, 1)
        result = engine.end_stroke()
        assert result is None
        assert engine.stroke_count == 0
        assert not engine.is_active

    def test_resume_enables_drawing(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.stop()
        engine.resume()
        engine.begin_stroke()
        engine.add_point(1, 1)
        result = engine.end_stroke()
        assert result is not None
        assert engine.is_active


class TestSerialization:

    def test_to_dict(self, bus: EventBus):
        engine = PaintEngine(bus)
        engine.offset = (10, 20)
        engine.begin_stroke()
        engine.add_point(1, 2)
        engine.end_stroke()

        data = engine.to_dict()
        assert data["offset"] == [10, 20]
        assert len(data["strokes"]) == 1
