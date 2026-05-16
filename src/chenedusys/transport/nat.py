"""NAT traversal — STUN-based public IP discovery and port prediction."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct

logger = logging.getLogger(__name__)

_DEFAULT_STUN_PORT = 3478
_STUN_TIMEOUT = 5.0

# STUN message types
_STUN_BINDING_REQUEST = 0x0001
_STUN_BINDING_RESPONSE = 0x0101
_STUN_MAGIC_COOKIE = 0x2112A442
_STUN_ATTR_MAPPED_ADDRESS = 0x0001
_STUN_ATTR_XOR_MAPPED_ADDRESS = 0x0020


def _build_stun_request() -> bytes:
    """Build a STUN Binding Request message."""
    import os
    transaction_id = os.urandom(12)
    # Type: Binding Request (0x0001), Length: 0 (no attributes)
    header = struct.pack("!HHI", _STUN_BINDING_REQUEST, 0, _STUN_MAGIC_COOKIE)
    return header + transaction_id


def _parse_stun_response(data: bytes) -> tuple[str, int] | None:
    """Parse STUN response to extract mapped (public) address."""
    if len(data) < 20:
        return None

    msg_type, msg_len, magic = struct.unpack("!HHI", data[:8])
    if msg_type != _STUN_BINDING_RESPONSE:
        return None
    if magic != _STUN_MAGIC_COOKIE:
        return None

    # Parse attributes
    offset = 20  # skip header (2+2+4+12)
    while offset + 4 <= len(data):
        attr_type, attr_len = struct.unpack("!HH", data[offset : offset + 4])
        attr_data = data[offset + 4 : offset + 4 + attr_len]

        if attr_type == _STUN_ATTR_XOR_MAPPED_ADDRESS:
            return _parse_xor_mapped_address(attr_data, data[4:20])
        elif attr_type == _STUN_ATTR_MAPPED_ADDRESS:
            return _parse_mapped_address(attr_data)

        # Attributes are padded to 4-byte boundary
        padded_len = (attr_len + 3) & ~3
        offset += 4 + padded_len

    return None


def _parse_mapped_address(attr_data: bytes) -> tuple[str, int] | None:
    if len(attr_data) < 8:
        return None
    family = attr_data[1]
    port = struct.unpack("!H", attr_data[2:4])[0]
    if family == 0x01:  # IPv4
        ip = socket.inet_ntoa(attr_data[4:8])
        return ip, port
    return None


def _parse_xor_mapped_address(attr_data: bytes, transaction_id: bytes) -> tuple[str, int] | None:
    if len(attr_data) < 8:
        return None
    family = attr_data[1]
    # XOR port with magic cookie upper 16 bits
    xored_port = struct.unpack("!H", attr_data[2:4])[0]
    port = xored_port ^ (_STUN_MAGIC_COOKIE >> 16)
    if family == 0x01:  # IPv4
        xored_ip = struct.unpack("!I", attr_data[4:8])[0]
        ip_int = xored_ip ^ _STUN_MAGIC_COOKIE
        ip = socket.inet_ntoa(struct.pack("!I", ip_int))
        return ip, port
    return None


async def discover_public_address(
    stun_server: str,
    timeout: float = _STUN_TIMEOUT,
) -> tuple[str, int] | None:
    """Query a STUN server to discover the public IP and port.

    *stun_server* should be in ``"host:port"`` format, or just ``"host"``
    (default port 3478 used).

    Returns ``(public_ip, public_port)`` or ``None`` on failure.
    """
    if ":" in stun_server:
        host, port_str = stun_server.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            host = stun_server
            port = _DEFAULT_STUN_PORT
    else:
        host = stun_server
        port = _DEFAULT_STUN_PORT

    # Strip any "stun:" prefix
    if host.startswith("stun:"):
        host = host[5:]

    request = _build_stun_request()

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, _stun_query, host, port, request, timeout
        )
        return result
    except Exception as exc:
        logger.warning("STUN query to %s:%d failed: %s", host, port, exc)
        return None


def _stun_query(
    host: str, port: int, request: bytes, timeout: float
) -> tuple[str, int] | None:
    """Blocking STUN query (runs in executor)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(request, (host, port))
        data, _ = sock.recvfrom(1024)
        return _parse_stun_response(data)
    except (socket.timeout, OSError) as exc:
        logger.debug("STUN query failed: %s", exc)
        return None
    finally:
        sock.close()


async def discover_with_fallback(
    stun_servers: list[str],
) -> tuple[str, int] | None:
    """Try multiple STUN servers in order; return the first success."""
    for server in stun_servers:
        result = await discover_public_address(server)
        if result is not None:
            return result
    logger.warning("All STUN servers failed — direct connection only")
    return None


def get_local_ip() -> str:
    """Get the machine's LAN IP address (best-effort)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"
