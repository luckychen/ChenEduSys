"""Event type definitions for the ChenEduSys event bus.

All events are frozen dataclasses. Each event maps to a topic string
that components use to subscribe/publish.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _topic(category: str, name: str) -> str:
    return f"{category}.{name}"


# ---------------------------------------------------------------------------
# Auth events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LoginSuccess:
    username: str
    user_id: str
    token: str

    @property
    def topic(self) -> str:
        return _topic("auth", "login_success")


@dataclass(frozen=True)
class LoginFail:
    reason: str

    @property
    def topic(self) -> str:
        return _topic("auth", "login_fail")


@dataclass(frozen=True)
class Logout:
    user_id: str

    @property
    def topic(self) -> str:
        return _topic("auth", "logout")


# ---------------------------------------------------------------------------
# Meeting events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MeetingCreated:
    meeting_id: str
    teacher_id: str
    title: str

    @property
    def topic(self) -> str:
        return _topic("meeting", "created")


@dataclass(frozen=True)
class MeetingJoined:
    meeting_id: str
    student_id: str
    student_name: str

    @property
    def topic(self) -> str:
        return _topic("meeting", "joined")


@dataclass(frozen=True)
class MeetingLeft:
    meeting_id: str
    participant_id: str

    @property
    def topic(self) -> str:
        return _topic("meeting", "left")


@dataclass(frozen=True)
class MeetingEnded:
    meeting_id: str

    @property
    def topic(self) -> str:
        return _topic("meeting", "ended")


# ---------------------------------------------------------------------------
# Network events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class P2PConnected:
    peer_id: str
    peer_address: str

    @property
    def topic(self) -> str:
        return _topic("network", "p2p_connected")


@dataclass(frozen=True)
class P2PDisconnected:
    peer_id: str
    reason: str

    @property
    def topic(self) -> str:
        return _topic("network", "p2p_disconnected")


@dataclass(frozen=True)
class P2PConnectFailed:
    peer_id: str
    error: str

    @property
    def topic(self) -> str:
        return _topic("network", "p2p_connect_failed")


# ---------------------------------------------------------------------------
# Content events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PDFLoaded:
    file_hash: str
    page_count: int
    file_name: str

    @property
    def topic(self) -> str:
        return _topic("content", "pdf_loaded")


@dataclass(frozen=True)
class PDFPageChanged:
    page_number: int

    @property
    def topic(self) -> str:
        return _topic("content", "pdf_page_changed")


# ---------------------------------------------------------------------------
# Paint events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PaintStroke:
    stroke_id: str
    points: tuple[tuple[float, float], ...]
    color: str
    width: float

    @property
    def topic(self) -> str:
        return _topic("paint", "stroke")


@dataclass(frozen=True)
class PaintRemoteStroke:
    stroke_id: str
    points: tuple[tuple[float, float], ...]
    color: str
    width: float

    @property
    def topic(self) -> str:
        return _topic("paint", "remote_stroke")


@dataclass(frozen=True)
class PaintErase:
    stroke_id: str

    @property
    def topic(self) -> str:
        return _topic("paint", "erase")


@dataclass(frozen=True)
class PaintClear:
    page_number: int = 0

    @property
    def topic(self) -> str:
        return _topic("paint", "clear")


@dataclass(frozen=True)
class PaintModeChange:
    mode: str  # "pen" | "eraser" | "pan"

    @property
    def topic(self) -> str:
        return _topic("paint", "mode_change")


# ---------------------------------------------------------------------------
# Audio events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AudioMuteToggle:
    muted: bool

    @property
    def topic(self) -> str:
        return _topic("audio", "mute_toggle")


# ---------------------------------------------------------------------------
# System events
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SystemError:
    source: str
    message: str
    details: str = ""

    @property
    def topic(self) -> str:
        return _topic("system", "error")


# ---------------------------------------------------------------------------
# Topic → Event class mapping (for deserialization)
# ---------------------------------------------------------------------------

EVENT_TYPES: dict[str, type] = {
    cls.topic.fget(None): cls  # type: ignore[union-attr]
    for cls in list(globals().values())
    if dataclasses.is_dataclass(cls)
    and hasattr(cls, "topic")
    and isinstance(getattr(cls, "topic"), property)
}
