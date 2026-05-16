"""Edge-case tests for hub server and auth."""

from __future__ import annotations


class TestEdgeCases:

    async def test_concurrent_registrations(self, aiohttp_client, tmp_path):
        from hub_server.main import create_app
        app = create_app(str(tmp_path / "test.db"))
        client = await aiohttp_client(app)

        import asyncio
        tasks = [
            client.post("/register", json={"username": f"user_{i}", "password": "password123"})
            for i in range(10)
        ]
        responses = await asyncio.gather(*tasks)
        statuses = [r.status for r in responses]
        assert all(s == 201 for s in statuses)

    async def test_unicode_username(self, aiohttp_client, tmp_path):
        from hub_server.main import create_app
        app = create_app(str(tmp_path / "test.db"))
        client = await aiohttp_client(app)

        resp = await client.post("/register", json={"username": "用户名", "password": "password123"})
        assert resp.status == 201
        login = await client.post("/login", json={"username": "用户名", "password": "password123"})
        assert login.status == 200

    async def test_join_full_meeting(self, aiohttp_client, tmp_path):
        from hub_server.main import create_app
        app = create_app(str(tmp_path / "test.db"))
        client = await aiohttp_client(app)

        # Create teacher + meeting with max 2 participants
        await client.post("/register", json={"username": "tf", "password": "password123", "role": "teacher"})
        login = await client.post("/login", json={"username": "tf", "password": "password123"})
        t_token = (await login.json())["token"]

        resp = await client.post("/meetings", json={"title": "Full", "max_participants": 3}, headers={"Authorization": f"Bearer {t_token}"})
        mid = (await resp.json())["id"]

        # Fill it up — teacher is auto-added, so 2 more students fills to 3
        for i in range(2):
            name = f"sf{i}"
            await client.post("/register", json={"username": name, "password": "password123"})
            login_resp = await client.post("/login", json={"username": name, "password": "password123"})
            tk = (await login_resp.json())["token"]
            r = await client.post(f"/meetings/{mid}/join", headers={"Authorization": f"Bearer {tk}"})
            assert r.status == 200

        # One more should fail
        await client.post("/register", json={"username": "overflow", "password": "password123"})
        login_resp = await client.post("/login", json={"username": "overflow", "password": "password123"})
        tk = (await login_resp.json())["token"]
        r = await client.post(f"/meetings/{mid}/join", headers={"Authorization": f"Bearer {tk}"})
        assert r.status == 403

    async def test_password_with_special_chars(self, aiohttp_client, tmp_path):
        from hub_server.main import create_app
        app = create_app(str(tmp_path / "test.db"))
        client = await aiohttp_client(app)

        pw = "p@$$w0rd!#%^&*()"
        await client.post("/register", json={"username": "spec", "password": pw})
        login = await client.post("/login", json={"username": "spec", "password": pw})
        assert login.status == 200

    async def test_token_after_restart(self, aiohttp_client, tmp_path):
        """Token should remain valid after server restart (same JWT secret)."""
        from hub_server.main import create_app
        db_path = str(tmp_path / "test.db")

        app1 = create_app(db_path)
        client1 = await aiohttp_client(app1)
        await client1.post("/register", json={"username": "persist", "password": "password123"})
        login = await client1.post("/login", json={"username": "persist", "password": "password123"})
        token = (await login.json())["token"]

        # New server instance, same DB
        app2 = create_app(db_path)
        client2 = await aiohttp_client(app2)
        resp = await client2.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status == 200
