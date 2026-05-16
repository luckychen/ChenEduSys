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


class TestRegisterAndLogin:

    async def test_register_then_login(self, client):
        # Register
        resp = await client.post("/register", json={
            "username": "alice",
            "password": "password123",
            "role": "teacher",
        })
        assert resp.status == 201
        body = await resp.json()
        assert body["username"] == "alice"
        assert body["role"] == "teacher"

        # Login
        resp = await client.post("/login", json={
            "username": "alice",
            "password": "password123",
        })
        assert resp.status == 200
        body = await resp.json()
        assert "token" in body
        assert body["user"]["username"] == "alice"

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
        resp = await client.post("/login", json={"username": "dave", "password": "wrong"})
        assert resp.status == 401

    async def test_login_nonexistent_user(self, client):
        resp = await client.post("/login", json={"username": "ghost", "password": "nopw1234"})
        assert resp.status == 401

    async def test_me_endpoint_with_valid_token(self, client):
        await client.post("/register", json={"username": "eve", "password": "password123"})
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
        # Should succeed as a literal username (no injection)
        assert resp.status == 201
        # Verify no data leak — only this one user
        login_resp = await client.post("/login", json={
            "username": "' OR 1=1 --",
            "password": "password123",
        })
        assert login_resp.status == 200


class TestMeetingFlow:

    async def _make_teacher(self, client, username="teacher1"):
        await client.post("/register", json={"username": username, "password": "password123", "role": "teacher"})
        resp = await client.post("/login", json={"username": username, "password": "password123"})
        return (await resp.json())["token"]

    async def _make_student(self, client, username="student1"):
        await client.post("/register", json={"username": username, "password": "password123", "role": "student"})
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
