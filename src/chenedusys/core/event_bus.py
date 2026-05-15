"""Typed publish/subscribe event bus for loose component coupling."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

# A handler can be sync or async, takes a single event payload.
Handler = Callable[[Any], Any]


class _Subscription:
    """Token returned by subscribe(). Holds the handler reference so
    callers can unsubscribe without keeping the handler callable."""

    __slots__ = ("topic", "handler", "_bus")

    def __init__(self, topic: str, handler: Handler, bus: EventBus) -> None:
        self.topic = topic
        self.handler = handler
        self._bus = bus

    def unsubscribe(self) -> None:
        self._bus._unsubscribe(self)


class EventBus:
    """Synchronous pub/sub with support for both sync and async handlers.

    Async handlers are scheduled on the running asyncio event loop (if
    any). If no loop is running they are *not* executed — prefer running
    inside ``asyncio.run()`` or a Qt-async bridge when async handlers
    are needed.

    Thread-safety: ``publish()`` and ``subscribe()``/``unsubscribe()``
    are protected by a reentrant lock so they can be called from any
    thread.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, handler: Handler) -> _Subscription:
        """Register *handler* for *topic*. Returns an unsubscribe token."""
        with self._lock:
            self._handlers[topic].append(handler)
        return _Subscription(topic, handler, self)

    def publish(self, event: Any) -> None:
        """Publish *event* to all subscribers of ``event.topic``."""
        topic = getattr(event, "topic", None)
        if topic is None:
            raise ValueError(f"Event {type(event).__name__!r} has no 'topic' attribute")

        with self._lock:
            handlers = list(self._handlers.get(topic, []))

        for handler in handlers:
            self._invoke(handler, event)

    def has_subscribers(self, topic: str) -> bool:
        with self._lock:
            return bool(self._handlers.get(topic))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _invoke(self, handler: Handler, event: Any) -> None:
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                self._schedule_coroutine(result)
        except Exception:
            logger.exception(
                "EventBus handler %r raised on topic %s",
                getattr(handler, "__name__", handler),
                getattr(event, "topic", "?"),
            )

    @staticmethod
    def _schedule_coroutine(coro: asyncio.coroutines) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            logger.warning("No running asyncio loop — async handler skipped")

    def _unsubscribe(self, sub: _Subscription) -> None:
        with self._lock:
            handlers = self._handlers.get(sub.topic)
            if handlers is not None:
                try:
                    handlers.remove(sub.handler)
                except ValueError:
                    pass

    def __repr__(self) -> str:
        with self._lock:
            total = sum(len(h) for h in self._handlers.values())
            topics = len(self._handlers)
        return f"<EventBus {topics} topics, {total} handlers>"
