"""Shared data models used across all layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    TEACHER = "teacher"
    STUDENT = "student"


@dataclass(frozen=True)
class User:
    id: str = field(default_factory=_new_id)
    username: str = ""
    role: UserRole = UserRole.STUDENT
    display_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role.value,
            "display_name": self.display_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        return cls(
            id=data["id"],
            username=data["username"],
            role=UserRole(data["role"]),
            display_name=data.get("display_name", ""),
        )


# ---------------------------------------------------------------------------
# Meeting
# ---------------------------------------------------------------------------

class MeetingStatus(str, Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    ENDED = "ended"


@dataclass(frozen=True)
class Meeting:
    id: str = field(default_factory=_new_id)
    teacher_id: str = ""
    title: str = ""
    status: MeetingStatus = MeetingStatus.WAITING
    max_participants: int = 5
    participants: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "teacher_id": self.teacher_id,
            "title": self.title,
            "status": self.status.value,
            "max_participants": self.max_participants,
            "participants": list(self.participants),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Meeting:
        return cls(
            id=data["id"],
            teacher_id=data["teacher_id"],
            title=data["title"],
            status=MeetingStatus(data["status"]),
            max_participants=data.get("max_participants", 5),
            participants=tuple(data.get("participants", ())),
        )


# ---------------------------------------------------------------------------
# Paint / Canvas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        import math
        if math.isnan(self.x) or math.isnan(self.y):
            raise ValueError("Point coordinates cannot be NaN")
        if math.isinf(self.x) or math.isinf(self.y):
            raise ValueError("Point coordinates cannot be infinite")

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Point:
        return cls(x=data["x"], y=data["y"])


@dataclass(frozen=True)
class Stroke:
    id: str = field(default_factory=_new_id)
    points: tuple[Point, ...] = ()
    color: str = "#000000"
    width: float = 2.0
    page_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "points": [p.to_dict() for p in self.points],
            "color": self.color,
            "width": self.width,
            "page_number": self.page_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Stroke:
        points = tuple(Point.from_dict(p) for p in data.get("points", ()))
        return cls(
            id=data["id"],
            points=points,
            color=data.get("color", "#000000"),
            width=data.get("width", 2.0),
            page_number=data.get("page_number", 0),
        )
