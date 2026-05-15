"""Edge-case tests for EventBus."""

from __future__ import annotations

import tracemalloc
from dataclasses import dataclass

import pytest

from chenedusys.core.event_bus import EventBus


@dataclass(frozen=True)
class _Ev:
    value: int

    @property
    def topic(self) -> str:
        return "edge.test"


class TestStressPublish:

    def test_10000_events_delivered(self):
        bus = EventBus()
        received = []
        bus.subscribe("edge.test", lambda e: received.append(e.value))

        for i in range(10_000):
            bus.publish(_Ev(value=i))

        assert len(received) == 10_000
        assert received == list(range(10_000))

    def test_no_memory_leak_on_many_events(self):
        tracemalloc.start()
        bus = EventBus()
        received = []
        bus.subscribe("edge.test", lambda e: received.append(e.value))

        snapshot_before = tracemalloc.take_snapshot()

        for i in range(10_000):
            bus.publish(_Ev(value=i))

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compare only EventBus-related allocations — not the 'received' list
        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        bus_allocs = [s for s in stats if "event_bus" in s.traceback[0].filename]
        total_bus_kb = sum(s.size_diff for s in bus_allocs) / 1024
        # EventBus should not accumulate unbounded memory
        assert total_bus_kb < 500, f"EventBus grew by {total_bus_kb:.0f} KB"


class TestSubscribeDuringPublish:

    def test_handler_subscribing_during_publish(self):
        """A handler that subscribes to the same topic should only get
        *future* events, not the current one."""
        bus = EventBus()
        order = []

        def handler_a(e):
            order.append("A")
            bus.subscribe("edge.test", handler_b)

        def handler_b(e):
            order.append("B")

        bus.subscribe("edge.test", handler_a)

        bus.publish(_Ev(value=1))
        assert order == ["A"]  # handler_b not called yet

        bus.publish(_Ev(value=2))
        assert "B" in order  # now handler_b gets called


class TestConcurrentConfigAccess:

    def test_concurrent_read_write(self, tmp_path):
        """Config file read/write from two threads should not corrupt."""
        import threading
        from chenedusys.core.config import AppConfig, save_config, load_config

        cfg_file = tmp_path / "config.toml"
        errors = []

        def writer():
            for i in range(100):
                try:
                    save_config(AppConfig(log_level="DEBUG"), cfg_file)
                except Exception as e:
                    errors.append(e)

        def reader():
            for i in range(100):
                try:
                    load_config(cfg_file)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == []


class TestStrokeEdgeCases:

    def test_stroke_with_nan_coordinates_rejected(self):
        from chenedusys.core.models import Point

        with pytest.raises((ValueError, TypeError)):
            Point(x=float("nan"), y=1.0)

    def test_stroke_with_inf_coordinates_rejected(self):
        from chenedusys.core.models import Point

        with pytest.raises((ValueError, TypeError)):
            Point(x=float("inf"), y=1.0)
