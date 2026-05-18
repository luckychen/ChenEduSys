"""Hub server entry point — accounts, signaling, meeting coordination."""

from __future__ import annotations

import logging
import os

from aiohttp import web

from hub_server.admin import setup_admin_routes
from hub_server.auth import hash_password, new_id, verify_password
from hub_server.database import Database
from hub_server.signaling import (
    create_meeting,
    end_meeting,
    get_meeting,
    join_meeting,
    leave_meeting,
    list_meetings,
    ws_signaling,
)

logger = logging.getLogger(__name__)


def _error(status: int, reason: str) -> web.Response:
    return web.json_response({"reason": reason}, status=status)


def seed_admin(db: Database) -> str | None:
    """Create initial admin account. Returns the password (auto-generated if not set via env)."""
    admin_user = os.environ.get("CHENEDUSYS_ADMIN_USER", "admin")
    existing = db.get_user_by_username(admin_user)
    if existing is not None:
        return None

    import secrets
    admin_password = os.environ.get("CHENEDUSYS_ADMIN_PASSWORD") or secrets.token_urlsafe(16)
    pw_hash = hash_password(admin_password)
    db.create_user(new_id(), admin_user, pw_hash, role="admin", status="active")
    logger.info("Seeded admin user '%s'", admin_user)
    return admin_password


# ------------------------------------------------------------------
# Auth REST endpoints
# ------------------------------------------------------------------

async def register(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    body = await request.json()

    username = body.get("username", "").strip()
    password = body.get("password", "")
    role = body.get("role", "student")

    if not username or len(username) < 2:
        raise web.HTTPBadRequest(text='{"reason": "Username must be at least 2 characters"}', content_type="application/json")
    if len(password) < 8:
        raise web.HTTPBadRequest(text='{"reason": "Password must be at least 8 characters"}', content_type="application/json")
    if role not in ("teacher", "student"):
        raise web.HTTPBadRequest(text='{"reason": "Role must be teacher or student"}', content_type="application/json")

    existing = db.get_user_by_username(username)
    if existing is not None:
        raise web.HTTPConflict(text='{"reason": "Username already taken"}', content_type="application/json")

    user_id = new_id()
    pw_hash = hash_password(password)
    db.create_user(user_id, username, pw_hash, role)

    return web.json_response(
        {"id": user_id, "username": username, "role": role, "status": "pending"},
        status=201,
    )


async def login(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    body = await request.json()

    username = body.get("username", "")
    password = body.get("password", "")

    user = db.get_user_by_username(username)
    if user is None or not verify_password(password, user["password_hash"]):
        raise web.HTTPUnauthorized(text='{"reason": "Invalid username or password"}', content_type="application/json")

    if user.get("status") == "pending":
        raise web.HTTPForbidden(text='{"reason": "Account pending approval"}', content_type="application/json")
    if user.get("status") == "rejected":
        raise web.HTTPForbidden(text='{"reason": "Account rejected"}', content_type="application/json")

    from hub_server.auth import create_token
    token = create_token(user["id"], user["username"], user["role"])

    return web.json_response({
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
        },
    })


async def me(request: web.Request) -> web.Response:
    """Return current user info (validates token)."""
    from hub_server.signaling import _require_auth
    payload = _require_auth(request)
    db: Database = request.app["db"]
    user = db.get_user_by_id(payload["sub"])
    if user is None:
        raise web.HTTPUnauthorized(reason="User not found")
    return web.json_response({
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
    })


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------

async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


# ------------------------------------------------------------------
# App factory
# ------------------------------------------------------------------

def create_app(db_path: str | None = None) -> web.Application:
    app = web.Application()
    app["db"] = Database(db_path)

    # Seed admin account
    admin_password = seed_admin(app["db"])
    if admin_password is not None:
        logger.warning("Admin password (save this — shown once): %s", admin_password)

    # Admin dashboard
    setup_admin_routes(app)

    # Auth
    app.router.add_post("/register", register)
    app.router.add_post("/login", login)
    app.router.add_get("/me", me)

    # Meetings
    app.router.add_post("/meetings", create_meeting)
    app.router.add_get("/meetings", list_meetings)
    app.router.add_get("/meetings/{meeting_id}", get_meeting)
    app.router.add_post("/meetings/{meeting_id}/join", join_meeting)
    app.router.add_post("/meetings/{meeting_id}/leave", leave_meeting)
    app.router.add_delete("/meetings/{meeting_id}", end_meeting)

    # WebSocket signaling
    app.router.add_get("/ws", ws_signaling)

    # Health
    app.router.add_get("/health", health)

    # Cleanup on shutdown
    async def on_shutdown(app):
        app["db"].close()

    app.on_shutdown.append(on_shutdown)

    return app


def main():
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("CHENEDUSYS_HUB_PORT", "8443"))
    db_path = os.environ.get("CHENEDUSYS_HUB_DB", None)
    app = create_app(db_path)
    logger.info("Hub server starting on port %d", port)
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
