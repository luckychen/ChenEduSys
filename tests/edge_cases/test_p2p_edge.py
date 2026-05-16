"""Edge-case tests for P2P networking."""

from __future__ import annotations

import asyncio
import struct

import pytest

from chenedusys.core.event_bus import EventBus
from chenedusys.transport.p2p_client import P2PClient
from chenedusys.transport.p2p_server import P2PServer
from chenedusys.transport.protocol import (
    CONTROL,
    HEADER_SIZE,
    ProtocolError,
    FrameReader,
    decode,
    encode,
    frame_size,
)


@pytest.fixture
def bus():
    return EventBus()


class TestProtocolEdgeCases:

    def test_oversized_payload_rejected(self):
        big = b"\x00" * (10 * 1024 * 1024 + 1)
        with pytest.raises(ProtocolError, match="Payload too large"):
            encode(CONTROL, big)

    def test_malformed_frame_random_bytes(self):
        with pytest.raises(ProtocolError):
            decode(b"\xFF" * 50)

    def test_frame_with_exact_max_size(self):
        # Just under the limit
        big = b"\x00" * (10 * 1024 * 1024)
        frame = encode(CONTROL, big)
        assert len(frame) == HEADER_SIZE + 10 * 1024 * 1024
        ch, payload = decode(frame)
        assert len(payload) == 10 * 1024 * 1024

    def test_many_tiny_frames(self):
        reader = FrameReader()
        data = b""
        for i in range(100):
            data += encode(CONTROL, {"seq": i})
        reader.feed(data)
        results = list(reader)
        assert len(results) == 100
        assert results[0][1]["seq"] == 0
        assert results[99][1]["seq"] == 99

    def test_frame_size_with_partial_data(self):
        frame = encode(CONTROL, {"test": True})
        # Only header, no payload
        partial = frame[:HEADER_SIZE]
        length = struct.unpack("!I", partial[:4])[0]
        assert frame_size(partial) == HEADER_SIZE + length


class TestP2PEdgeCases:

    async def test_tcp_fragmentation(self, bus):
        """Data arrives in small chunks — should reassemble correctly."""
        server = P2PServer(bus, max_peers=2)
        server_msgs = []
        server.on_message(lambda peer, ch, payload: server_msgs.append(payload))
        port = await server.start(port=0)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        # Send handshake
        writer.write(encode(CONTROL, {"type": "hello", "peer_id": "s1"}))
        await writer.drain()
        await asyncio.sleep(0.1)

        # Send a large message in tiny chunks
        big_payload = {"data": "x" * 5000}
        frame = encode(CONTROL, big_payload)
        for i in range(0, len(frame), 3):
            writer.write(frame[i:i+3])
            await asyncio.sleep(0)  # yield to event loop
        await writer.drain()
        await asyncio.sleep(0.3)

        assert any(isinstance(m, dict) and m.get("data") == "x" * 5000 for m in server_msgs)

        writer.close()
        await server.stop()

    async def test_sudden_disconnect(self, bus):
        """Client drops without clean close."""
        server = P2PServer(bus, max_peers=2)
        events = []
        bus.subscribe("network.p2p_disconnected", lambda e: events.append(e))
        port = await server.start(port=0)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(encode(CONTROL, {"type": "hello", "peer_id": "s1"}))
        await writer.drain()
        await asyncio.sleep(0.1)

        # Abrupt close
        writer.close()
        await asyncio.sleep(0.3)

        assert server.peer_count == 0

        await server.stop()

    async def test_invalid_handshake_no_hello(self, bus):
        """Client sends non-hello first message — should be rejected."""
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        # Send something that's not a hello
        writer.write(encode(CONTROL, {"type": "not_hello", "peer_id": "s1"}))
        await writer.drain()

        await asyncio.sleep(0.1)
        assert server.peer_count == 0

        writer.close()
        await server.stop()

    async def test_invalid_handshake_wrong_channel(self, bus):
        """Client sends first message on AUDIO channel, not CONTROL."""
        from chenedusys.transport.protocol import AUDIO
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(encode(AUDIO, {"type": "hello", "peer_id": "s1"}))
        await writer.drain()

        await asyncio.sleep(0.1)
        assert server.peer_count == 0

        writer.close()
        await server.stop()

    async def test_connection_flood(self, bus):
        """Many rapid connections — server should handle gracefully."""
        server = P2PServer(bus, max_peers=50)
        port = await server.start(port=0)

        writers = []
        for i in range(20):
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(encode(CONTROL, {"type": "hello", "peer_id": f"s{i}"}))
            writers.append(w)

        await asyncio.sleep(0.3)
        assert server.peer_count == 20

        for w in writers:
            w.close()
        await server.stop()

    async def test_send_to_nonexistent_peer(self, bus):
        """Sending to a peer that doesn't exist should log warning, not crash."""
        server = P2PServer(bus, max_peers=5)
        port = await server.start(port=0)
        # Should not raise
        await server.send_to_peer("nonexistent", CONTROL, {"type": "test"})
        await server.stop()

    async def test_client_connect_to_wrong_port(self, bus):
        """Client connects to a port where nothing is listening."""
        events = []
        bus.subscribe("network.p2p_connect_failed", lambda e: events.append(e))

        client = P2PClient(bus, peer_id="s1")
        await client.connect("127.0.0.1", 59998)
        assert not client.connected
        assert len(events) == 1
