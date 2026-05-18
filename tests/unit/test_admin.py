"""Unit tests for admin dashboard API endpoints."""

from __future__ import annotations

import pytest

from hub_server.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "test.db"))


@pytest.fixture
async def client(aiohttp_client, app):
    return await aiohttp_client(app)


def _db(client):
    return client.app["db"]


async def _admin_login(client):
    """Login as admin. Returns the session cookie jar automatically set by aiohttp."""
    db = _db(client)
    admin = db.get_user_by_username("admin")
    # Admin is seeded with a random password; bypass by setting known one
    from hub_server.auth import hash_password
    from unittest.mock import patch
    # Just use the DB directly to set a known password
    db._conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (hash_password("test-password123"), "admin"),
    )
    db._conn.commit()
    resp = await client.post("/admin/login", json={
        "username": "admin",
        "password": "test-password123",
    })
    return resp


class TestAdminPage:

    async def test_admin_page_served(self, client):
        resp = await client.get("/admin")
        assert resp.status == 200
        text = await resp.text()
        assert "ChenEduSys Admin" in text


class TestAdminLogin:

    async def test_admin_login_success(self, client):
        resp = await _admin_login(client)
        assert resp.status == 200

    async def test_admin_login_wrong_password(self, client):
        resp = await client.post("/admin/login", json={
            "username": "admin",
            "password": "wrong-password",
        })
        assert resp.status == 401

    async def test_admin_login_non_admin(self, client):
        from hub_server.auth import hash_password
        db = _db(client)
        pw_hash = hash_password("password123")
        db.create_user("u1", "student1", pw_hash, "student", status="active")
        resp = await client.post("/admin/login", json={
            "username": "student1",
            "password": "password123",
        })
        assert resp.status == 403


class TestAdminAPI:

    async def _setup_admin_session(self, client):
        """Login as admin and return client (cookie auto-set)."""
        await _admin_login(client)
        return client

    async def test_list_pending(self, client):
        client = await self._setup_admin_session(client)
        db = _db(client)
        db.create_user("u1", "pending_user", "hash", "student", status="pending")
        db.create_user("u2", "active_user", "hash", "student", status="active")

        resp = await client.get("/admin/pending")
        assert resp.status == 200
        body = await resp.json()
        assert len(body) == 1
        assert body[0]["username"] == "pending_user"

    async def test_list_all_users(self, client):
        client = await self._setup_admin_session(client)
        db = _db(client)
        db.create_user("u1", "user1", "hash", "student", status="pending")
        db.create_user("u2", "user2", "hash", "teacher", status="active")

        resp = await client.get("/admin/users")
        assert resp.status == 200
        body = await resp.json()
        usernames = [u["username"] for u in body]
        assert "user1" in usernames
        assert "user2" in usernames
        assert "admin" in usernames

    async def test_approve_user(self, client):
        client = await self._setup_admin_session(client)
        db = _db(client)
        db.create_user("u1", "pending_user", "hash", "student", status="pending")

        resp = await client.post("/admin/approve", json={
            "user_id": "u1",
            "role": "teacher",
        })
        assert resp.status == 200
        body = await resp.json()
        assert body["status"] == "approved"

        user = db.get_user_by_id("u1")
        assert user["status"] == "active"
        assert user["role"] == "teacher"

    async def test_approve_invalid_role(self, client):
        client = await self._setup_admin_session(client)
        db = _db(client)
        db.create_user("u1", "pending_user", "hash", "student", status="pending")

        resp = await client.post("/admin/approve", json={
            "user_id": "u1",
            "role": "admin",
        })
        assert resp.status == 400

    async def test_approve_nonexistent_user(self, client):
        client = await self._setup_admin_session(client)
        resp = await client.post("/admin/approve", json={
            "user_id": "nonexistent",
            "role": "student",
        })
        assert resp.status == 404

    async def test_reject_user(self, client):
        client = await self._setup_admin_session(client)
        db = _db(client)
        db.create_user("u1", "pending_user", "hash", "student", status="pending")

        resp = await client.post("/admin/reject", json={"user_id": "u1"})
        assert resp.status == 200
        user = db.get_user_by_id("u1")
        assert user["status"] == "rejected"

    async def test_reject_nonexistent_user(self, client):
        client = await self._setup_admin_session(client)
        resp = await client.post("/admin/reject", json={"user_id": "nonexistent"})
        assert resp.status == 404

    async def test_stats(self, client):
        client = await self._setup_admin_session(client)
        db = _db(client)
        db.create_user("u1", "p1", "hash", "student", status="pending")
        db.create_user("u2", "p2", "hash", "student", status="pending")
        db.create_user("u3", "a1", "hash", "teacher", status="active")
        db.create_user("u4", "r1", "hash", "student", status="rejected")

        resp = await client.get("/admin/stats")
        assert resp.status == 200
        body = await resp.json()
        assert body["pending"] == 2
        assert body["active"] == 2  # admin + a1
        assert body["rejected"] == 1
        assert body["total"] == 5


class TestAdminSession:

    async def test_unauthenticated_api_returns_401(self, client):
        resp = await client.get("/admin/pending")
        assert resp.status == 401

    async def test_logout(self, client):
        await _admin_login(client)
        resp = await client.post("/admin/logout")
        assert resp.status == 200

        # Subsequent request should be unauthorized
        resp = await client.get("/admin/pending")
        assert resp.status == 401


class TestSeedAdmin:

    def test_seed_admin_creates_account(self, tmp_path):
        from hub_server.database import Database
        from hub_server.main import seed_admin

        db = Database(str(tmp_path / "test.db"))
        password = seed_admin(db)
        assert password is not None

        admin = db.get_user_by_username("admin")
        assert admin is not None
        assert admin["role"] == "admin"
        assert admin["status"] == "active"
        db.close()

    def test_seed_admin_idempotent(self, tmp_path):
        from hub_server.database import Database
        from hub_server.main import seed_admin

        db = Database(str(tmp_path / "test.db"))
        pw1 = seed_admin(db)
        pw2 = seed_admin(db)
        assert pw1 is not None
        assert pw2 is None  # already exists
        db.close()

    def test_seed_admin_custom_credentials(self, tmp_path, monkeypatch):
        import os
        from hub_server.database import Database
        from hub_server.main import seed_admin

        monkeypatch.setenv("CHENEDUSYS_ADMIN_USER", "superadmin")
        monkeypatch.setenv("CHENEDUSYS_ADMIN_PASSWORD", "my-secret-pw")
        db = Database(str(tmp_path / "test.db"))
        password = seed_admin(db)
        assert password == "my-secret-pw"

        admin = db.get_user_by_username("superadmin")
        assert admin is not None
        assert admin["role"] == "admin"
        db.close()
