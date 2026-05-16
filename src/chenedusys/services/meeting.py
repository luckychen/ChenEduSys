"""Meeting service — orchestrates P2P connections for a meeting session."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from chenedusys.core.config import AppConfig
from chenedusys.core.event_bus import EventBus
from chenedusys.core.models import User
from chenedusys.transport.nat import discover_with_fallback, get_local_ip
from chenedusys.transport.p2p_client import P2PClient
from chenedusys.transport.p2p_server import P2PServer
from chenedusys.transport.protocol import CONTROL, AUDIO, CONTENT, PAINT
from chenedusys.transport.security import (
    cert_fingerprint,
    cleanup_cert_files,
    create_client_ssl_context,
    create_server_ssl_context,
    generate_cert,
)
from chenedusys.transport.signaling import SignalingClient

logger = logging.getLogger(__name__)


class MeetingService:
    """Coordinates the lifecycle of a meeting session.

    For teachers: starts a P2P server and exchanges connection info
    via signaling so students can connect.

    For students: uses signaling to learn the teacher's address,
    then connects via P2P client.
    """

    def __init__(
        self,
        bus: EventBus,
        signaling: SignalingClient,
        config: AppConfig,
    ) -> None:
        self._bus = bus
        self._signaling = signaling
        self._config = config
        self._user: User | None = None
        self._meeting_id: str | None = None
        self._server: P2PServer | None = None
        self._client: P2PClient | None = None
        self._cert_path: str | None = None
        self._key_path: str | None = None
        self._active = False

        # Subscribe to signaling relay messages
        self._bus.subscribe("network.relay", self._on_relay)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self._active

    @property
    def meeting_id(self) -> str | None:
        return self._meeting_id

    @property
    def is_teacher(self) -> bool:
        return self._user is not None and self._user.role.value == "teacher"

    @property
    def peers(self) -> dict:
        if self._server:
            return self._server.peers
        return {}

    async def start_as_teacher(
        self,
        user: User,
        meeting_id: str,
        max_participants: int = 5,
    ) -> int:
        """Start P2P server as teacher. Returns the listening port."""
        self._user = user
        self._meeting_id = meeting_id
        self._active = True

        # Generate TLS cert
        self._cert_path, self._key_path = generate_cert(
            common_name=f"chenedusys-{meeting_id}"
        )
        ssl_ctx = create_server_ssl_context(self._cert_path, self._key_path)
        fp = cert_fingerprint(self._cert_path)

        # Start server
        self._server = P2PServer(
            bus=self._bus,
            max_peers=max_participants - 1,  # exclude teacher
            ssl_context=ssl_ctx,
        )
        self._server.on_message(self._on_peer_message)

        port = await self._server.start(
            port=self._config.p2p_port_range_start,
        )

        # Announce via signaling
        local_ip = get_local_ip()
        await self._signaling.relay(
            "",  # broadcast
            {
                "type": "p2p_info",
                "meeting_id": meeting_id,
                "teacher_id": user.id,
                "host": local_ip,
                "port": port,
                "cert_fingerprint": fp,
            },
        )

        logger.info("Teacher P2P server on port %d (fingerprint: %s...)", port, fp[:16])
        return port

    async def start_as_student(
        self,
        user: User,
        meeting_id: str,
        teacher_host: str,
        teacher_port: int,
        cert_fp: str | None = None,
    ) -> None:
        """Connect to teacher's P2P server as student."""
        self._user = user
        self._meeting_id = meeting_id
        self._active = True

        ssl_ctx = create_client_ssl_context(expected_fingerprint=cert_fp)

        self._client = P2PClient(
            bus=self._bus,
            peer_id=user.id,
            ssl_context=ssl_ctx,
        )
        self._client.on_message(self._on_server_message)

        await self._client.connect(teacher_host, teacher_port)
        logger.info("Student connected to %s:%d", teacher_host, teacher_port)

    async def stop(self) -> None:
        """Stop the meeting session."""
        self._active = False

        if self._server:
            await self._server.stop()
            self._server = None

        if self._client:
            await self._client.disconnect()
            self._client = None

        if self._cert_path and self._key_path:
            cleanup_cert_files(self._cert_path, self._key_path)
            self._cert_path = None
            self._key_path = None

        self._meeting_id = None
        logger.info("Meeting session stopped")

    async def send_to_all(self, channel: int, payload: dict | bytes) -> None:
        """Send to all peers (teacher broadcasts to students)."""
        if self._server:
            await self._server.send_to_all(channel, payload)

    async def send_to_teacher(self, channel: int, payload: dict | bytes) -> None:
        """Send to teacher (student sends upstream)."""
        if self._client:
            await self._client.send(channel, payload)

    async def send_to_peer(self, peer_id: str, channel: int, payload: dict | bytes) -> None:
        """Send to a specific peer (teacher to student)."""
        if self._server:
            await self._server.send_to_peer(peer_id, channel, payload)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _on_peer_message(self, peer, channel: int, payload: Any) -> None:
        """Handle message from a student (teacher side)."""
        self._bus.publish(
            _MessageEvent(
                "network.p2p_message",
                {
                    "peer_id": peer.peer_id,
                    "channel": channel,
                    "payload": payload,
                    "direction": "incoming",
                },
            )
        )

    def _on_server_message(self, channel: int, payload: Any) -> None:
        """Handle message from teacher (student side)."""
        self._bus.publish(
            _MessageEvent(
                "network.p2p_message",
                {
                    "channel": channel,
                    "payload": payload,
                    "direction": "incoming",
                },
            )
        )

    def _on_relay(self, event: Any) -> None:
        """Handle relay messages from signaling server."""
        data = getattr(event, "data", {})
        payload = data.get("payload", data)
        msg_type = payload.get("type", "") if isinstance(payload, dict) else ""

        if msg_type == "p2p_info" and self._user:
            # Student receives teacher's P2P connection info
            meeting_id = payload.get("meeting_id", "")
            if meeting_id != self._meeting_id:
                return
            teacher_id = payload.get("teacher_id", "")
            if self._user.id == teacher_id:
                return  # ignore own message

            host = payload.get("host", "")
            port = payload.get("port", 0)
            cert_fp = payload.get("cert_fingerprint")

            if self._client is None and self._active:
                asyncio.create_task(
                    self.start_as_student(
                        self._user, meeting_id, host, port, cert_fp
                    )
                )


class _MessageEvent:
    __slots__ = ("topic", "data")

    def __init__(self, topic: str, data: dict) -> None:
        self.topic = topic
        self.data = data
