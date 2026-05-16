"""P2P server — teacher listens for incoming student connections."""

from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Callable

from chenedusys.core.event_bus import EventBus
from chenedusys.transport.protocol import CONTROL, FrameReader, decode, encode

logger = logging.getLogger(__name__)


class Peer:
    """Represents a connected student."""

    __slots__ = ("peer_id", "reader", "writer", "_server")

    def __init__(
        self,
        peer_id: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        server: P2PServer,
    ) -> None:
        self.peer_id = peer_id
        self.reader = reader
        self.writer = writer
        self._server = server

    async def send(self, channel: int, payload: dict | bytes) -> None:
        frame = encode(channel, payload)
        try:
            self.writer.write(frame)
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logger.warning("Send to peer %s failed: %s", self.peer_id, exc)

    def close(self) -> None:
        if not self.writer.is_closing():
            self.writer.close()


class P2PServer:
    """TCP server that accepts P2P connections from students.

    The teacher runs this after creating a meeting. Students connect
    using the address/port exchanged via the signaling server.
    """

    def __init__(
        self,
        bus: EventBus,
        max_peers: int = 5,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._bus = bus
        self._max_peers = max_peers
        self._ssl_context = ssl_context
        self._server: asyncio.Server | None = None
        self._peers: dict[str, Peer] = {}
        self._running = False
        self._listen_task: asyncio.Task | None = None
        self._on_message: Callable[[Peer, int, dict | bytes], None] | None = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def on_message(self, handler: Callable[[Peer, int, dict | bytes], None]) -> None:
        """Register a callback for incoming messages from any peer.

        Handler signature: ``handler(peer, channel, payload)``
        """
        self._on_message = handler

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def port(self) -> int | None:
        if self._server is not None:
            sockets = self._server.sockets
            if sockets:
                return sockets[0].getsockname()[1]
        return None

    @property
    def peers(self) -> dict[str, Peer]:
        return dict(self._peers)

    @property
    def peer_count(self) -> int:
        return len(self._peers)

    async def start(self, port: int = 0, host: str = "0.0.0.0") -> int:
        """Start listening. Returns the actual port bound."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            host=host,
            port=port,
            ssl=self._ssl_context,
        )
        self._running = True
        actual_port = self.port
        logger.info("P2P server listening on %s:%d", host, actual_port)
        return actual_port  # type: ignore[return-value]

    async def stop(self) -> None:
        """Stop server and disconnect all peers."""
        self._running = False
        for peer in list(self._peers.values()):
            peer.close()
        self._peers.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.info("P2P server stopped")

    async def send_to_all(self, channel: int, payload: dict | bytes) -> None:
        """Broadcast a message to all connected peers."""
        for peer in list(self._peers.values()):
            await peer.send(channel, payload)

    async def send_to_peer(self, peer_id: str, channel: int, payload: dict | bytes) -> None:
        peer = self._peers.get(peer_id)
        if peer:
            await peer.send(channel, payload)
        else:
            logger.warning("Unknown peer %s", peer_id)

    def kick_peer(self, peer_id: str) -> None:
        peer = self._peers.pop(peer_id, None)
        if peer:
            peer.close()
            logger.info("Kicked peer %s", peer_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        addr = writer.get_extra_info("peername")
        logger.info("Incoming connection from %s", addr)

        if self.peer_count >= self._max_peers:
            # Send rejection and close
            frame = encode(CONTROL, {"type": "reject", "reason": "meeting_full"})
            writer.write(frame)
            await writer.drain()
            writer.close()
            logger.info("Rejected connection from %s — meeting full", addr)
            return

        # Wait for the handshake: first message must be a CONTROL "hello"
        peer_id = await self._handshake(reader, writer)
        if peer_id is None:
            writer.close()
            return

        # If peer reconnects, drop old connection
        old = self._peers.pop(peer_id, None)
        if old:
            old.close()

        peer = Peer(peer_id, reader, writer, self)
        self._peers[peer_id] = peer

        # Send welcome
        await peer.send(CONTROL, {"type": "welcome"})

        self._bus.publish(_PeerEvent("network.p2p_connected", {"peer_id": peer_id}))
        logger.info("Peer %s connected from %s", peer_id, addr)

        # Read loop
        await self._read_loop(peer)

    async def _handshake(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> str | None:
        """Read the first frame — must be CONTROL hello with peer_id."""
        try:
            header = await asyncio.wait_for(reader.readexactly(5), timeout=10.0)
            import struct
            length, channel = struct.unpack("!IB", header)
            if channel != CONTROL:
                logger.warning("Handshake: first frame not CONTROL (0x%02x)", channel)
                return None
            body = await asyncio.wait_for(reader.readexactly(length), timeout=10.0)
            channel, payload = decode(header + body)
            if not isinstance(payload, dict) or payload.get("type") != "hello":
                logger.warning("Handshake: expected hello, got %s", payload)
                return None
            peer_id = payload.get("peer_id", "")
            if not peer_id:
                return None
            return peer_id
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, Exception) as exc:
            logger.warning("Handshake failed: %s", exc)
            return None

    async def _read_loop(self, peer: Peer) -> None:
        frame_reader = FrameReader()
        try:
            while self._running:
                data = await peer.reader.read(65536)
                if not data:
                    break
                frame_reader.feed(data)
                for channel, payload in frame_reader:
                    if self._on_message:
                        self._on_message(peer, channel, payload)
        except (ConnectionResetError, asyncio.IncompleteReadError, OSError):
            pass
        finally:
            # Only remove if this is still the current peer (not replaced)
            current = self._peers.get(peer.peer_id)
            if current is peer:
                del self._peers[peer.peer_id]
                self._bus.publish(
                    _PeerEvent("network.p2p_disconnected", {"peer_id": peer.peer_id})
                )
                logger.info("Peer %s disconnected", peer.peer_id)
            peer.close()


class _PeerEvent:
    __slots__ = ("topic", "data")

    def __init__(self, topic: str, data: dict) -> None:
        self.topic = topic
        self.data = data
