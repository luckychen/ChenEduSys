"""Unit tests for P2P server."""

from __future__ import annotations

import asyncio

import pytest

from chenedusys.core.event_bus import EventBus
from chenedusys.transport.p2p_server import P2PServer
from chenedusys.transport.protocol import CONTROL, FrameReader, encode


@pytest.fixture
def bus():
    return EventBus()


class TestP2PServer:

    async def test_start_and_port(self, bus):
        server = P2PServer(bus, max_peers=3)
        port = await server.start(port=0)
        assert isinstance(port, int)
        assert port > 0
        assert server.running
        await server.stop()

    async def test_stop_cleans_up(self, bus):
        server = P2PServer(bus)
        await server.start(port=0)
        assert server.running
        await server.stop()
        assert not server.running
        assert server.peer_count == 0

    async def test_accept_one_connection(self, bus):
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        events = []
        bus.subscribe("network.p2p_connected", lambda e: events.append(e))

        # Connect a client
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        # Send hello handshake
        hello = encode(CONTROL, {"type": "hello", "peer_id": "student1"})
        writer.write(hello)
        await writer.drain()

        # Wait for welcome
        await asyncio.sleep(0.1)

        assert server.peer_count == 1
        assert "student1" in server.peers

        writer.close()
        await server.stop()

    async def test_reject_when_full(self, bus):
        server = P2PServer(bus, max_peers=1)
        port = await server.start(port=0)

        # First connection
        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        hello = encode(CONTROL, {"type": "hello", "peer_id": "s1"})
        w1.write(hello)
        await w1.drain()
        await asyncio.sleep(0.1)

        # Second should be rejected
        r2, w2 = await asyncio.open_connection("127.0.0.1", port)
        hello2 = encode(CONTROL, {"type": "hello", "peer_id": "s2"})
        w2.write(hello2)
        await w2.drain()

        data = await asyncio.wait_for(r2.read(1024), timeout=1.0)
        fr = FrameReader()
        fr.feed(data)
        results = list(fr)
        assert len(results) >= 1
        ch, payload = results[0]
        assert payload.get("type") == "reject"

        w1.close()
        w2.close()
        await server.stop()

    async def test_send_to_peer(self, bus):
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        hello = encode(CONTROL, {"type": "hello", "peer_id": "s1"})
        writer.write(hello)
        await writer.drain()
        await asyncio.sleep(0.1)

        # Read the welcome first
        welcome_data = await asyncio.wait_for(reader.read(1024), timeout=1.0)

        await server.send_to_peer("s1", CONTROL, {"type": "test", "value": 42})

        data = await asyncio.wait_for(reader.read(1024), timeout=1.0)
        fr = FrameReader()
        fr.feed(data)
        results = list(fr)
        test_msgs = [p for ch, p in results if isinstance(p, dict) and p.get("type") == "test"]
        assert len(test_msgs) == 1
        assert test_msgs[0]["value"] == 42

        writer.close()
        await server.stop()

    async def test_peer_disconnect_detected(self, bus):
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        events = []
        bus.subscribe("network.p2p_disconnected", lambda e: events.append(e))

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        hello = encode(CONTROL, {"type": "hello", "peer_id": "s1"})
        writer.write(hello)
        await writer.drain()
        await asyncio.sleep(0.1)

        assert server.peer_count == 1

        writer.close()
        await asyncio.sleep(0.2)

        assert server.peer_count == 0
        assert len(events) == 1

        await server.stop()

    async def test_kick_peer(self, bus):
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        hello = encode(CONTROL, {"type": "hello", "peer_id": "s1"})
        writer.write(hello)
        await writer.drain()
        await asyncio.sleep(0.1)

        assert server.peer_count == 1
        server.kick_peer("s1")
        assert server.peer_count == 0

        await server.stop()

    async def test_duplicate_peer_replaces(self, bus):
        server = P2PServer(bus, max_peers=5)
        port = await server.start(port=0)

        # First connection
        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        w1.write(encode(CONTROL, {"type": "hello", "peer_id": "s1"}))
        await w1.drain()
        await asyncio.sleep(0.2)

        assert server.peer_count == 1

        # Second connection with same peer_id — old should be dropped
        r2, w2 = await asyncio.open_connection("127.0.0.1", port)
        w2.write(encode(CONTROL, {"type": "hello", "peer_id": "s1"}))
        await w2.drain()
        await asyncio.sleep(0.3)

        assert server.peer_count == 1

        w1.close()
        w2.close()
        await server.stop()

    async def test_broadcast_to_all(self, bus):
        server = P2PServer(bus, max_peers=5)
        port = await server.start(port=0)

        readers = []
        writers = []
        for i in range(3):
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(encode(CONTROL, {"type": "hello", "peer_id": f"s{i}"}))
            await w.drain()
            readers.append(r)
            writers.append(w)

        await asyncio.sleep(0.2)
        assert server.peer_count == 3

        # Read welcome messages first
        for r in readers:
            await asyncio.wait_for(r.read(4096), timeout=1.0)

        await server.send_to_all(CONTROL, {"type": "broadcast", "msg": "hello_all"})

        for r in readers:
            data = await asyncio.wait_for(r.read(4096), timeout=1.0)
            fr = FrameReader()
            fr.feed(data)
            results = list(fr)
            msgs = [p for ch, p in results if isinstance(p, dict) and p.get("type") == "broadcast"]
            assert len(msgs) == 1

        for w in writers:
            w.close()
        await server.stop()
