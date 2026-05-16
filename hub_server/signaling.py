"""Meeting and signaling endpoints for the hub server."""

from __future__ import annotations

import json
import logging

from aiohttp import web, WSMsgType

from hub_server.auth import decode_token, new_id
from hub_server.database import Database

logger = logging.getLogger(__name__)

# Active WebSocket connections: user_id → WebSocketResponse
_ws_connections: dict[str, web.WebSocketResponse] = {}


def _require_auth(request: web.Request) -> dict:
    """Extract and validate JWT from Authorization header. Returns payload or raises."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise web.HTTPUnauthorized(reason="Missing or invalid Authorization header")
    token = auth_header[7:]
    payload = decode_token(token)
    if payload is None:
        raise web.HTTPUnauthorized(reason="Invalid or expired token")
    return payload


# ------------------------------------------------------------------
# Meeting REST endpoints
# ------------------------------------------------------------------

async def create_meeting(request: web.Request) -> web.Response:
    payload = _require_auth(request)
    if payload["role"] != "teacher":
        raise web.HTTPForbidden(reason="Only teachers can create meetings")

    db: Database = request.app["db"]
    body = await request.json()
    title = body.get("title", "")
    max_participants = body.get("max_participants", 5)
    p2p_host = body.get("p2p_host")
    p2p_port = body.get("p2p_port")

    meeting_id = new_id()
    db.create_meeting(
        meeting_id=meeting_id,
        teacher_id=payload["sub"],
        title=title,
        max_participants=max_participants,
        p2p_host=p2p_host,
        p2p_port=p2p_port,
    )
    # Teacher is automatically a participant
    db.add_participant(meeting_id, payload["sub"])

    meeting = db.get_meeting(meeting_id)
    return web.json_response(meeting, status=201)


async def list_meetings(request: web.Request) -> web.Response:
    _require_auth(request)
    db: Database = request.app["db"]
    meetings = db.list_active_meetings()
    return web.json_response(meetings)


async def get_meeting(request: web.Request) -> web.Response:
    _require_auth(request)
    db: Database = request.app["db"]
    meeting_id = request.match_info["meeting_id"]
    meeting = db.get_meeting(meeting_id)
    if meeting is None:
        raise web.HTTPNotFound(reason="Meeting not found")
    participants = db.get_participants(meeting_id)
    meeting["participants"] = participants
    return web.json_response(meeting)


async def join_meeting(request: web.Request) -> web.Response:
    payload = _require_auth(request)
    db: Database = request.app["db"]
    meeting_id = request.match_info["meeting_id"]

    meeting = db.get_meeting(meeting_id)
    if meeting is None:
        raise web.HTTPNotFound(reason="Meeting not found")
    if meeting["status"] == "ended":
        raise web.HTTPGone(reason="Meeting has ended")

    count = db.participant_count(meeting_id)
    if count >= meeting["max_participants"]:
        raise web.HTTPForbidden(reason="Meeting is full")

    db.add_participant(meeting_id, payload["sub"])

    # Notify teacher via WebSocket that a student joined
    teacher_id = meeting["teacher_id"]
    _send_to_user(teacher_id, {
        "type": "participant_joined",
        "meeting_id": meeting_id,
        "user_id": payload["sub"],
        "username": payload["username"],
    })

    participants = db.get_participants(meeting_id)
    return web.json_response({"meeting_id": meeting_id, "participants": participants})


async def leave_meeting(request: web.Request) -> web.Response:
    payload = _require_auth(request)
    db: Database = request.app["db"]
    meeting_id = request.match_info["meeting_id"]

    db.remove_participant(meeting_id, payload["sub"])
    return web.json_response({"status": "left"})


async def end_meeting(request: web.Request) -> web.Response:
    payload = _require_auth(request)
    db: Database = request.app["db"]
    meeting_id = request.match_info["meeting_id"]

    meeting = db.get_meeting(meeting_id)
    if meeting is None:
        raise web.HTTPNotFound()
    if meeting["teacher_id"] != payload["sub"]:
        raise web.HTTPForbidden(reason="Only the teacher can end the meeting")

    db.update_meeting_status(meeting_id, "ended")

    # Notify all participants
    for p in db.get_participants(meeting_id):
        _send_to_user(p["id"], {"type": "meeting_ended", "meeting_id": meeting_id})

    return web.json_response({"status": "ended"})


# ------------------------------------------------------------------
# WebSocket signaling
# ------------------------------------------------------------------

async def ws_signaling(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    user_id = None

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "reason": "Invalid JSON"})
                continue

            msg_type = data.get("type")

            if msg_type == "auth":
                token = data.get("token", "")
                token_payload = decode_token(token)
                if token_payload is None:
                    await ws.send_json({"type": "auth_fail", "reason": "Invalid token"})
                    continue
                user_id = token_payload["sub"]
                _ws_connections[user_id] = ws
                await ws.send_json({"type": "auth_ok"})
                logger.info("WebSocket auth ok: user=%s", user_id)

            elif msg_type == "relay" and user_id:
                target_id = data.get("target")
                if target_id and target_id in _ws_connections:
                    _ws_connections[target_id].send_json({
                        "type": "relay",
                        "from": user_id,
                        "payload": data.get("payload", {}),
                    })

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

        elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
            break

    # Cleanup
    if user_id and user_id in _ws_connections:
        del _ws_connections[user_id]
    logger.info("WebSocket disconnected: user=%s", user_id)
    return ws


def _send_to_user(user_id: str, message: dict) -> None:
    ws = _ws_connections.get(user_id)
    if ws is not None:
        ws.send_json(message)
