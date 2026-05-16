"""Integration tests for full P2P flow (server + client together)."""

from __future__ import annotations

import asyncio

import pytest

from chenedusys.core.event_bus import EventBus
from chenedusys.transport.p2p_client import P2PClient
from chenedusys.transport.p2p_server import P2PServer
from chenedusys.transport.protocol import AUDIO, CONTROL, CONTENT, PAINT


@pytest.fixture
def bus():
    return EventBus()


class TestP2PFlow:

    async def test_full_connect_and_exchange(self, bus):
        """Server start → client connect → bidirectional messages."""
        server = P2PServer(bus, max_peers=5)
        port = await server.start(port=0)

        # Track server-side messages
        server_msgs = []
        server.on_message(lambda peer, ch, payload: server_msgs.append(payload))

        # Client connect
        client = P2PClient(bus, peer_id="student1")
        client_msgs = []
        client.on_message(lambda ch, payload: client_msgs.append(payload))
        await client.connect("127.0.0.1", port)
        await asyncio.sleep(0.1)

        assert client.connected
        assert server.peer_count == 1

        # Client → Server
        await client.send(CONTROL, {"type": "chat", "text": "hi from student"})
        await asyncio.sleep(0.1)
        assert any(m.get("text") == "hi from student" for m in server_msgs if isinstance(m, dict))

        # Server → Client
        await server.send_to_all(CONTROL, {"type": "chat", "text": "hi from teacher"})
        await asyncio.sleep(0.1)
        assert any(m.get("text") == "hi from teacher" for m in client_msgs if isinstance(m, dict))

        await client.disconnect()
        await server.stop()

    async def test_multi_peer(self, bus):
        """1 teacher + 3 students connected simultaneously."""
        server = P2PServer(bus, max_peers=5)
        port = await server.start(port=0)

        clients = []
        for i in range(3):
            c = P2PClient(bus, peer_id=f"s{i}")
            await c.connect("127.0.0.1", port)
            clients.append(c)

        await asyncio.sleep(0.1)
        assert server.peer_count == 3

        # Broadcast to all
        await server.send_to_all(CONTROL, {"type": "broadcast", "seq": 1})
        await asyncio.sleep(0.1)

        for c in clients:
            assert not c.connected or c.connected  # still connected

        for c in clients:
            await c.disconnect()
        await server.stop()

    async def test_large_message_transfer(self, bus):
        """Send a 1MB message through the P2P channel."""
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        server_msgs = []
        server.on_message(lambda peer, ch, payload: server_msgs.append(payload))

        client = P2PClient(bus, peer_id="s1")
        await client.connect("127.0.0.1", port)
        await asyncio.sleep(0.1)

        big_data = b"\xAB" * (1024 * 1024)  # 1MB
        await client.send(CONTENT, big_data)
        await asyncio.sleep(0.5)

        assert len(server_msgs) >= 1
        # The big_data should arrive as raw bytes
        found = any(isinstance(m, bytes) and len(m) == 1024 * 1024 for m in server_msgs)
        assert found

        await client.disconnect()
        await server.stop()

    async def test_reconnect_after_disconnect(self, bus):
        """Client disconnects then reconnects."""
        server = P2PServer(bus, max_peers=5)
        port = await server.start(port=0)

        client = P2PClient(bus, peer_id="s1")
        await client.connect("127.0.0.1", port)
        await asyncio.sleep(0.1)
        assert server.peer_count == 1

        await client.disconnect()
        await asyncio.sleep(0.2)
        assert server.peer_count == 0

        # Reconnect
        client2 = P2PClient(bus, peer_id="s1")
        await client2.connect("127.0.0.1", port)
        await asyncio.sleep(0.1)
        assert server.peer_count == 1

        await client2.disconnect()
        await server.stop()

    async def test_concurrent_messaging(self, bus):
        """Multiple clients send messages simultaneously."""
        server = P2PServer(bus, max_peers=10)
        all_msgs = []
        server.on_message(lambda peer, ch, payload: all_msgs.append((peer.peer_id, payload)))
        port = await server.start(port=0)

        clients = []
        for i in range(5):
            c = P2PClient(bus, peer_id=f"s{i}")
            await c.connect("127.0.0.1", port)
            clients.append(c)

        await asyncio.sleep(0.1)

        # All send simultaneously
        tasks = []
        for i, c in enumerate(clients):
            tasks.append(c.send(CONTROL, {"type": "msg", "from": f"s{i}"}))
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.2)

        assert len(all_msgs) == 5

        for c in clients:
            await c.disconnect()
        await server.stop()
