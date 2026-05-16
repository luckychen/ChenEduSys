"""WebSocket client that connects to the hub signaling server."""

from __future__ import annotations

import asyncio
import json
import logging

import aiohttp

from chenedusys.core.event_bus import EventBus

logger = logging.getLogger(__name__)

_RECONNECT_BASE_DELAY = 2.0
_RECONNECT_MAX_DELAY = 60.0
_HEARTBEAT_INTERVAL = 30


class SignalingClient:
    """Async WebSocket client for the hub server.

    Handles connection lifecycle, reconnection with exponential backoff,
    and heartbeat pings. All incoming messages are forwarded to the
    EventBus as typed events.
    """

    def __init__(self, bus: EventBus, hub_url: str = "ws://localhost:8443") -> None:
        self._bus = bus
        self._hub_url = hub_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._token: str | None = None
        self._connected = False
        self._authed = False
        self._stop_event = asyncio.Event()
        self._reconnect_delay = _RECONNECT_BASE_DELAY
        self._listen_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected and self._authed

    async def connect(self, token: str) -> None:
        """Open WebSocket and authenticate with *token*."""
        self._token = token
        self._stop_event.clear()
        self._session = aiohttp.ClientSession()
        await self._do_connect()

    async def disconnect(self) -> None:
        self._stop_event.set()
        await self._cancel_tasks()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        self._connected = False
        self._authed = False

    async def send(self, message: dict) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_json(message)
        else:
            logger.warning("Cannot send — WebSocket not connected")

    async def relay(self, target_user_id: str, payload: dict) -> None:
        await self.send({"type": "relay", "target": target_user_id, "payload": payload})

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _do_connect(self) -> None:
        ws_url = f"{self._hub_url}/ws"
        try:
            self._ws = await self._session.ws_connect(ws_url, heartbeat=_HEARTBEAT_INTERVAL)
            self._connected = True
            logger.info("WebSocket connected to %s", ws_url)
            # Authenticate
            await self._ws.send_json({"type": "auth", "token": self._token})
            # Start listening
            self._listen_task = asyncio.create_task(self._listen())
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            self._reconnect_delay = _RECONNECT_BASE_DELAY
        except Exception as exc:
            logger.error("WebSocket connect failed: %s", exc)
            self._connected = False

    async def _listen(self) -> None:
        if self._ws is None:
            return
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    self._handle_message(data)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            self._authed = False
            if not self._stop_event.is_set():
                logger.info("WebSocket lost — scheduling reconnect")
                asyncio.create_task(self._reconnect())

    def _handle_message(self, data: dict) -> None:
        msg_type = data.get("type", "")

        if msg_type == "auth_ok":
            self._authed = True
            logger.info("WebSocket authenticated")
            self._bus.publish(_make_event("network", "ws_auth_ok", data))

        elif msg_type == "auth_fail":
            self._authed = False
            logger.warning("WebSocket auth failed: %s", data.get("reason"))
            self._bus.publish(_make_event("network", "ws_auth_fail", data))

        elif msg_type == "participant_joined":
            self._bus.publish(_make_event("meeting", "participant_joined", data))

        elif msg_type == "meeting_ended":
            self._bus.publish(_make_event("meeting", "meeting_ended", data))

        elif msg_type == "relay":
            self._bus.publish(_make_event("network", "relay", data))

        elif msg_type == "pong":
            pass  # heartbeat response

        else:
            logger.debug("Unhandled WS message type: %s", msg_type)

    async def _heartbeat(self) -> None:
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                if self._ws and not self._ws.closed:
                    await self._ws.send_json({"type": "ping"})
        except asyncio.CancelledError:
            pass

    async def _reconnect(self) -> None:
        while not self._stop_event.is_set():
            logger.info("Reconnecting in %.0fs...", self._reconnect_delay)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._reconnect_delay
                )
                return  # stop was requested
            except asyncio.TimeoutError:
                pass

            try:
                await self._do_connect()
                if self._connected:
                    return
            except Exception as exc:
                logger.error("Reconnect failed: %s", exc)

            self._reconnect_delay = min(self._reconnect_delay * 2, _RECONNECT_MAX_DELAY)

    async def _cancel_tasks(self) -> None:
        for task in (self._listen_task, self._heartbeat_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


def _make_event(category: str, name: str, data: dict):
    """Create a lightweight namespace-style event for the bus."""
    # We use a simple object with a .topic attribute so the EventBus works
    class _Event:
        __slots__ = ("topic", "data")
        def __init__(self, cat, n, d):
            self.topic = f"{cat}.{n}"
            self.data = d
    return _Event(category, name, data)
