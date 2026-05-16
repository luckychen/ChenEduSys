"""P2P binary protocol: length-prefixed frames with channel multiplexing.

Wire format:
    [4 bytes: big-endian length of payload]
    [1 byte:  channel ID]
    [N bytes: msgpack-encoded payload]

Channels allow different data types to share one TCP connection
with independent ordering and priority handling.
"""

from __future__ import annotations

import struct
from typing import Any

import msgpack

# Channel IDs
CONTROL = 0x01  # meeting commands, participant management
AUDIO = 0x02  # encoded audio frames
CONTENT = 0x03  # PDF pages, page changes
PAINT = 0x04  # stroke data

VALID_CHANNELS = {CONTROL, AUDIO, CONTENT, PAINT}
CHANNEL_NAMES = {CONTROL: "control", AUDIO: "audio", CONTENT: "content", PAINT: "paint"}

HEADER_SIZE = 5  # 4 bytes length + 1 byte channel
MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


class ProtocolError(Exception):
    """Raised on malformed protocol data."""


def encode(channel: int, payload: dict | bytes) -> bytes:
    """Encode a message into a binary frame."""
    if channel not in VALID_CHANNELS:
        raise ProtocolError(f"Invalid channel: 0x{channel:02x}")

    if isinstance(payload, dict):
        data = msgpack.packb(payload, use_bin_type=True)
    elif isinstance(payload, bytes):
        data = payload
    else:
        raise ProtocolError(f"Payload must be dict or bytes, got {type(payload).__name__}")

    if len(data) > MAX_PAYLOAD_SIZE:
        raise ProtocolError(f"Payload too large: {len(data)} bytes (max {MAX_PAYLOAD_SIZE})")

    header = struct.pack("!IB", len(data), channel)
    return header + data


def decode(data: bytes) -> tuple[int, Any]:
    """Decode a single frame. Returns (channel, payload).

    Raises ProtocolError if data is incomplete or malformed.
    Use FrameReader for streaming data.
    """
    if len(data) < HEADER_SIZE:
        raise ProtocolError(f"Incomplete header: got {len(data)} bytes, need {HEADER_SIZE}")

    length, channel = struct.unpack("!IB", data[:HEADER_SIZE])

    if channel not in VALID_CHANNELS:
        raise ProtocolError(f"Invalid channel: 0x{channel:02x}")

    if length > MAX_PAYLOAD_SIZE:
        raise ProtocolError(f"Payload too large: {length} bytes")

    if len(data) < HEADER_SIZE + length:
        raise ProtocolError(
            f"Incomplete payload: got {len(data) - HEADER_SIZE} bytes, need {length}"
        )

    payload_bytes = data[HEADER_SIZE : HEADER_SIZE + length]

    # Try msgpack decode; fall back to raw bytes for audio frames
    try:
        payload: Any = msgpack.unpackb(payload_bytes, raw=False)
    except (msgpack.ExtraData, msgpack.UnpackValueError, ValueError):
        payload = payload_bytes

    return channel, payload


def frame_size(data: bytes) -> int | None:
    """Return the total byte size of the next frame in *data*, or None if incomplete."""
    if len(data) < HEADER_SIZE:
        return None
    length = struct.unpack("!I", data[:4])[0]
    return HEADER_SIZE + length


class FrameReader:
    """Accumulates raw TCP data and yields complete frames.

    Usage::

        reader = FrameReader()
        reader.feed(tcp_data)
        for channel, payload in reader:
            handle(channel, payload)
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> None:
        self._buffer.extend(data)

    def __iter__(self):
        return self

    def __next__(self) -> tuple[int, Any]:
        total = frame_size(bytes(self._buffer))
        if total is None or len(self._buffer) < total:
            raise StopIteration

        frame_data = bytes(self._buffer[:total])
        self._buffer = self._buffer[total:]

        channel, payload = decode(frame_data)
        return channel, payload

    @property
    def buffered(self) -> int:
        return len(self._buffer)
