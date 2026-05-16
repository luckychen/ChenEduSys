"""Unit tests for hub server database."""

from __future__ import annotations

import pytest

from hub_server.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


class TestUserCRUD:

    def test_create_and_get_user(self, db):
        db.create_user("u1", "alice", "hash123", "student")
        user = db.get_user_by_username("alice")
        assert user is not None
        assert user["id"] == "u1"
        assert user["role"] == "student"

    def test_get_nonexistent_user(self, db):
        assert db.get_user_by_username("nobody") is None

    def test_get_user_by_id(self, db):
        db.create_user("u1", "bob", "hash", "teacher")
        user = db.get_user_by_id("u1")
        assert user["username"] == "bob"

    def test_password_hash_stored_not_plaintext(self, db):
        db.create_user("u1", "alice", "$argon2id$somehash", "student")
        user = db.get_user_by_username("alice")
        assert user["password_hash"].startswith("$argon2")
        assert user["password_hash"] != "plaintext"


class TestMeetingCRUD:

    def test_create_and_get_meeting(self, db):
        db.create_user("t1", "teacher", "hash", "teacher")
        db.create_meeting("m1", "t1", "Math Class", max_participants=3)
        m = db.get_meeting("m1")
        assert m is not None
        assert m["title"] == "Math Class"
        assert m["status"] == "waiting"

    def test_list_active_meetings(self, db):
        db.create_user("t1", "teacher", "hash", "teacher")
        db.create_meeting("m1", "t1", "Active")
        db.create_meeting("m2", "t1", "Ended")
        db.update_meeting_status("m2", "ended")
        active = db.list_active_meetings()
        assert len(active) == 1
        assert active[0]["id"] == "m1"

    def test_delete_meeting(self, db):
        db.create_user("t1", "teacher", "hash", "teacher")
        db.create_meeting("m1", "t1", "Test")
        db.delete_meeting("m1")
        assert db.get_meeting("m1") is None


class TestParticipants:

    def test_add_and_count_participants(self, db):
        db.create_user("t1", "teacher", "hash", "teacher")
        db.create_user("s1", "student1", "hash", "student")
        db.create_user("s2", "student2", "hash", "student")
        db.create_meeting("m1", "t1", "Test", max_participants=5)
        db.add_participant("m1", "t1")
        db.add_participant("m1", "s1")
        db.add_participant("m1", "s2")
        assert db.participant_count("m1") == 3

    def test_remove_participant(self, db):
        db.create_user("t1", "teacher", "hash", "teacher")
        db.create_user("s1", "student", "hash", "student")
        db.create_meeting("m1", "t1", "Test")
        db.add_participant("m1", "s1")
        assert db.participant_count("m1") == 1
        db.remove_participant("m1", "s1")
        assert db.participant_count("m1") == 0

    def test_get_participants_list(self, db):
        db.create_user("t1", "teacher", "hash", "teacher")
        db.create_user("s1", "student", "hash", "student")
        db.create_meeting("m1", "t1", "Test")
        db.add_participant("m1", "t1")
        db.add_participant("m1", "s1")
        participants = db.get_participants("m1")
        assert len(participants) == 2

    def test_duplicate_participant_is_idempotent(self, db):
        db.create_user("t1", "teacher", "hash", "teacher")
        db.create_meeting("m1", "t1", "Test")
        db.add_participant("m1", "t1")
        db.add_participant("m1", "t1")  # no error
        assert db.participant_count("m1") == 1
