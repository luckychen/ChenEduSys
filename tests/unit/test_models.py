"""Unit tests for core data models."""

from __future__ import annotations

import pytest

from chenedusys.core.models import (
    Meeting,
    MeetingStatus,
    Point,
    Stroke,
    User,
    UserRole,
)


class TestUser:

    def test_create_user(self):
        user = User(username="alice", role=UserRole.TEACHER)
        assert user.username == "alice"
        assert user.role == UserRole.TEACHER
        assert len(user.id) == 12  # default factory

    def test_serialization_round_trip(self):
        user = User(username="bob", role=UserRole.STUDENT, display_name="Bob S")
        data = user.to_dict()
        restored = User.from_dict(data)
        assert restored == user

    def test_frozen(self):
        user = User(username="alice")
        with pytest.raises(AttributeError):
            user.username = "changed"  # type: ignore[misc]


class TestMeeting:

    def test_default_status_is_waiting(self):
        m = Meeting(teacher_id="abc", title="Math")
        assert m.status == MeetingStatus.WAITING

    def test_serialization_round_trip(self):
        m = Meeting(
            teacher_id="t1",
            title="Physics",
            status=MeetingStatus.ACTIVE,
            participants=("s1", "s2"),
        )
        data = m.to_dict()
        restored = Meeting.from_dict(data)
        assert restored == m

    def test_frozen(self):
        m = Meeting(teacher_id="t1", title="Math")
        with pytest.raises(AttributeError):
            m.title = "changed"  # type: ignore[misc]


class TestStroke:

    def test_create_stroke_with_points(self):
        stroke = Stroke(
            points=(Point(0, 0), Point(10, 20), Point(30, 40)),
            color="#FF0000",
            width=3.0,
        )
        assert len(stroke.points) == 3
        assert stroke.color == "#FF0000"

    def test_serialization_round_trip(self):
        stroke = Stroke(
            points=(Point(1.5, 2.5), Point(3.0, 4.0)),
            color="#00FF00",
            width=1.5,
            page_number=2,
        )
        data = stroke.to_dict()
        restored = Stroke.from_dict(data)
        assert restored == stroke

    def test_empty_stroke(self):
        stroke = Stroke()
        assert stroke.points == ()
        data = stroke.to_dict()
        restored = Stroke.from_dict(data)
        assert restored == stroke

    def test_single_point_stroke(self):
        stroke = Stroke(points=(Point(5, 5),))
        assert len(stroke.points) == 1
