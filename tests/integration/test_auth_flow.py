"""Integration tests: full auth + meeting flow against aiohttp test server."""

from __future__ import annotations

import pytest

from hub_server.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "test.db"))


@pytest.fixture
async def client(aiohttp_client, app):
    return await aiohttp_client(app)


async def _approve_user(client, username):
    """Approve a pending user via admin API (simulates admin action)."""
    # Login as admin (seeded by create_app)
    admin_resp = await client.post("/admin/login", json={"username": "admin", "password": "admin"})
    # Admin login may fail if password differs; use direct DB approve instead
    db = client.app["db"]
    user = db.get_user_by_username(username)
    if user:
        db.update_user_status(user["id"], "active")


class TestRegisterAndLogin:

    async def test_register_returns_pending_status(self, client):
        resp = await client.post("/register", json={
            "username": "alice",
            "password": "password123",
            "role": "teacher",
        })
        assert resp.status == 201
        body = await resp.json()
        assert body["username"] == "alice"
        assert body["role"] == "teacher"
        assert body["status"] == "pending"

    async def test_pending_user_cannot_login(self, client):
        await client.post("/register", json={
            "username": "alice",
            "password": "password123",
            "role": "teacher",
        })
        resp = await client.post("/login", json={
            "username": "alice",
            "password": "password123",
        })
        assert resp.status == 403
        body = await resp.json()
        assert "pending" in body["reason"].lower()

    async def test_approved_user_can_login(self, client):
        await client.post("/register", json={
            "username": "alice",
            "password": "password123",
            "role": "teacher",
        })
        await _approve_user(client, "alice")

        resp = await client.post("/login", json={
            "username": "alice",
            "password": "password123",
        })
        assert resp.status == 200
        body = await resp.json()
        assert "token" in body
        assert body["user"]["username"] == "alice"

    async def test_rejected_user_cannot_login(self, client):
        await client.post("/register", json={
            "username": "bob",
            "password": "password123",
        })
        db = client.app["db"]
        user = db.get_user_by_username("bob")
        db.update_user_status(user["id"], "rejected")

        resp = await client.post("/login", json={
            "username": "bob",
            "password": "password123",
        })
        assert resp.status == 403
        body = await resp.json()
        assert "rejected" in body["reason"].lower()

    async def test_register_duplicate_fails(self, client):
        await client.post("/register", json={"username": "bob", "password": "password123"})
        resp = await client.post("/register", json={"username": "bob", "password": "password123"})
        assert resp.status == 409

    async def test_register_short_password(self, client):
        resp = await client.post("/register", json={"username": "charlie", "password": "short"})
        assert resp.status == 400
        body = await resp.json()
        assert "8 characters" in body["reason"]

    async def test_register_empty_username(self, client):
        resp = await client.post("/register", json={"username": "", "password": "password123"})
        assert resp.status == 400

    async def test_login_wrong_password(self, client):
        await client.post("/register", json={"username": "dave", "password": "password123"})
        await _approve_user(client, "dave")
        resp = await client.post("/login", json={"username": "dave", "password": "wrong"})
        assert resp.status == 401

    async def test_login_nonexistent_user(self, client):
        resp = await client.post("/login", json={"username": "ghost", "password": "nopw1234"})
        assert resp.status == 401

    async def test_me_endpoint_with_valid_token(self, client):
        await client.post("/register", json={"username": "eve", "password": "password123"})
        await _approve_user(client, "eve")
        login_resp = await client.post("/login", json={"username": "eve", "password": "password123"})
        token = (await login_resp.json())["token"]

        resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status == 200
        body = await resp.json()
        assert body["username"] == "eve"

    async def test_me_endpoint_no_token(self, client):
        resp = await client.get("/me")
        assert resp.status == 401

    async def test_sql_injection_username(self, client):
        resp = await client.post("/register", json={
            "username": "' OR 1=1 --",
            "password": "password123",
        })
        assert resp.status == 201
        await _approve_user(client, "' OR 1=1 --")
        login_resp = await client.post("/login", json={
            "username": "' OR 1=1 --",
            "password": "password123",
        })
        assert login_resp.status == 200


class TestMeetingFlow:

    async def _make_teacher(self, client, username="teacher1"):
        await client.post("/register", json={"username": username, "password": "password123", "role": "teacher"})
        await _approve_user(client, username)
        resp = await client.post("/login", json={"username": username, "password": "password123"})
        return (await resp.json())["token"]

    async def _make_student(self, client, username="student1"):
        await client.post("/register", json={"username": username, "password": "password123", "role": "student"})
        await _approve_user(client, username)
        resp = await client.post("/login", json={"username": username, "password": "password123"})
        return (await resp.json())["token"]

    async def test_create_meeting(self, client):
        token = await self._make_teacher(client)
        resp = await client.post("/meetings", json={"title": "Physics"}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status == 201
        body = await resp.json()
        assert body["title"] == "Physics"

    async def test_student_cannot_create_meeting(self, client):
        token = await self._make_student(client)
        resp = await client.post("/meetings", json={"title": "Hack"}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status == 403

    async def test_list_meetings(self, client):
        t1 = await self._make_teacher(client, "t1")
        await client.post("/meetings", json={"title": "Math"}, headers={"Authorization": f"Bearer {t1}"})
        resp = await client.get("/meetings", headers={"Authorization": f"Bearer {t1}"})
        assert resp.status == 200
        body = await resp.json()
        assert len(body) >= 1

    async def test_join_meeting(self, client):
        t_token = await self._make_teacher(client, "teacher_j")
        s_token = await self._make_student(client, "student_j")

        # Teacher creates
        resp = await client.post("/meetings", json={"title": "Join Test"}, headers={"Authorization": f"Bearer {t_token}"})
        meeting_id = (await resp.json())["id"]

        # Student joins
        resp = await client.post(f"/meetings/{meeting_id}/join", headers={"Authorization": f"Bearer {s_token}"})
        assert resp.status == 200
        body = await resp.json()
        assert len(body["participants"]) == 2  # teacher + student

    async def test_join_nonexistent_meeting(self, client):
        token = await self._make_student(client, "student_n")
        resp = await client.post("/meetings/nonexistent/join", headers={"Authorization": f"Bearer {token}"})
        assert resp.status == 404

    async def test_end_meeting(self, client):
        token = await self._make_teacher(client, "teacher_e")
        resp = await client.post("/meetings", json={"title": "End Test"}, headers={"Authorization": f"Bearer {token}"})
        meeting_id = (await resp.json())["id"]

        resp = await client.delete(f"/meetings/{meeting_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status == 200

        # Verify ended
        resp = await client.get(f"/meetings/{meeting_id}", headers={"Authorization": f"Bearer {token}"})
        body = await resp.json()
        assert body["status"] == "ended"

    async def test_unauthenticated_create(self, client):
        resp = await client.post("/meetings", json={"title": "No Auth"})
        assert resp.status == 401


class TestHealthCheck:

    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status == 200
        body = await resp.json()
        assert body["status"] == "ok"
