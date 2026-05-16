"""P2P client — student connects to the teacher's P2P server."""

from __future__ import annotations

import asyncio
import logging
import ssl

from chenedusys.core.event_bus import EventBus
from chenedusys.transport.protocol import CONTROL, FrameReader, encode

logger = logging.getLogger(__name__)


class P2PClient:
    """TCP client that connects to a teacher's P2P server.

    After connecting, sends a handshake ``hello`` message with the
    student's peer ID, then enters a read loop that forwards received
    messages to the EventBus and/or a registered callback.
    """

    def __init__(
        self,
        bus: EventBus,
        peer_id: str,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._bus = bus
        self._peer_id = peer_id
        self._ssl_context = ssl_context
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._read_task: asyncio.Task | None = None
        self._on_message = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def on_message(self, handler) -> None:
        """Register callback for incoming messages. Signature: ``(channel, payload)``."""
        self._on_message = handler

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self, host: str, port: int) -> None:
        """Connect to teacher's P2P server and perform handshake."""
        try:
            self._reader, self._writer = await asyncio.open_connection(
                host, port, ssl=self._ssl_context
            )
        except (OSError, ConnectionRefusedError) as exc:
            logger.error("P2P connect to %s:%d failed: %s", host, port, exc)
            self._bus.publish(
                _ClientEvent(
                    "network.p2p_connect_failed",
                    {"host": host, "port": port, "error": str(exc)},
                )
            )
            return

        # Handshake: send hello
        hello = encode(CONTROL, {"type": "hello", "peer_id": self._peer_id})
        self._writer.write(hello)
        await self._writer.drain()

        # Wait for welcome
        try:
            header = await asyncio.wait_for(self._reader.readexactly(5), timeout=10.0)
            import struct
            length, channel = struct.unpack("!IB", header)
            body = await asyncio.wait_for(self._reader.readexactly(length), timeout=10.0)

            from chenedusys.transport.protocol import decode
            ch, payload = decode(header + body)
            if isinstance(payload, dict) and payload.get("type") == "reject":
                reason = payload.get("reason", "unknown")
                logger.warning("Server rejected connection: %s", reason)
                self._writer.close()
                self._bus.publish(
                    _ClientEvent(
                        "network.p2p_connect_failed",
                        {"host": host, "port": port, "error": f"rejected: {reason}"},
                    )
                )
                return
        except (asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
            logger.error("Handshake timeout/error: %s", exc)
            self._writer.close()
            self._bus.publish(
                _ClientEvent(
                    "network.p2p_connect_failed",
                    {"host": host, "port": port, "error": f"handshake failed: {exc}"},
                )
            )
            return

        self._connected = True
        logger.info("P2P connected to %s:%d", host, port)
        self._bus.publish(
            _ClientEvent("network.p2p_connected", {"host": host, "port": port})
        )

        # Start read loop
        self._read_task = asyncio.create_task(self._read_loop())

    async def disconnect(self) -> None:
        """Cleanly disconnect from the teacher."""
        self._connected = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self._writer and not self._writer.is_closing():
            self._writer.close()
        self._reader = None
        self._writer = None
        logger.info("P2P client disconnected")
        self._bus.publish(_ClientEvent("network.p2p_disconnected", {}))

    async def send(self, channel: int, payload: dict | bytes) -> None:
        """Send a message to the teacher."""
        if not self._connected or self._writer is None:
            logger.warning("Cannot send — not connected")
            return
        frame = encode(channel, payload)
        try:
            self._writer.write(frame)
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logger.warning("Send failed: %s", exc)
            self._connected = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        frame_reader = FrameReader()
        try:
            while self._connected and self._reader:
                data = await self._reader.read(65536)
                if not data:
                    break
                frame_reader.feed(data)
                for channel, payload in frame_reader:
                    if self._on_message:
                        self._on_message(channel, payload)
        except (ConnectionResetError, asyncio.IncompleteReadError, OSError):
            pass
        except asyncio.CancelledError:
            return
        finally:
            if self._connected:
                self._connected = False
                self._bus.publish(_ClientEvent("network.p2p_disconnected", {}))
                logger.info("P2P connection lost")


class _ClientEvent:
    __slots__ = ("topic", "data")

    def __init__(self, topic: str, data: dict) -> None:
        self.topic = topic
        self.data = data
