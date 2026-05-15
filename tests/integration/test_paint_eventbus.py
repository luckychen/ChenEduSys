"""Integration tests: PaintEngine + EventBus event flow."""

from __future__ import annotations

from chenedusys.core.event_bus import EventBus
from chenedusys.core.events import (
    PaintClear,
    PaintModeChange,
    PaintRemoteStroke,
    PaintStroke,
)
from chenedusys.core.models import Point, Stroke
from chenedusys.services.paint_engine import PaintEngine


class TestStrokeEvents:

    def test_stroke_fires_event(self, bus: EventBus):
        events = []
        bus.subscribe("paint.stroke", lambda e: events.append(e))

        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(1, 1)
        engine.end_stroke()

        assert len(events) == 1
        assert isinstance(events[0], PaintStroke)
        assert events[0].points == ((1.0, 1.0),)

    def test_stroke_event_contains_correct_data(self, bus: EventBus):
        events = []
        bus.subscribe("paint.stroke", lambda e: events.append(e))

        engine = PaintEngine(bus)
        engine.begin_stroke(color="#FF0000", width=3.0)
        engine.add_point(10, 20)
        engine.add_point(30, 40)
        stroke = engine.end_stroke()

        assert stroke is not None
        e = events[0]
        assert e.color == "#FF0000"
        assert e.width == 3.0
        assert e.stroke_id == stroke.id
        assert len(e.points) == 2

    def test_no_stroke_event_for_empty_stroke(self, bus: EventBus):
        events = []
        bus.subscribe("paint.stroke", lambda e: events.append(e))

        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.end_stroke()  # no points

        assert len(events) == 0


class TestClearEvent:

    def test_clear_fires_event(self, bus: EventBus):
        events = []
        bus.subscribe("paint.clear", lambda e: events.append(e))

        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(1, 1)
        engine.end_stroke()
        engine.clear()

        assert len(events) == 1
        assert isinstance(events[0], PaintClear)


class TestEraseEvent:

    def test_erase_fires_event(self, bus: EventBus):
        events = []
        bus.subscribe("paint.erase", lambda e: events.append(e))

        engine = PaintEngine(bus)
        engine.begin_stroke()
        engine.add_point(50, 50)
        stroke = engine.end_stroke()
        assert stroke is not None

        engine.erase_at(50, 50, radius=10)
        assert len(events) == 1
        assert events[0].stroke_id == stroke.id


class TestModeChangeEvent:

    def test_mode_change_published(self, bus: EventBus):
        events = []
        bus.subscribe("paint.mode_change", lambda e: events.append(e))

        bus.publish(PaintModeChange(mode="eraser"))
        assert len(events) == 1
        assert events[0].mode == "eraser"


class TestRemoteStrokeEvent:

    def test_remote_stroke_applied_via_event(self, bus: EventBus):
        engine = PaintEngine(bus)

        remote_stroke = Stroke(
            points=(Point(100, 100), Point(200, 200)),
            color="#00FF00",
            width=1.0,
        )

        def on_remote(event):
            engine.apply_remote_stroke(remote_stroke)

        bus.subscribe("paint.remote_stroke", on_remote)
        bus.publish(PaintRemoteStroke(
            stroke_id=remote_stroke.id,
            points=((100, 100), (200, 200)),
            color="#00FF00",
            width=1.0,
        ))

        assert engine.stroke_count == 1
        assert engine.strokes[0].color == "#00FF00"
