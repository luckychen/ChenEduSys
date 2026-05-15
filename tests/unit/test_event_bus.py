"""Unit tests for EventBus."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

from chenedusys.core.event_bus import EventBus


# -- Helpers ---------------------------------------------------------------

@dataclass(frozen=True)
class _FakeEvent:
    value: int

    @property
    def topic(self) -> str:
        return "test.fake"


# -- Tests -----------------------------------------------------------------

class TestSubscribePublish:

    def test_subscriber_receives_event(self, bus: EventBus):
        received = []
        bus.subscribe("test.fake", lambda e: received.append(e))
        event = _FakeEvent(value=42)
        bus.publish(event)
        assert len(received) == 1
        assert received[0].value == 42

    def test_multiple_subscribers_all_receive(self, bus: EventBus):
        results = [[], [], []]
        for i in range(3):
            bus.subscribe("test.fake", lambda e, idx=i: results[idx].append(e))
        bus.publish(_FakeEvent(value=1))
        assert all(len(r) == 1 for r in results)

    def test_publish_to_empty_topic_is_noop(self, bus: EventBus):
        bus.publish(_FakeEvent(value=1))  # no subscribers — no crash

    def test_typed_event_payload(self, bus: EventBus):
        received = []
        bus.subscribe("test.fake", lambda e: received.append(e))
        bus.publish(_FakeEvent(value=99))
        assert isinstance(received[0], _FakeEvent)
        assert received[0].value == 99


class TestUnsubscribe:

    def test_unsubscribed_handler_does_not_receive(self, bus: EventBus):
        received = []
        sub = bus.subscribe("test.fake", lambda e: received.append(e))
        sub.unsubscribe()
        bus.publish(_FakeEvent(value=1))
        assert received == []

    def test_double_unsubscribe_is_safe(self, bus: EventBus):
        sub = bus.subscribe("test.fake", lambda e: None)
        sub.unsubscribe()
        sub.unsubscribe()  # second call — no error


class TestHandlerException:

    def test_exception_in_handler_does_not_stop_others(self, bus: EventBus):
        results = []

        def bad_handler(e):
            raise RuntimeError("boom")

        bus.subscribe("test.fake", bad_handler)
        bus.subscribe("test.fake", lambda e: results.append(e))

        bus.publish(_FakeEvent(value=1))
        assert len(results) == 1  # second handler still ran


class TestAsyncHandler:

    def test_async_handler_is_scheduled(self, bus: EventBus):
        result = []

        async def async_handler(e):
            result.append(e.value)

        bus.subscribe("test.fake", async_handler)

        async def _run():
            bus.publish(_FakeEvent(value=7))
            # give the scheduled coroutine a chance to run
            await asyncio.sleep(0.05)
            assert result == [7]

        asyncio.run(_run())

    def test_async_handler_without_running_loop_logs_warning(self, bus: EventBus):
        async def async_handler(e):
            pass

        bus.subscribe("test.fake", async_handler)
        # Called from sync context — no running loop
        bus.publish(_FakeEvent(value=1))  # should not crash


class TestThreadSafety:

    def test_concurrent_publish(self, bus: EventBus):
        received = []
        lock = threading.Lock()
        barrier = threading.Barrier(4)

        def handler(e):
            with lock:
                received.append(e.value)

        bus.subscribe("test.fake", handler)

        def publish_many(start):
            barrier.wait()
            for i in range(100):
                bus.publish(_FakeEvent(value=start + i))

        threads = [threading.Thread(target=publish_many, args=(t * 1000,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == 400

    def test_has_subscribers(self, bus: EventBus):
        assert not bus.has_subscribers("test.fake")
        bus.subscribe("test.fake", lambda e: None)
        assert bus.has_subscribers("test.fake")
