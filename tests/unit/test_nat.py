"""Unit tests for NAT traversal (STUN protocol logic)."""

from __future__ import annotations

import struct

from chenedusys.transport.nat import (
    _build_stun_request,
    _parse_stun_response,
    _STUN_MAGIC_COOKIE,
    _STUN_BINDING_RESPONSE,
    _STUN_ATTR_XOR_MAPPED_ADDRESS,
    _STUN_ATTR_MAPPED_ADDRESS,
    get_local_ip,
)


class TestSTUNRequest:

    def test_build_request_length(self):
        req = _build_stun_request()
        # Header is 20 bytes (2+2+4+12)
        assert len(req) == 20

    def test_build_request_type(self):
        req = _build_stun_request()
        msg_type = struct.unpack("!H", req[:2])[0]
        assert msg_type == 0x0001  # Binding Request

    def test_build_request_magic_cookie(self):
        req = _build_stun_request()
        magic = struct.unpack("!I", req[4:8])[0]
        assert magic == _STUN_MAGIC_COOKIE


class TestSTUNResponse:

    def test_parse_xor_mapped_address(self):
        # Build a fake STUN response with XOR-MAPPED-ADDRESS
        transaction_id = b"\x00" * 12
        # XOR the IP 1.2.3.4 and port 12345
        import socket
        port = 12345
        xored_port = port ^ (_STUN_MAGIC_COOKIE >> 16)
        ip_int = struct.unpack("!I", socket.inet_aton("1.2.3.4"))[0]
        xored_ip = ip_int ^ _STUN_MAGIC_COOKIE

        attr = struct.pack("!BBH", 0, 0x01, xored_port) + struct.pack("!I", xored_ip)
        attr_header = struct.pack("!HH", _STUN_ATTR_XOR_MAPPED_ADDRESS, len(attr))
        attr_data = attr_header + attr

        msg_len = len(attr_data)
        header = struct.pack("!HHI", _STUN_BINDING_RESPONSE, msg_len, _STUN_MAGIC_COOKIE)
        response = header + transaction_id + attr_data

        result = _parse_stun_response(response)
        assert result is not None
        assert result == ("1.2.3.4", 12345)

    def test_parse_mapped_address(self):
        import socket
        attr = struct.pack("!BBH", 0, 0x01, 5678) + socket.inet_aton("10.0.0.1")
        attr_header = struct.pack("!HH", _STUN_ATTR_MAPPED_ADDRESS, len(attr))
        attr_data = attr_header + attr

        msg_len = len(attr_data)
        header = struct.pack("!HHI", _STUN_BINDING_RESPONSE, msg_len, _STUN_MAGIC_COOKIE)
        response = header + b"\x00" * 12 + attr_data

        result = _parse_stun_response(response)
        assert result is not None
        assert result == ("10.0.0.1", 5678)

    def test_parse_too_short(self):
        assert _parse_stun_response(b"\x00" * 10) is None

    def test_parse_wrong_type(self):
        header = struct.pack("!HHI", 0x0002, 0, _STUN_MAGIC_COOKIE)
        assert _parse_stun_response(header + b"\x00" * 12) is None

    def test_parse_wrong_magic(self):
        header = struct.pack("!HHI", _STUN_BINDING_RESPONSE, 0, 0x00000000)
        assert _parse_stun_response(header + b"\x00" * 12) is None


class TestGetLocalIP:

    def test_returns_string(self):
        ip = get_local_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    def test_valid_format(self):
        ip = get_local_ip()
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255
