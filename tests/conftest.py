"""Shared test fixtures."""

from __future__ import annotations

import pytest

from chenedusys.core.event_bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    """Fresh EventBus for each test."""
    return EventBus()
