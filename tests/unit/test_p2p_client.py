"""Unit tests for P2P client."""

from __future__ import annotations

import asyncio

import pytest

from chenedusys.core.event_bus import EventBus
from chenedusys.transport.p2p_client import P2PClient
from chenedusys.transport.p2p_server import P2PServer
from chenedusys.transport.protocol import CONTROL, encode


@pytest.fixture
def bus():
    return EventBus()


class TestP2PClient:

    async def test_connect_to_server(self, bus):
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        client = P2PClient(bus, peer_id="student1")
        await client.connect("127.0.0.1", port)

        assert client.connected

        await client.disconnect()
        await server.stop()

    async def test_connection_refused(self, bus):
        events = []
        bus.subscribe("network.p2p_connect_failed", lambda e: events.append(e))

        client = P2PClient(bus, peer_id="student1")
        await client.connect("127.0.0.1", 59999)  # nobody listening

        assert not client.connected
        assert len(events) == 1
        assert "error" in events[0].data

    async def test_send_and_receive(self, bus):
        server = P2PServer(bus, max_peers=2)
        received = []
        server.on_message(lambda peer, ch, payload: received.append((peer.peer_id, ch, payload)))
        port = await server.start(port=0)

        client = P2PClient(bus, peer_id="s1")
        await client.connect("127.0.0.1", port)
        await asyncio.sleep(0.05)

        await client.send(CONTROL, {"type": "chat", "text": "hello"})
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0][0] == "s1"
        assert received[0][2]["text"] == "hello"

        await client.disconnect()
        await server.stop()

    async def test_disconnect_event(self, bus):
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        client = P2PClient(bus, peer_id="s1")
        await client.connect("127.0.0.1", port)
        assert client.connected

        await client.disconnect()
        assert not client.connected

        await server.stop()

    async def test_send_when_disconnected(self, bus):
        client = P2PClient(bus, peer_id="s1")
        # Should not raise
        await client.send(CONTROL, {"type": "test"})

    async def test_receive_from_server(self, bus):
        server = P2PServer(bus, max_peers=2)
        port = await server.start(port=0)

        client_messages = []
        client = P2PClient(bus, peer_id="s1")
        client.on_message(lambda ch, payload: client_messages.append((ch, payload)))
        await client.connect("127.0.0.1", port)
        await asyncio.sleep(0.05)

        await server.send_to_peer("s1", CONTROL, {"type": "page", "num": 3})
        await asyncio.sleep(0.1)

        assert len(client_messages) >= 1
        page_msgs = [p for ch, p in client_messages if isinstance(p, dict) and p.get("type") == "page"]
        assert len(page_msgs) == 1
        assert page_msgs[0]["num"] == 3

        await client.disconnect()
        await server.stop()
